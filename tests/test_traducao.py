"""Tabela de frases (frases.txt): leitura, avisos e conversão."""

from libras import config
from libras.traducao import TabelaFrases

EXEMPLO = """
# comentário
OI        = Oi!
BOM DIA   = Bom dia!
BOM       = Bom
EU NOME   = Meu nome é      # comentário no fim da linha
OBRIGADO  = Obrigado!
não       = Não.
"""


def _tabela():
    return TabelaFrases.de_texto(EXEMPLO)


def test_leitura_ignora_comentarios_e_normaliza_sinais():
    tabela = _tabela()
    assert tabela.avisos == []
    assert len(tabela) == 6
    assert tabela.frases[("EU", "NOME")] == "Meu nome é"
    assert tabela.frases[("NAO",)] == "Não."          # "não" -> identificador NAO


def test_frase_mais_longa_ganha():
    assert _tabela().traduzir(["BOM", "DIA"]).texto == "Bom dia!"
    assert _tabela().traduzir(["BOM"]).texto == "Bom"


def test_varias_frases_e_maiusculas():
    resultado = _tabela().traduzir(["OI", "BOM", "DIA", "EU", "NOME"])
    assert resultado.texto == "Oi! Bom dia! Meu nome é"
    assert resultado.glosa == "OI BOM DIA EU NOME"
    assert resultado.completa
    # no meio de uma frase (sem pontuação antes), a frase seguinte começa com minúscula
    assert _tabela().traduzir(["EU", "NOME", "OBRIGADO"]).texto == "Meu nome é obrigado!"


def test_trechos_sem_frase_ficam_como_glosa():
    resultado = _tabela().traduzir(["AJUDA", "EU", "NOME", "NAO", "SIM"])
    assert resultado.texto == "AJUDA Meu nome é não. SIM"   # maiúscula depois da glosa
    assert resultado.convertida and not resultado.completa
    assert [p.texto for p in resultado.partes] == [None, "Meu nome é", "Não.", None]
    assert TabelaFrases().traduzir(["AJUDA"]).texto == "AJUDA"


def test_tabela_vazia_devolve_a_glosa():
    resultado = TabelaFrases().traduzir(["EU", "NAO"])
    assert resultado.texto == resultado.glosa == "EU NÃO"
    assert not resultado.convertida
    assert TabelaFrases().traduzir([]).texto == ""


def test_avisos_com_numero_da_linha():
    tabela = TabelaFrases.de_texto("OI Oi!\n= sem sinais\nOI =\nOBRIGADA = Obrigada!\n"
                                   f"{config.CLASSE_NADA} = nada\nSIM = Sim.\nSIM = Sim!\n")
    texto = "\n".join(tabela.avisos)
    assert "linha 1: falta o '='" in texto
    assert "linha 2: falta os sinais" in texto
    assert "linha 3: falta o texto" in texto
    assert "linha 4: sinal desconhecido OBRIGADA" in texto
    assert f"linha 5: {config.CLASSE_NADA}" in texto
    assert "linha 7: 'SIM' repetida" in texto
    assert tabela.frases[("SIM",)] == "Sim!"


def test_ler_arquivo_utf8_ansi_e_ausente(tmp_path):
    utf8 = tmp_path / "utf8.txt"
    utf8.write_text("NAO = Não.\n", encoding="utf-8-sig")        # com BOM (Bloco de Notas)
    assert TabelaFrases.ler(utf8).frases[("NAO",)] == "Não."
    ansi = tmp_path / "ansi.txt"
    ansi.write_bytes("NAO = Não.\n".encode("cp1252"))            # Bloco de Notas antigo
    assert TabelaFrases.ler(ansi).frases[("NAO",)] == "Não."
    ausente = TabelaFrases.ler(tmp_path / "nao_existe.txt")
    assert len(ausente) == 0 and "não encontrado" in ausente.avisos[0]


def test_frases_txt_do_projeto_e_valido():
    tabela = TabelaFrases.ler(config.ARQ_FRASES)
    assert tabela.avisos == [], tabela.avisos
    assert len(tabela) > 0


def test_letras_seguidas_viram_palavra_soletrada():
    tabela = TabelaFrases.de_texto("MEU NOME = Meu nome é\nOBRIGADO = Obrigado!")
    resultado = tabela.traduzir(["MEU", "NOME", "C", "A", "U", "A"])
    assert resultado.texto == "Meu nome é Caua"
    assert resultado.glosa == "MEU NOME C-A-U-A"
    assert resultado.completa and resultado.partes[-1].soletrada
    # sem tabela também soletra; Ç aparece com cedilha; nome próprio sempre com maiúscula
    assert TabelaFrases().traduzir(["EU", "C_CEDILHA", "A"]).texto == "EU Ça"
    assert tabela.traduzir(["OBRIGADO", "A", "N", "A"]).texto == "Obrigado! Ana"
    assert tabela.traduzir(["A", "N", "A", "OBRIGADO"]).texto == "Ana obrigado!"


def test_letra_na_tabela_gera_aviso():
    tabela = TabelaFrases.de_texto("A = Letra A")  # letras são soletradas sozinhas, não pela tabela
    assert any("sinal desconhecido A" in a for a in tabela.avisos)
