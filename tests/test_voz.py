"""Módulo de voz com motores falsos (não precisa de alto-falante)."""

import threading
import time

import pytest

from libras import voz as modulo_voz
from libras.voz import ErroVoz, Voz, _pontuacao_idioma


class MotorFalso:
    nome_voz = "Falsa (pt-BR)"

    def __init__(self, duracao=0.0, falhar=False):
        self.falas, self.duracao, self.falhar = [], duracao, falhar
        self.liberar = threading.Event()

    def falar_bloqueante(self, texto):
        if self.falhar:
            raise OSError("dispositivo de áudio indisponível")
        self.falas.append(texto)
        if self.duracao:
            self.liberar.wait(self.duracao)


def _esperar(voz, limite=2.0):
    fim = time.time() + limite
    while voz.falando and time.time() < fim:
        time.sleep(0.01)


def test_fala_em_segundo_plano():
    motor = MotorFalso()
    voz = Voz(criar_motor=lambda: motor)
    assert voz.disponivel and voz.nome_voz == "Falsa (pt-BR)"
    assert voz.speak("eu nome caua") is True        # speak() = falar()
    _esperar(voz)
    assert motor.falas == ["eu nome caua"]
    voz.encerrar()


def test_texto_vazio_e_ignorado():
    motor = MotorFalso()
    voz = Voz(criar_motor=lambda: motor)
    assert voz.falar("") is False and voz.falar("   ") is False and voz.falar(None) is False
    _esperar(voz)
    assert motor.falas == []
    voz.encerrar()


def test_fala_em_andamento_ignora_nova_fala():
    motor = MotorFalso(duracao=5.0)
    voz = Voz(criar_motor=lambda: motor, politica="ignorar")
    assert voz.falar("primeira")
    assert voz.falar("segunda") is False
    motor.liberar.set()
    _esperar(voz)
    assert motor.falas == ["primeira"]
    voz.encerrar()


def test_fala_em_andamento_enfileira_nova_fala():
    motor = MotorFalso(duracao=0.05)
    voz = Voz(criar_motor=lambda: motor, politica="enfileirar")
    assert voz.falar("primeira") and voz.falar("segunda")
    _esperar(voz)
    assert motor.falas == ["primeira", "segunda"]
    voz.encerrar()


def test_sem_sistema_de_voz_fica_indisponivel_sem_quebrar():
    erros = []

    def sem_motor():
        raise ErroVoz("nenhum motor")

    voz = Voz(criar_motor=sem_motor, ao_erro=erros.append)
    assert voz.disponivel is False and "nenhum motor" in voz.erro
    assert voz.falar("oi") is False
    assert erros and "indisponível" in erros[0]
    voz.encerrar()


def test_erro_de_audio_durante_a_fala_e_recupera():
    motores = [MotorFalso(falhar=True), MotorFalso()]
    erros = []
    voz = Voz(criar_motor=lambda: motores.pop(0), ao_erro=erros.append)
    assert voz.falar("primeira")
    _esperar(voz)
    assert erros and "áudio" in voz.erro
    assert voz.falar("segunda")                     # motor recriado
    _esperar(voz)
    voz.encerrar()


def test_motor_que_pede_recriar_e_criado_de_novo_a_cada_fala():
    criados = []

    class MotorDescartavel(MotorFalso):
        recriar_por_fala = True

    def criar():
        criados.append(MotorDescartavel())
        return criados[-1]

    voz = Voz(criar_motor=criar, politica="enfileirar")
    voz.falar("um")
    voz.falar("dois")
    _esperar(voz)
    voz.encerrar()
    assert [m.falas for m in criados] == [["um"], ["dois"]]


# Processo falso que segue o mesmo protocolo do script do PowerShell: responde
# "OK:<voz>" ao abrir e "OK" (ou "ERRO:...") a cada linha em base64; grava os
# textos recebidos num arquivo, para o teste conferir.
_VOZ_FALSA = r"""
import base64, sys
registro = open(sys.argv[1], "a", encoding="utf-8")
if sys.argv[2] == "sem-voz":
    print("ERRO:nenhuma voz instalada no Windows", flush=True)
    sys.exit(1)
print("OK:Microsoft Maria (pt-BR)", flush=True)
for linha in sys.stdin:
    linha = linha.strip()
    if linha == "FIM":
        break
    texto = base64.b64decode(linha).decode("utf-8")
    registro.write(texto + "\n"); registro.flush()
    print("ERRO:falha simulada" if texto == "quebra" else "OK", flush=True)
"""


def _motor_falso(tmp_path, modo="normal"):
    import sys

    class MotorFalsoWindows(modulo_voz.MotorWindows):
        def _comando(self):
            return [sys.executable, "-c", _VOZ_FALSA, str(tmp_path / "falas.txt"), modo]
    return MotorFalsoWindows


def test_motor_windows_fica_aberto_entre_as_falas(tmp_path):
    motor = _motor_falso(tmp_path)()
    assert motor.nome_voz == "Microsoft Maria (pt-BR)"
    processo = motor._processo
    motor.falar_bloqueante("eu não sei, 'obrigado'")    # acentos e aspas chegam inteiros
    motor.falar_bloqueante("segunda fala")
    assert motor._processo is processo and processo.poll() is None   # o mesmo processo
    with pytest.raises(ErroVoz, match="falha simulada"):
        motor.falar_bloqueante("quebra")
    motor.falar_bloqueante("depois do erro")
    motor.fechar()
    assert processo.wait(timeout=5) is not None
    falas = (tmp_path / "falas.txt").read_text(encoding="utf-8").splitlines()
    assert falas == ["eu não sei, 'obrigado'", "segunda fala", "quebra", "depois do erro"]


def test_motor_windows_sem_voz_instalada(tmp_path):
    with pytest.raises(ErroVoz, match="nenhuma voz instalada"):
        _motor_falso(tmp_path, "sem-voz")()


def test_voz_encerra_o_processo_do_motor(tmp_path):
    motor = _motor_falso(tmp_path)()
    voz = Voz(criar_motor=lambda: motor)
    assert voz.falar("oi")
    _esperar(voz, limite=5)
    voz.encerrar(timeout=5)
    assert motor._processo.wait(timeout=5) is not None


def test_politica_invalida():
    with pytest.raises(ValueError):
        Voz(criar_motor=MotorFalso, politica="gritar")


def test_preferencia_por_portugues_do_brasil():
    assert _pontuacao_idioma("roa/pt-BR Portuguese (Brazil)") > _pontuacao_idioma("roa/pt Portuguese (Portugal)")
    assert _pontuacao_idioma("Portuguese (Portugal)") > 0
    assert _pontuacao_idioma("English (America)") == 0


def test_atalho_speak_do_modulo(monkeypatch):
    motor = MotorFalso()
    monkeypatch.setattr(modulo_voz, "_voz_padrao", Voz(criar_motor=lambda: motor))
    assert modulo_voz.speak("oi")
    _esperar(modulo_voz._voz_padrao)
    assert motor.falas == ["oi"]
