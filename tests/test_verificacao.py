"""Verificação do ambiente (luz, câmera, ombros, distância, mãos)."""

import numpy as np

from libras.verificacao import VerificacaoAmbiente, brilho_medio, largura_ombros


def _itens(v):
    return {item.nome: item for item in v.resultado()}


def _pose(x_esquerdo, x_direito, y=0.5):
    pose = np.zeros((33, 3), dtype=np.float32)
    pose[11, :2], pose[12, :2] = (x_esquerdo, y), (x_direito, y)
    return pose


def test_ambiente_bom():
    v = VerificacaoAmbiente()
    for _ in range(40):
        v.adicionar(120, 28, largura_ombros(_pose(0.65, 0.35), 640, 480), True)
    assert v.tudo_ok and all(item.ok for item in v.resultado())


def test_problemas_viram_dicas():
    v = VerificacaoAmbiente()
    for _ in range(40):
        v.adicionar(40, 8, largura_ombros(_pose(0.55, 0.45), 640, 480), False)
    itens = _itens(v)
    assert not v.tudo_ok
    assert "Pouca luz" in itens["Luz"].texto and not itens["Câmera"].ok
    assert "Longe demais" in itens["Distância"].texto and itens["Mãos"].ok is None
    v = VerificacaoAmbiente()
    for _ in range(40):
        v.adicionar(240, 30, largura_ombros(_pose(0.9, 0.2), 640, 480), True)
    assert "clara demais" in _itens(v)["Luz"].texto and "Perto demais" in _itens(v)["Distância"].texto


def test_sem_ombros_e_sem_imagem():
    v = VerificacaoAmbiente()
    for _ in range(40):
        v.adicionar(120, 30, None, True)
    itens = _itens(v)
    assert not itens["Ombros"].ok and itens["Distância"].ok is None
    assert not VerificacaoAmbiente().tudo_ok


def test_brilho_medio():
    assert brilho_medio(np.full((48, 64, 3), 200, dtype=np.uint8)) == np.float32(200).item()
    assert brilho_medio(np.zeros((48, 64, 3), dtype=np.uint8)) == 0
