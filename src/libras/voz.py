"""Text-to-Speech offline e gratuito, em uma thread própria.

    voz = Voz()
    voz.falar("eu nome caua")      # ou voz.speak(...): não bloqueia
    ...
    voz.encerrar()

Motores (escolhidos automaticamente):
- Windows e Linux: pyttsx3 (Windows usa as vozes SAPI5 do sistema; Linux usa
  o eSpeak: `sudo apt install espeak-ng alsa-utils`);
- macOS: o comando `say` do sistema (o pyttsx3 trava fora da thread principal
  no Mac);
- se o pyttsx3 falhar (ou, no Linux, faltar o `aplay` que ele usa para tocar
  o som), usa os comandos `espeak-ng`/`espeak`.

A voz em português do Brasil é escolhida quando existe (config.IDIOMAS_VOZ).

Situações tratadas:
- texto vazio: ignorado (falar() devolve False);
- fala já em andamento: ignorada ou enfileirada (config.POLITICA_VOZ);
- sem sistema de áudio/voz: `disponivel` fica False, `erro` explica o motivo e
  o resto do programa continua funcionando (só sem som);
- erro durante a fala: registrado em `erro`, avisado por `ao_erro` e o motor é
  recriado na próxima fala.

Nada aqui conhece câmera ou interface: quem usa só chama falar().
"""

from __future__ import annotations

import platform
import queue
import shutil
import subprocess
import threading
from typing import Callable, Protocol

from libras import config


class ErroVoz(RuntimeError):
    """O sistema de voz não pôde ser iniciado ou falhou ao falar."""


class Motor(Protocol):
    nome_voz: str

    def falar_bloqueante(self, texto: str) -> None: ...


def _pontuacao_idioma(descricao: str) -> int:
    """Quanto uma voz combina com config.IDIOMAS_VOZ (maior = melhor, 0 = nada)."""
    descricao = descricao.lower().replace(" ", "")
    for i, idioma in enumerate(config.IDIOMAS_VOZ):
        if idioma in descricao:
            return len(config.IDIOMAS_VOZ) - i
    return 1 if "portug" in descricao else 0


class MotorPyttsx3:
    """pyttsx3: SAPI5 (Windows), eSpeak (Linux). Criado DENTRO da thread da voz."""

    def __init__(self, taxa: int = config.TAXA_FALA) -> None:
        if platform.system() == "Windows":
            try:  # o SAPI5 usa COM, que precisa ser iniciado em cada thread
                import comtypes
                comtypes.CoInitialize()
            except ImportError:
                pass
        import pyttsx3
        self._motor = pyttsx3.init()
        self._motor.setProperty("rate", taxa)
        self.nome_voz = "padrão do sistema"
        melhor, pontos_melhor = None, 0
        for voz in self._motor.getProperty("voices") or []:
            idiomas = " ".join(i.decode(errors="ignore") if isinstance(i, bytes) else str(i)
                               for i in (getattr(voz, "languages", None) or []))
            pontos = _pontuacao_idioma(f"{voz.id} {voz.name} {idiomas}")
            if pontos > pontos_melhor:
                melhor, pontos_melhor = voz, pontos
        if melhor is not None:
            self._motor.setProperty("voice", melhor.id)
            self.nome_voz = melhor.name

    def falar_bloqueante(self, texto: str) -> None:
        self._motor.say(texto)
        self._motor.runAndWait()


class MotorComando:
    """Comando do sistema: `say` (macOS) ou `espeak-ng`/`espeak` (Linux)."""

    def __init__(self, taxa: int = config.TAXA_FALA) -> None:
        if platform.system() == "Darwin" and shutil.which("say"):
            vozes = subprocess.run(["say", "-v", "?"], capture_output=True, text=True, timeout=10).stdout
            linha = max(vozes.splitlines(), key=_pontuacao_idioma, default="")
            voz = linha.split()[0] if linha and _pontuacao_idioma(linha) else None
            self._comando = ["say", "-r", str(taxa)] + (["-v", voz] if voz else [])
            self.nome_voz = voz or "padrão do sistema"
            return
        for programa in ("espeak-ng", "espeak"):
            if shutil.which(programa):
                self._comando = [programa, "-v", "pt-br", "-s", str(taxa)]
                self.nome_voz = f"{programa} pt-br"
                return
        raise ErroVoz("nenhum comando de voz encontrado (say, espeak-ng ou espeak)")

    def falar_bloqueante(self, texto: str) -> None:
        subprocess.run(self._comando + [texto], check=True, capture_output=True, timeout=60)


def criar_motor_padrao() -> Motor:
    """macOS: `say`. Demais: pyttsx3, com os comandos do sistema como alternativa.

    No Linux, o pyttsx3 toca o áudio chamando o programa `aplay` e, se ele não
    existir, falha EM SILÊNCIO; nesse caso usamos direto o `espeak-ng`."""
    sistema = platform.system()
    if sistema == "Darwin" or (sistema == "Linux" and not shutil.which("aplay")
                               and (shutil.which("espeak-ng") or shutil.which("espeak"))):
        return MotorComando()
    try:
        return MotorPyttsx3()
    except Exception as erro_pyttsx3:  # driver ausente, sem áudio, etc.
        try:
            return MotorComando()
        except ErroVoz:
            raise ErroVoz(f"pyttsx3 indisponível ({erro_pyttsx3}) e nenhum comando de voz "
                          "encontrado. No Linux: sudo apt install espeak-ng") from erro_pyttsx3


class Voz:
    """Fala em segundo plano; falar() nunca bloqueia quem chama."""

    def __init__(self, criar_motor: Callable[[], Motor] = criar_motor_padrao,
                 politica: str = config.POLITICA_VOZ,
                 ao_erro: Callable[[str], None] | None = None,
                 timeout_inicio: float = 10.0,
                 recriar_motor_por_fala: bool | None = None) -> None:
        """`ao_erro` é chamado NA THREAD DA VOZ: não mexa em widgets dentro dele.
        `recriar_motor_por_fala`: None = automático (sim no Windows com o motor
        padrão, porque o pyttsx3/SAPI5 às vezes só fala a primeira frase)."""
        if politica not in ("ignorar", "enfileirar"):
            raise ValueError("politica deve ser 'ignorar' ou 'enfileirar'")
        self._criar_motor = criar_motor
        if recriar_motor_por_fala is None:
            recriar_motor_por_fala = platform.system() == "Windows" and criar_motor is criar_motor_padrao
        self.recriar_motor_por_fala = recriar_motor_por_fala
        self.politica = politica
        self.ao_erro = ao_erro
        self.disponivel = False
        self.erro: str | None = None
        self.nome_voz = ""
        self._fila: queue.Queue[str | None] = queue.Queue()
        self._falando = threading.Event()
        self._pronta = threading.Event()
        self._thread = threading.Thread(target=self._trabalhar, name="voz", daemon=True)
        self._thread.start()
        self._pronta.wait(timeout_inicio)

    @property
    def falando(self) -> bool:
        return self._falando.is_set() or not self._fila.empty()

    def falar(self, texto: str) -> bool:
        """Pede para falar `texto`. Devolve False (sem erro) se o texto está vazio,
        a voz está indisponível ou já há uma fala e a política é "ignorar"."""
        texto = (texto or "").strip()
        if not texto or not self.disponivel:
            return False
        if self.falando and self.politica == "ignorar":
            return False
        self._falando.set()  # marca já, para um segundo pedido imediato ser ignorado
        self._fila.put(texto)
        return True

    speak = falar  # nome em inglês, como pedido na especificação

    def encerrar(self, timeout: float = 2.0) -> None:
        self._fila.put(None)
        self._thread.join(timeout)

    # --- thread da voz ---------------------------------------------------------

    def _iniciar_motor(self) -> Motor | None:
        try:
            motor = self._criar_motor()
        except Exception as erro:
            self._registrar_erro(f"voz indisponível: {erro}")
            return None
        self.nome_voz = getattr(motor, "nome_voz", "")
        self.disponivel, self.erro = True, None
        return motor

    def _trabalhar(self) -> None:
        motor = self._iniciar_motor()
        self._pronta.set()
        while True:
            texto = self._fila.get()
            if texto is None:
                break
            try:
                if motor is None:
                    motor = self._iniciar_motor()
                if motor is not None:
                    motor.falar_bloqueante(texto)
            except Exception as erro:  # erro do sistema de áudio durante a fala
                self._registrar_erro(f"erro ao falar: {erro}")
                motor = None  # recria na próxima fala
            finally:
                if self.recriar_motor_por_fala:
                    motor = None  # o próximo pedido cria um motor novo
                if self._fila.empty():
                    self._falando.clear()

    def _registrar_erro(self, mensagem: str) -> None:
        self.erro = mensagem
        if self.ao_erro:
            try:
                self.ao_erro(mensagem)
            except Exception:
                pass


_voz_padrao: Voz | None = None


def speak(texto: str) -> bool:
    """Atalho: fala com uma instância compartilhada (criada no primeiro uso)."""
    global _voz_padrao
    if _voz_padrao is None:
        _voz_padrao = Voz()
    return _voz_padrao.falar(texto)
