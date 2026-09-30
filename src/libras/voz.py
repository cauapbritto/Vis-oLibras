"""Text-to-Speech offline e gratuito, em uma thread própria.

    voz = Voz()
    voz.falar("eu nome caua")      # ou voz.speak(...): não bloqueia
    ...
    voz.encerrar()

Motores (escolhidos automaticamente, ou por config.MOTOR_VOZ):
- Windows: as vozes do sistema (System.Speech/SAPI) por um processo do
  PowerShell, isolado do programa - o pyttsx3 no Windows depende de COM e
  pode ficar mudo quando usado fora da thread principal; ele fica como
  alternativa;
- Linux: pyttsx3 com o eSpeak (`sudo apt install espeak-ng alsa-utils`);
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

import base64
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

    # No Windows, o pyttsx3/SAPI5 às vezes só fala a primeira frase: recria a cada fala.
    recriar_por_fala = platform.system() == "Windows"

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


_SCRIPT_WINDOWS = r"""
$ErrorActionPreference = 'Stop'
try {
    Add-Type -AssemblyName System.Speech
    $s = New-Object System.Speech.Synthesis.SpeechSynthesizer
    $vozes = @($s.GetInstalledVoices() | Where-Object { $_.Enabled } | ForEach-Object { $_.VoiceInfo })
    if (-not $vozes) { throw 'nenhuma voz instalada no Windows' }
    $v = $vozes | Where-Object { $_.Culture.Name -eq 'pt-BR' } | Select-Object -First 1
    if (-not $v) { $v = $vozes | Where-Object { $_.Culture.Name -like 'pt*' } | Select-Object -First 1 }
    if ($v) { $s.SelectVoice($v.Name) }
    $s.Rate = __TAXA__
    $texto = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('__TEXTO__'))
    if ($texto) { $s.SetOutputToDefaultAudioDevice(); $s.Speak($texto) }
    [Console]::Out.Write('OK:' + $s.Voice.Name + ' (' + $s.Voice.Culture.Name + ')')
} catch {
    [Console]::Out.Write('ERRO:' + $_.Exception.Message)
    exit 1
}
"""


class MotorWindows:
    """Windows: System.Speech (as mesmas vozes SAPI do sistema), um processo do
    PowerShell por fala. Não usa COM no programa, então funciona em qualquer thread."""

    def __init__(self, taxa: int = config.TAXA_FALA) -> None:
        self._powershell = shutil.which("powershell") or shutil.which("pwsh")
        if not self._powershell:
            raise ErroVoz("PowerShell não encontrado")
        self._taxa = max(-10, min(10, round((taxa - 170) / 20)))  # SAPI: -10 a 10, 0 = normal
        self.nome_voz = self._executar("")  # confere se há alguma voz e qual será usada

    def _executar(self, texto: str) -> str:
        script = (_SCRIPT_WINDOWS.replace("__TAXA__", str(self._taxa))
                  .replace("__TEXTO__", base64.b64encode(texto.encode("utf-8")).decode("ascii")))
        comando = [self._powershell, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                   "-EncodedCommand", base64.b64encode(script.encode("utf-16-le")).decode("ascii")]
        resultado = subprocess.run(comando, capture_output=True, timeout=60,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        saida = resultado.stdout.decode(errors="replace").strip()
        if resultado.returncode != 0 or not saida.startswith("OK:"):
            detalhe = saida.removeprefix("ERRO:") or f"código {resultado.returncode}"
            raise ErroVoz(f"vozes do Windows (System.Speech): {detalhe}")
        return saida.removeprefix("OK:")

    def falar_bloqueante(self, texto: str) -> None:
        self._executar(texto)


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


MOTORES = {"windows": MotorWindows, "pyttsx3": MotorPyttsx3, "comando": MotorComando}


def motores_do_sistema() -> list[str]:
    """Nomes dos motores que fazem sentido neste sistema, na ordem de preferência."""
    sistema = platform.system()
    if sistema == "Windows":
        return ["windows", "pyttsx3"]
    if sistema == "Darwin":
        return ["comando"]
    return ["pyttsx3", "comando"]


def criar_motor_padrao() -> Motor:
    """config.MOTOR_VOZ ("auto" = Windows: System.Speech, depois pyttsx3;
    macOS: `say`; Linux: pyttsx3, depois os comandos do sistema).

    No Linux, o pyttsx3 toca o áudio chamando o programa `aplay` e, se ele não
    existir, falha EM SILÊNCIO; nesse caso usamos direto o `espeak-ng`."""
    if config.MOTOR_VOZ != "auto":
        return MOTORES[config.MOTOR_VOZ]()
    sistema = platform.system()
    if sistema == "Windows":
        try:
            return MotorWindows()
        except Exception as erro_windows:
            try:
                return MotorPyttsx3()
            except Exception as erro_pyttsx3:
                raise ErroVoz(f"vozes do Windows indisponíveis ({erro_windows}); "
                              f"pyttsx3 também falhou ({erro_pyttsx3})") from erro_pyttsx3
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
        `recriar_motor_por_fala`: None = automático (o motor decide, pelo
        atributo `recriar_por_fala`; o pyttsx3 no Windows pede isso)."""
        if politica not in ("ignorar", "enfileirar"):
            raise ValueError("politica deve ser 'ignorar' ou 'enfileirar'")
        self._criar_motor = criar_motor
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
                recriar = self.recriar_motor_por_fala
                if recriar is None:
                    recriar = getattr(motor, "recriar_por_fala", False)
                if recriar:
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
