from libras import config
from libras.frase import Frase, carregar_frases, traduzir

FRASES = {("OI",): "Oi!", ("BOM", "DIA"): "Bom dia!", ("OI", "BOM", "DIA"): "Oi, bom dia!",
          ("MEU", "NOME"): "Meu nome é", ("NAO",): "Não."}


def test_traduz_a_maior_combinacao_primeiro():
    assert traduzir(["OI", "BOM", "DIA"], FRASES) == "Oi, bom dia!"
    assert traduzir(["OI", "OBRIGADO"], FRASES) == "Oi! obrigado"
    assert traduzir(["BOM", "DIA", "OI"], FRASES) == "Bom dia! Oi!"


def test_palavras_desconhecidas_viram_minusculas_com_inicial_maiuscula():
    assert traduzir(["EU", "NAO"], FRASES) == "Eu Não."
    assert traduzir(["EU", "AJUDA"], {}) == "Eu ajuda"
    assert traduzir(["NAO"], {}) == "Não"
    assert traduzir([], FRASES) == ""


def test_arquivo_de_frases_do_projeto():
    frases = carregar_frases(config.ARQ_FRASES)
    assert frases[("BOM", "DIA")] == "Bom dia!"
    assert all(p in config.SINAIS for chave in frases for p in chave)


def test_sequencia_glosa_apagar_e_limpar():
    frase = Frase(FRASES)
    for i, p in enumerate(["OI", "BOM", "DIA"]):
        frase.adicionar(p, float(i))
    assert frase.glosa() == "OI · BOM · DIA"
    assert frase.texto() == "Oi, bom dia!"
    frase.remover_ultima()
    assert frase.palavras == ["OI", "BOM"]
    frase.limpar()
    assert frase.palavras == [] and frase.texto() == ""


def test_pausa_encerra_a_frase():
    frase = Frase(FRASES, pausa_s=2.5)
    frase.adicionar("MEU", 10.0)
    frase.adicionar("NOME", 11.0)
    assert not frase.pausa_detectada(13.0)
    assert frase.pausa_detectada(13.6)
    assert frase.finalizar() == "Meu nome é"
    assert frase.palavras == [] and frase.ultima_frase == "Meu nome é"
    assert not frase.pausa_detectada(20.0)
    assert frase.finalizar() is None


def test_frase_cheia_e_encerrada_antes_da_nova_palavra():
    frase = Frase({}, max_palavras=2)
    assert frase.adicionar("EU", 0) is None
    assert frase.adicionar("SIM", 1) is None
    assert frase.adicionar("OI", 2) == "Eu sim"
    assert frase.palavras == ["OI"]
