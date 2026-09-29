import numpy as np
import pytest

from libras import config, dataset
from sinteticos import amostra, linha, mao


@pytest.fixture
def dataset_vazio(tmp_path, monkeypatch):
    """Redireciona data/ para uma pasta temporária."""
    monkeypatch.setattr(config, "DIR_DATA", tmp_path)
    monkeypatch.setattr(config, "DIR_RAW", tmp_path / "raw")
    monkeypatch.setattr(config, "ARQ_METADATA", tmp_path / "metadata.csv")
    for classe in config.CLASSES:
        (tmp_path / "raw" / classe).mkdir(parents=True)
    return tmp_path


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
    assert rel.perfis("OI") == {"direita": 8}
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
