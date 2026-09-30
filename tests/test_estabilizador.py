from libras.estabilizador import Estabilizador

PASSO = 0.2  # ~5 previsões por segundo


def _rodar(estabilizador, previsoes, inicio=0.0):
    """previsoes: lista de (sinal, confiança). Devolve as palavras aceitas."""
    aceitas = []
    for i, (sinal, confianca) in enumerate(previsoes):
        palavra = estabilizador.atualizar(sinal, confianca, inicio + i * PASSO)
        if palavra:
            aceitas.append(palavra)
    return aceitas


def _est(**kw):
    padrao = dict(limiar=0.75, n_consecutivas=3, cooldown_s=1.0, cooldown_mesmo_sinal_s=2.0,
                  exigir_liberacao=True, confirmacao_adaptativa=False)
    return Estabilizador(**{**padrao, **kw})


def test_nome_repetido_vira_um_so_nome():
    assert _rodar(_est(), [("NOME", 0.9)] * 5) == ["NOME"]


def test_sinal_segurado_por_10_segundos_vira_um_so():
    assert _rodar(_est(), [("NOME", 0.95)] * 50) == ["NOME"]


def test_precisa_de_n_previsoes_seguidas():
    assert _rodar(_est(), [("NOME", 0.9)] * 2) == []
    assert _rodar(_est(), [("NOME", 0.9), ("SIM", 0.9), ("NOME", 0.9), ("SIM", 0.9)] * 3) == []


def test_confianca_baixa_nao_e_aceita_e_quebra_a_sequencia():
    assert _rodar(_est(), [("NOME", 0.6)] * 10) == []
    assert _rodar(_est(), [("NOME", 0.9), ("NOME", 0.9), ("NOME", 0.5), ("NOME", 0.9), ("NOME", 0.9)]) == []


def test_mesma_palavra_depois_de_soltar_o_sinal():
    previsoes = [("NOME", 0.9)] * 5 + [("_NADA", 1.0)] * 10 + [("NOME", 0.9)] * 5
    assert _rodar(_est(), previsoes) == ["NOME", "NOME"]


def test_mesma_palavra_sem_soltar_nao_repete_mesmo_apos_o_cooldown():
    assert _rodar(_est(), [("NOME", 0.9)] * 40) == ["NOME"]


def test_sem_exigir_liberacao_repete_a_cada_cooldown_do_mesmo_sinal():
    # 40 previsões = 8 s; aceita em t=0.4 e depois a cada ~2 s
    aceitas = _rodar(_est(exigir_liberacao=False), [("NOME", 0.9)] * 40)
    assert aceitas == ["NOME"] * 4


def test_soltar_rapido_demais_respeita_o_cooldown_do_mesmo_sinal():
    previsoes = [("NOME", 0.9)] * 3 + [("_NADA", 1.0)] + [("NOME", 0.9)] * 3
    assert _rodar(_est(), previsoes) == ["NOME"]  # 2ª tentativa em t<2 s


def test_palavra_diferente_espera_o_cooldown_geral():
    est = _est(cooldown_s=1.0)
    assert est.atualizar("OI", 0.9, 0.0) is None
    assert est.atualizar("OI", 0.9, 0.2) is None
    assert est.atualizar("OI", 0.9, 0.4) == "OI"
    for t in (0.6, 0.8, 1.0, 1.2):  # SIM estável, mas dentro do cooldown
        assert est.atualizar("SIM", 0.9, t) is None
    assert est.atualizar("SIM", 0.9, 1.45) == "SIM"


def test_reiniciar_esquece_a_ultima_palavra():
    est = _est()
    assert _rodar(est, [("NOME", 0.9)] * 3) == ["NOME"]
    est.reiniciar()
    assert _rodar(est, [("NOME", 0.9)] * 3, inicio=0.8) == ["NOME"]


def test_progresso():
    est = _est(n_consecutivas=4)
    est.atualizar("OI", 0.9, 0.0)
    est.atualizar("OI", 0.9, 0.2)
    assert est.progresso == 0.5


def test_confirmacao_adaptativa_confianca_alta_aceita_com_duas():
    est = _est(confirmacao_adaptativa=True, limiar_rapido=0.9, n_rapido=2)
    assert est.atualizar("OI", 0.95, 0.0) is None
    assert est.atualizar("OI", 0.93, 0.2) == "OI"          # 2 previsões bastam


def test_confirmacao_adaptativa_confianca_duvidosa_exige_tres():
    est = _est(confirmacao_adaptativa=True, limiar_rapido=0.9, n_rapido=2)
    assert est.atualizar("OI", 0.95, 0.0) is None
    assert est.atualizar("OI", 0.80, 0.2) is None           # uma duvidosa: volta a exigir 3
    assert est.necessarias == 3
    assert est.atualizar("OI", 0.97, 0.4) == "OI"
    # com a adaptativa desligada, sempre 3
    est = _est()
    est.atualizar("SIM", 0.99, 0.0)
    assert est.atualizar("SIM", 0.99, 0.2) is None
