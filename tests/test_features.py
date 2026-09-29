import numpy as np
import pytest

from libras import config
from libras.features import (ErroJanela, forma_mao, indices_reamostragem, janela_para_vetor,
                             preencher_lacunas_maos)
from sinteticos import MAO_BASE, amostra, linha, mao, transformar


def test_versao_1_e_o_inicio_da_versao_2():
    frames = amostra(esquerda=True)
    v1, v2 = janela_para_vetor(frames, versao=1), janela_para_vetor(frames, versao=2)
    assert v1.shape == (config.TAM_FEATURES_POSICIONAIS,)
    assert v2.shape == (config.TAM_FEATURES_POSICIONAIS + config.TAM_MOVIMENTO,)
    np.testing.assert_array_equal(v2[:v1.size], v1)


def test_versao_desconhecida_gera_erro():
    with pytest.raises(ValueError):
        janela_para_vetor(amostra(), versao=99)


def test_vetor_tem_sempre_o_mesmo_tamanho():
    for n_frames in (20, 45, 90):  # câmeras de ~13, 30 e 60 fps
        assert janela_para_vetor(amostra(n_frames=n_frames)).shape == (config.TAM_FEATURES_JANELA,)


def test_invariante_a_posicao_da_pessoa_na_imagem():
    base = amostra(esquerda=True)
    movida = transformar(base, deslocamento=(-0.3, 0.1))
    np.testing.assert_allclose(janela_para_vetor(base), janela_para_vetor(movida), atol=1e-5)


def test_invariante_a_distancia_da_camera():
    base = amostra(esquerda=True)
    longe = transformar(base, escala=0.5)  # pessoa com metade do tamanho na imagem
    np.testing.assert_allclose(janela_para_vetor(base), janela_para_vetor(longe), atol=1e-5)


def test_forma_invariante_ao_tamanho_da_mao():
    np.testing.assert_allclose(forma_mao(mao((0.5, 0.5), 0.05)), forma_mao(mao((0.2, 0.9), 0.12)), atol=1e-5)


def test_vetor_invariante_ao_tamanho_da_mao():
    pequena = amostra(tamanho=0.06)
    grande = amostra(tamanho=0.11)
    np.testing.assert_allclose(janela_para_vetor(pequena), janela_para_vetor(grande), atol=1e-5)


def test_local_do_sinal_em_relacao_ao_corpo_importa():
    peito = amostra(inicio=(0.70, 0.75), fim=(0.70, 0.75))
    testa = amostra(inicio=(0.70, 0.30), fim=(0.70, 0.30))
    assert not np.allclose(janela_para_vetor(peito), janela_para_vetor(testa))


def test_formato_da_mao_importa():
    fechada = MAO_BASE * np.array([0.3, 0.3, 1.0], dtype=np.float32)
    fechada[config.MAO_BASE_DEDO_MEDIO] = MAO_BASE[config.MAO_BASE_DEDO_MEDIO]
    assert not np.allclose(forma_mao(mao((0.5, 0.5), forma=MAO_BASE)), forma_mao(mao((0.5, 0.5), forma=fechada)))


def test_mao_ausente_vira_zeros_com_flag_zero():
    vetor = janela_para_vetor(amostra(esquerda=False), versao=1).reshape(config.T_FRAMES, config.TAM_FEATURES_FRAME)
    bloco = config.TAM_FORMA_MAO + config.TAM_POSICAO_MAO
    assert vetor[:, :bloco].any()                       # direita presente
    assert not vetor[:, bloco:2 * bloco].any()          # esquerda = zeros
    np.testing.assert_array_equal(vetor[:, -2:], np.tile([1.0, 0.0], (config.T_FRAMES, 1)))


def test_lacuna_curta_e_interpolada_e_longa_nao():
    frames = amostra(n_frames=30)
    flag = config.COL_FLAGS.start
    curta, longa = frames.copy(), frames.copy()
    curta[10:12, config.COL_MAO_DIREITA] = 0
    curta[10:12, flag] = 0
    longa[10:20, config.COL_MAO_DIREITA] = 0
    longa[10:20, flag] = 0
    assert (preencher_lacunas_maos(curta)[:, flag] == 1).all()
    np.testing.assert_allclose(preencher_lacunas_maos(curta)[10:12], frames[10:12], atol=1e-5)
    assert (preencher_lacunas_maos(longa)[10:20, flag] == 0).all()


def test_frames_sem_ombros_usam_o_frame_mais_proximo():
    frames = amostra()
    sem_pose = frames.copy()
    sem_pose[5:10, config.COL_POSE] = 0
    np.testing.assert_allclose(janela_para_vetor(frames), janela_para_vetor(sem_pose), atol=1e-5)


def test_sem_ombros_em_nenhum_frame_gera_erro():
    frames = np.stack([linha(t, direita=mao((0.6, 0.6)), ombros=None) for t in np.linspace(0, 1.5, 30)])
    with pytest.raises(ErroJanela, match="ombros"):
        janela_para_vetor(frames)


def test_formato_invalido_gera_erro():
    with pytest.raises(ErroJanela):
        janela_para_vetor(np.zeros((10, 5)))
    with pytest.raises(ErroJanela):
        janela_para_vetor(amostra()[:1])


def test_reamostragem_uniforme_no_tempo():
    tempos = np.array([0.0, 0.1, 0.2, 0.9, 1.0])
    np.testing.assert_array_equal(indices_reamostragem(tempos, 3), [0, 2, 4])


def test_duas_maos_preenchem_os_dois_blocos():
    vetor = janela_para_vetor(amostra(esquerda=True), versao=1).reshape(config.T_FRAMES, config.TAM_FEATURES_FRAME)
    bloco = config.TAM_FORMA_MAO + config.TAM_POSICAO_MAO
    assert vetor[:, :bloco].any() and vetor[:, bloco:2 * bloco].any()
    np.testing.assert_array_equal(vetor[:, -2:], np.ones((config.T_FRAMES, 2)))


def test_so_a_mao_esquerda():
    frames = np.stack([linha(t, esquerda=mao((0.8, 0.6))) for t in np.linspace(0, 1.5, 45)])
    vetor = janela_para_vetor(frames, versao=1).reshape(config.T_FRAMES, config.TAM_FEATURES_FRAME)
    bloco = config.TAM_FORMA_MAO + config.TAM_POSICAO_MAO
    assert not vetor[:, :bloco].any() and vetor[:, bloco:2 * bloco].any()
    np.testing.assert_array_equal(vetor[:, -2:], np.tile([0.0, 1.0], (config.T_FRAMES, 1)))


def test_sem_nenhuma_mao_o_vetor_existe_e_e_zero_nas_maos():
    frames = np.stack([linha(t) for t in np.linspace(0, 1.5, 45)])
    vetor = janela_para_vetor(frames)
    assert vetor.shape == (config.TAM_FEATURES_JANELA,) and not vetor.any()


def test_coleta_e_tempo_real_geram_o_mesmo_vetor(dataset_vazio):
    """A amostra gravada pelo coletor e a mesma sequência vista no tempo real
    (buffer com timestamps absolutos) precisam gerar exatamente o mesmo vetor."""
    from libras import dataset
    from libras.features import BufferJanela

    frames = amostra(esquerda=True, ruido=0.02)
    frames[:, config.COL_TIMESTAMP] += 1000.0          # tempo real: relógio absoluto
    buffer = BufferJanela(duracao=10.0, duracao_minima=1.0)
    for l in frames:
        buffer.adicionar(l)
    gravada = frames.copy()
    gravada[:, config.COL_TIMESTAMP] -= gravada[0, config.COL_TIMESTAMP]   # como o coletor salva
    caminho = dataset.salvar_amostra(gravada, "OI", "ana")
    np.testing.assert_allclose(buffer.vetor(), janela_para_vetor(np.load(caminho)), atol=1e-5)
