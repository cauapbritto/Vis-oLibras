"""Gerenciador de sentença (independente da visão computacional)."""

from libras import config
from libras.frase import GerenciadorSentenca


def _g(**kw):
    finalizadas = []
    g = GerenciadorSentenca(ao_finalizar=finalizadas.append, **kw)
    return g, finalizadas


def test_exemplo_eu_nome_caua():
    g, finalizadas = _g()
    for i, palavra in enumerate(["EU", "NOME", "CAUA"]):  # qualquer palavra, não só as classes
        assert g.adicionar(palavra, float(i * 2))
    assert g.sequencia == ["EU", "NOME", "CAUA"]
    assert g.frase_atual == "EU NOME CAUA"
    assert g.ultimo_confirmado == "CAUA"
    assert g.finalizar() == "EU NOME CAUA"
    assert finalizadas == ["EU NOME CAUA"]
    assert g.frase_final == "EU NOME CAUA" and g.palavras == []


def test_quatro_estados_sao_independentes():
    g, _ = _g()
    g.atualizar_deteccao("SIM", 0.62)          # só detectado: não entra na sequência
    assert g.sinal_atual == "SIM" and g.palavras == [] and g.ultimo_confirmado is None
    g.adicionar("OI", 0.0)
    assert g.ultimo_confirmado == "OI" and g.sequencia == ["OI"] and g.frase_final == ""
    g.atualizar_deteccao(config.CLASSE_NADA, 1.0)
    assert g.sinal_atual is None and g.confianca_atual == 0.0


def test_repeticao_involuntaria_e_ignorada():
    g, _ = _g(janela_repeticao_s=1.5)
    assert g.adicionar("NOME", 10.0)
    assert not g.adicionar("NOME", 10.8)       # 0,8 s depois: involuntária
    assert g.adicionar("NOME", 12.0)           # 2 s depois: intencional
    assert g.adicionar("OI", 12.1)             # palavra diferente: sempre aceita
    assert g.sequencia == ["NOME", "NOME", "OI"]


def test_palavras_invalidas_sao_ignoradas():
    g, _ = _g()
    assert not g.adicionar("", 0.0)
    assert not g.adicionar("   ", 0.0)
    assert not g.adicionar(config.CLASSE_NADA, 0.0)
    assert g.palavras == []


def test_remover_ultima_e_limpar():
    g, _ = _g()
    for i, p in enumerate(["EU", "NOME", "CAUA"]):
        g.adicionar(p, float(i * 2))
    assert g.remover_ultima() == "CAUA"
    assert g.ultimo_confirmado == "NOME" and g.sequencia == ["EU", "NOME"]
    g.finalizar()
    g.adicionar("OI", 10.0)
    g.limpar()
    assert g.palavras == [] and g.frase_final == "" and g.ultimo_confirmado is None
    assert g.remover_ultima() is None


def test_finalizar_vazio_nao_chama_callback():
    g, finalizadas = _g()
    assert g.finalizar() is None
    assert finalizadas == []


def test_pausa_encerra_a_frase():
    g, finalizadas = _g(pausa_s=2.5)
    g.adicionar("OI", 10.0)
    assert g.verificar_pausa(12.0) is None
    assert g.verificar_pausa(12.6) == "OI"
    assert finalizadas == ["OI"] and g.verificar_pausa(30.0) is None


def test_frase_cheia_e_encerrada_antes_da_proxima_palavra():
    g, finalizadas = _g(max_palavras=2)
    g.adicionar("EU", 0.0)
    g.adicionar("SIM", 2.0)
    g.adicionar("OI", 4.0)
    assert finalizadas == ["EU SIM"] and g.sequencia == ["OI"]


def test_exibicao_e_texto_para_fala():
    g, _ = _g()
    g.adicionar("NAO", 0.0)
    assert g.sequencia == ["NÃO"] and g.frase_atual == "NÃO"
    assert GerenciadorSentenca.texto_para_fala("EU NÃO") == "eu não"


def test_regras_sao_opcionais_e_plugaveis():
    def juntar(palavras):  # exemplo de regra futura
        return ["BOM DIA" if p == "BOM" else p for p in palavras if p != "DIA"]
    g = GerenciadorSentenca(regras=[juntar])
    g.adicionar("BOM", 0.0)
    g.adicionar("DIA", 2.0)
    assert g.sequencia == ["BOM", "DIA"]       # a sequência reconhecida não muda
    assert g.frase_atual == "BOM DIA"
