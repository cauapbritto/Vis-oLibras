import sys
from pathlib import Path

import pytest

from libras import config

# Permite "from sinteticos import ..." nos testes
sys.path.insert(0, str(Path(__file__).parent))


@pytest.fixture
def dataset_vazio(tmp_path, monkeypatch):
    """Redireciona data/, models/ e reports/ para uma pasta temporária."""
    caminhos = {
        "DIR_DATA": tmp_path,
        "DIR_RAW": tmp_path / "raw",
        "DIR_PROCESSED": tmp_path / "processed",
        "ARQ_METADATA": tmp_path / "metadata.csv",
        "ARQ_DATASET": tmp_path / "processed" / "dataset.npz",
        "DIR_MODELOS": tmp_path / "models",
        "ARQ_MODELO": tmp_path / "models" / "classificador.joblib",
        "ARQ_MODELO_INFO": tmp_path / "models" / "classificador_info.json",
        "ARQ_CLASSES": tmp_path / "models" / "classes.json",
        "DIR_REPORTS": tmp_path / "reports",
    }
    for nome, caminho in caminhos.items():
        monkeypatch.setattr(config, nome, caminho)
    for classe in config.CLASSES:
        (tmp_path / "raw" / classe).mkdir(parents=True)
    return tmp_path
