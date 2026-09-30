import numpy as np
import pytest

from libras import config, dataset
from sinteticos import amostra, linha, mao


def test_amostra_valida():
    assert dataset.validar_amostra(amostra(), "OI") == []


def test_amostra_com_poucos_frames():
    assert "poucos frames" in dataset.validar_amostra(amostra(n_frames=8), "OI")[0]


def test_amostra_sem_maos_invalida_para_sinal_mas_valida_para_nada():
    sem_maos = np.stack([linha(t) for t in np.linspace(0, 1.5, 45)])
    assert any("mãos" in p for p in dataset.validar_amostra(sem_maos, "OI"))
    assert dataset.validar_amostra(sem_maos, config.CLASSE_NADA) == []


def test_amostra_sem_ombros_invalida():
    frames = np.stack([linha(t, direita=mao((0.6, 0.6)), ombros=None) for t in np.linspace(0, 1.5, 45)])
    assert any("ombros" in p for p in dataset.validar_amostra(frames, "OI"))


def test_amostra_curta_invalida():
    assert any("duração" in p for p in dataset.validar_amostra(amostra(duracao=0.5), "OI"))


def test_validar_pessoa():
    assert dataset.validar_pessoa("Ana") == "ana"
    assert dataset.validar_pessoa("joão") == "joao"
    with pytest.raises(ValueError):
        dataset.validar_pessoa("ana maria")


def test_salvar_contar_e_remover(dataset_vazio):
    caminho = dataset.salvar_amostra(amostra(), "OI", "ana")
    dataset.salvar_amostra(amostra(semente=1), "OI", "bia")
    assert caminho.parent == dataset_vazio / "raw" / "OI"
    assert dataset.contar_amostras("OI") == 2
    assert dataset.contar_amostras("OI", "ana") == 1
    metadata = dataset.carregar_metadata()
    assert [l["pessoa"] for l in metadata] == ["ana", "bia"]
    assert metadata[0]["arquivo"] == "raw/OI/" + caminho.name

    dataset.remover_amostra(caminho)
    assert not caminho.exists()
    assert dataset.contar_amostras("OI") == 1
    assert [l["pessoa"] for l in dataset.carregar_metadata()] == ["bia"]


def _popular(n=8):
    """Dois sinais com movimentos diferentes, duas pessoas."""
    for i in range(n):
        pessoa = "ana" if i % 2 else "bia"
        dataset.salvar_amostra(amostra((0.6, 0.75), (0.6, 0.45), ruido=0.01, semente=i), "OI", pessoa)
        dataset.salvar_amostra(amostra((0.5, 0.60), (0.8, 0.60), ruido=0.01, semente=100 + i), "SIM", pessoa)


def test_analise_de_dataset_consistente(dataset_vazio):
    _popular()
    rel = dataset.analisar_dataset()
    assert rel.contagem("OI") == 8 and rel.contagem("SIM") == 8
    assert rel.tamanhos_vetor == {config.TAM_FEATURES_JANELA}
    assert rel.invalidas() == []
    assert rel.inconsistencias == []
    assert rel.pessoas("OI") == {"ana": 4, "bia": 4}
    # as amostras sintéticas usam a coluna "Right"; com os rótulos do MediaPipe
    # invertidos, essa é a mão esquerda da pessoa
    assert rel.perfis("OI") == {"esquerda" if config.NOMES_MAOS_INVERTIDOS else "direita": 8}
    assert "OI" in rel.classes_com_poucas_amostras()  # 8 < mínimo
    classes, matriz = rel.similaridade
    assert classes == ["OI", "SIM"] and matriz.shape == (2, 2)


def test_analise_encontra_problemas(dataset_vazio):
    _popular()
    raw = dataset_vazio / "raw"
    # amostra inválida (sem mãos) gravada direto, sem passar pelo coletor
    dataset.salvar_amostra(np.stack([linha(t) for t in np.linspace(0, 1.5, 45)]), "OI", "ana")
    # duplicata
    original = dataset.listar_amostras("SIM")[0]
    (raw / "SIM" / "ana_copia.npy").write_bytes(original.read_bytes())
    # pasta desconhecida, arquivo fora do metadata e linha órfã no metadata
    (raw / "CASA").mkdir()
    np.save(raw / "CASA" / "ana_1.npy", amostra())
    np.save(raw / "OI" / "ana_solta.npy", amostra())
    with open(config.ARQ_METADATA, "a", encoding="utf-8") as f:
        f.write("raw/OI/sumiu.npy,OI,ana,2026-01-01T00:00:00,45,30,1,1\n")
    # amostra de OI usando a mão esquerda também (perfil diferente) e em outro lugar (outlier)
    dataset.salvar_amostra(amostra((0.6, 0.2), (0.6, 0.1), esquerda=True), "OI", "ana")

    rel = dataset.analisar_dataset()
    problemas = {a.arquivo.split("/")[-1]: a.problemas for a in rel.invalidas()}
    assert any("duplicata" in p[0] for p in problemas.values())
    assert any("mãos" in " ".join(p) for p in problemas.values())
    texto = "\n".join(rel.inconsistencias)
    assert "CASA" in texto
    assert "ana_solta.npy não está no metadata" in texto
    assert "sumiu.npy, que não existe" in texto
    motivos = " ".join(m for _, m in rel.alertas)
    assert "ambas" in motivos
    assert "muito diferente" in motivos


def test_construir_salvar_e_carregar_dados_treino(dataset_vazio):
    _popular(4)
    dataset.salvar_amostra(np.stack([linha(t) for t in np.linspace(0, 1.5, 45)]), "OI", "ana")  # inválida
    dados, invalidas = dataset.construir_dados_treino()
    assert dados.X.shape == (8, config.TAM_FEATURES_JANELA)
    assert len(invalidas) == 1
    dataset.salvar_dados_treino(dados)
    carregados = dataset.carregar_dados_treino()
    np.testing.assert_array_equal(carregados.X, dados.X)
    assert list(carregados.y) == list(dados.y)
    assert set(carregados.pessoas) == {"ana", "bia"}


def test_gravacao_nova_depois_do_treino_reconstroi_o_dataset(dataset_vazio):
    """Gravou letras, treinou, gravou SIM: o próximo treino precisa ver o SIM."""
    import os
    _popular(4)
    dataset.salvar_dados_treino(dataset.construir_dados_treino()[0])
    antigo = config.ARQ_DATASET.stat().st_mtime - 60
    for caminho in [config.DIR_RAW, *config.DIR_RAW.iterdir(), *config.DIR_RAW.glob("*/*.npy")]:
        os.utime(caminho, (antigo, antigo))
    assert not dataset.precisa_reconstruir()
    dataset.salvar_amostra(amostra((0.5, 0.60), (0.8, 0.60), ruido=0.01, semente=999), "NAO", "ana")
    assert dataset.precisa_reconstruir()


def test_dados_treino_de_outra_versao_sao_recusados(dataset_vazio, monkeypatch):
    _popular(4)
    dataset.salvar_dados_treino(dataset.construir_dados_treino()[0])
    monkeypatch.setattr(config, "VERSAO_FEATURES", config.VERSAO_FEATURES + 1)
    with pytest.raises(dataset.ErroDataset, match="construir_dataset"):
        dataset.carregar_dados_treino()


def test_validar_dados_treino():
    X = np.zeros((3, config.TAM_FEATURES_JANELA), dtype=np.float32)
    dados = dataset.DadosTreino(X, np.array(["OI", "OI", "CASA"]), np.array(["a"] * 3), np.array(["x"] * 3))
    problemas = " ".join(dataset.validar_dados_treino(dados))
    assert "CASA" in problemas and "menos de 2 amostras" in problemas
    X[0, 0] = np.nan
    assert any("NaN" in p for p in dataset.validar_dados_treino(dados))


def test_sem_amostras_validas(dataset_vazio):
    with pytest.raises(dataset.ErroDataset, match="nenhuma amostra"):
        dataset.construir_dados_treino()


def test_juntar_gravacoes_e_reconstruir_metadata(dataset_vazio):
    """Simula o metadata.csv de uma pessoa sobrescrito pelo de outra ao juntar zips."""
    _popular(4)
    antes = dataset.carregar_metadata()
    config.ARQ_METADATA.write_text(",".join(dataset.COLUNAS_METADATA) + "\n", encoding="utf-8")  # índice perdido
    assert any("não está no metadata" in i for i in dataset.analisar_dataset().inconsistencias)
    assert dataset.reconstruir_metadata() == len(antes)
    depois = dataset.carregar_metadata()
    assert sorted(l["arquivo"] for l in depois) == sorted(l["arquivo"] for l in antes)
    assert {l["pessoa"] for l in depois} == {"ana", "bia"} and all(l["data_hora"] for l in depois)
    assert dataset.analisar_dataset().inconsistencias == []


def test_letras_sao_opcionais_na_analise(dataset_vazio):
    _popular(4)
    rel = dataset.analisar_dataset()
    assert "A" not in rel.classes_em_uso()              # letra sem gravação: nem aparece
    assert "A" not in rel.classes_com_poucas_amostras()
    dataset.salvar_amostra(amostra(semente=7), "A", "ana")
    rel = dataset.analisar_dataset()
    assert "A" in rel.classes_em_uso() and "A" in rel.classes_com_poucas_amostras()
