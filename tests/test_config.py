"""Testes da configuração: garantem que a fundação do projeto está coerente."""

from libras import config


def test_caminhos_sao_relativos_a_raiz_do_projeto():
    for caminho in (config.DIR_RAW, config.ARQ_DATASET, config.ARQ_MODELO, config.DIR_REPORTS):
        assert caminho.is_relative_to(config.RAIZ_PROJETO)


def test_raiz_do_projeto_correta():
    assert (config.RAIZ_PROJETO / "src" / "libras" / "config.py").is_file()


def test_classes_incluem_nada_e_nao_repetem():
    assert config.CLASSE_NADA in config.CLASSES
    assert len(config.CLASSES) == len(set(config.CLASSES))


def test_identificadores_sem_acento():
    # Os identificadores viram nomes de pasta; acentos quebram entre sistemas.
    for classe in config.CLASSES:
        assert classe.isascii()


def test_existe_pasta_de_dados_para_cada_classe():
    for classe in config.CLASSES:
        assert (config.DIR_RAW / classe).is_dir()


def test_layout_dos_landmarks():
    assert config.TAM_FRAME_BRUTO == 228
    assert config.COL_POSE.stop == config.TAM_FRAME_BRUTO
    assert config.TAM_FEATURES_FRAME == 132
    assert config.TAM_FEATURES_POSICIONAIS == config.T_FRAMES * 132
    assert config.TAM_FEATURES_JANELA == config.TAM_FEATURES_POSICIONAIS + config.TAM_MOVIMENTO


def test_limiares_validos():
    assert 0 < config.LIMIAR_CONFIANCA <= 1
    assert config.DURACAO_MINIMA_JANELA <= config.DURACAO_JANELA
    assert config.N_CONSECUTIVAS >= 1


def test_rotulo_exibicao():
    assert config.rotulo_exibicao("NAO") == "NÃO"
    assert config.rotulo_exibicao("OI") == "OI"


def test_identificador_sinal():
    assert config.identificador_sinal("não") == "NAO"
    assert config.identificador_sinal(" oi ") == "OI"
    assert config.identificador_sinal("_nada") == config.CLASSE_NADA
