"""Testes controlados: máquina de estados, CSV e resumo (sem câmera)."""

import pytest

from libras import config
from libras.experimento import (CONTAGEM, EXECUCAO, FIM, NENHUM, RESULTADO, RegistroCSV, SessaoTeste,
                                ler_csv, plano_de_tentativas, resumir)


def _sessao(plano, registradas, reinicios=None):
    return SessaoTeste(plano, "ana", "s1", "RF teste", registradas.append,
                       ao_iniciar_tentativa=(lambda: reinicios.append(1)) if reinicios is not None else None,
                       contagem_s=1.0, janela_s=3.0, resultado_s=0.5)


def _quadro(s, t, palavra=None, conf=0.0, maos=False, fps=25.0, inf=0.0):
    s.atualizar(t, palavra, conf, maos, fps, inf)


def test_plano_repeticoes_e_semente():
    plano = plano_de_tentativas(["OI", "SIM"], 10, semente=7)
    assert sorted(plano) == ["OI"] * 10 + ["SIM"] * 10
    assert plano == plano_de_tentativas(["OI", "SIM"], 10, semente=7)       # reprodutível
    assert plano_de_tentativas(["OI", "SIM"], 2, 7, aleatorio=False) == ["OI", "OI", "SIM", "SIM"]


def test_acerto_com_tempos_medidos():
    registradas, reinicios = [], []
    s = _sessao(["OI"], registradas, reinicios)
    s.iniciar(0.0)
    assert s.estado == CONTAGEM
    _quadro(s, 1.0)                       # "JÁ!" em t=1.0
    assert s.estado == EXECUCAO and reinicios == [1]
    _quadro(s, 1.2)                       # sem mãos
    _quadro(s, 1.5, maos=True, inf=12.0)  # mãos aparecem em t=1.5
    _quadro(s, 2.3, "OI", 0.91, maos=True, fps=20.0, inf=14.0)
    assert s.estado == RESULTADO and registradas == []   # só confirma após o resultado
    _quadro(s, 2.9)
    assert s.estado == FIM
    t = registradas[0]
    assert t.acerto and t.sinal_reconhecido == "OI" and t.confianca == pytest.approx(0.91)
    assert t.tempo_resposta_s == pytest.approx(1.3)      # 2.3 - 1.0
    assert t.latencia_sistema_s == pytest.approx(0.8)    # 2.3 - 1.5
    assert t.inferencia_ms_media == pytest.approx(13.0)
    assert t.fps_medio == pytest.approx((25 + 25 + 20) / 3)


def test_erro_e_tempo_esgotado():
    registradas = []
    s = _sessao(["OI", "SIM"], registradas)
    s.iniciar(0.0)
    _quadro(s, 1.0)
    _quadro(s, 2.0, "SIM", 0.8, maos=True)               # reconheceu o sinal errado
    _quadro(s, 2.6)                                      # confirma e começa a próxima
    _quadro(s, 3.6)                                      # "JÁ!" da 2ª
    _quadro(s, 6.7)                                      # 3,1 s sem palavra: esgotou
    _quadro(s, 7.3)
    erro, esgotada = registradas
    assert not erro.acerto and erro.sinal_esperado == "OI" and erro.sinal_reconhecido == "SIM"
    assert not esgotada.acerto and esgotada.sinal_reconhecido == NENHUM
    assert esgotada.tempo_resposta_s is None and esgotada.confianca is None


def test_palavra_do_frame_do_ja_nao_conta():
    registradas = []
    s = _sessao(["OI"], registradas)
    s.iniciar(0.0)
    _quadro(s, 1.0, "OI", 0.9)                           # chega no mesmo frame do "JÁ!"
    assert s.estado == EXECUCAO


def test_descartar_refaz_o_mesmo_sinal():
    registradas = []
    s = _sessao(["OI", "SIM"], registradas)
    s.iniciar(0.0)
    _quadro(s, 1.0)
    _quadro(s, 1.5, "SIM", 0.7, maos=True)
    assert s.descartar()
    _quadro(s, 1.6)                                      # próxima tentativa: OI de novo
    assert s.estado == CONTAGEM and s.atual == "OI" and registradas == []
    assert not s.descartar()                             # só vale durante o resultado


def test_pausar_devolve_a_tentativa_para_a_fila():
    registradas = []
    s = _sessao(["OI", "SIM"], registradas)
    s.iniciar(0.0)
    _quadro(s, 1.0)
    s.pausar()
    assert s.pendentes == ["OI", "SIM"] and registradas == []


def test_tentativa_de_nao_sinalizar():
    registradas = []
    s = _sessao([config.CLASSE_NADA, config.CLASSE_NADA], registradas)
    s.iniciar(0.0)
    _quadro(s, 1.0)
    _quadro(s, 4.1)                                      # nada aceito: acerto
    _quadro(s, 4.7)
    _quadro(s, 5.7)
    _quadro(s, 6.0, "OI", 0.8, maos=True)                # falso positivo: erro
    _quadro(s, 6.6)
    assert [t.acerto for t in registradas] == [True, False]


def test_csv_ida_e_volta(tmp_path):
    registradas = []
    s = _sessao(["OI"], registradas)
    s.iniciar(0.0)
    _quadro(s, 1.0)
    _quadro(s, 2.0, "OI", 0.9, maos=True)
    _quadro(s, 2.6)
    registro = RegistroCSV(tmp_path / "t.csv")
    registro.adicionar(registradas[0])
    linha = ler_csv([tmp_path / "t.csv"])[0]
    assert linha["acerto"] is True and linha["sinal_reconhecido"] == "OI"
    assert linha["tempo_resposta_s"] == pytest.approx(1.0) and linha["participante"] == "ana"


def _linha(esperado, reconhecido, tempo=None, participante="ana", fps=25.0, inf=10.0):
    acerto = reconhecido == esperado or (esperado == config.CLASSE_NADA and reconhecido == NENHUM)
    return {"sessao": "s1", "participante": participante, "tentativa": 1, "sinal_esperado": esperado,
            "sinal_reconhecido": reconhecido, "acerto": acerto, "confianca": 0.9 if tempo else None,
            "tempo_resposta_s": tempo, "latencia_sistema_s": tempo, "fps_medio": fps,
            "inferencia_ms_media": inf, "inicio": "", "modelo": "RF"}


def test_resumo_calcula_so_com_o_que_foi_registrado():
    linhas = ([_linha("OI", "OI", 1.0)] * 3 + [_linha("OI", "SIM", 1.4)] +
              [_linha("SIM", "SIM", 2.0)] * 2 + [_linha("SIM", NENHUM)] * 2)
    r = resumir(linhas)
    assert r["tentativas"] == 8
    assert r["accuracy"] == pytest.approx(5 / 8)
    oi, sim = r["por_classe"]["OI"], r["por_classe"]["SIM"]
    assert (oi["acertos"], oi["erros"], oi["confundido_com"]) == (3, 1, {"SIM": 1})
    assert oi["precision"] == pytest.approx(1.0) and oi["recall"] == pytest.approx(0.75)
    assert sim["precision"] == pytest.approx(2 / 3) and sim["recall"] == pytest.approx(0.5)
    assert sim["nao_reconhecidos"] == 2
    assert r["matriz_confusao"]["colunas_reconhecido"] == ["OI", "SIM", NENHUM]
    assert r["matriz_confusao"]["valores"] == [[3, 1, 0], [0, 2, 2]]
    tempos = r["tempo_resposta_s_acertos"]                   # só os 5 acertos
    assert tempos["n"] == 5 and tempos["media"] == pytest.approx((3 * 1.0 + 2 * 2.0) / 5)


def test_resumo_vazio_nao_inventa_nada():
    with pytest.raises(ValueError):
        resumir([])


def test_resumo_sem_tempos_diz_sem_dados():
    r = resumir([_linha("OI", NENHUM), _linha("OI", NENHUM)])
    assert r["accuracy"] == 0.0 and r["tempo_resposta_s_acertos"] == {"n": 0}
