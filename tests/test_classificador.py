import json

import numpy as np
import pytest
from sklearn.ensemble import RandomForestClassifier
from sklearn.pipeline import Pipeline

from libras import config
from libras.classificador import ErroClassificador, carregar_classificador, salvar_classificador


def _modelo_treinado():
    rng = np.random.default_rng(0)
    X = rng.normal(size=(40, config.TAM_FEATURES_JANELA)).astype(np.float32)
    y = np.array(["OI", "SIM"] * 20)
    X[y == "SIM", :10] += 5
    return Pipeline([("modelo", RandomForestClassifier(n_estimators=20, n_jobs=-1, random_state=0))]).fit(X, y), X


def test_salvar_e_carregar(dataset_vazio):
    modelo, X = _modelo_treinado()
    salvar_classificador(modelo, {"algoritmo": "rf"})
    assert json.loads(config.ARQ_CLASSES.read_text(encoding="utf-8")) == ["OI", "SIM"]

    with pytest.warns(UserWarning, match="não conhece os sinais"):
        classificador = carregar_classificador()
    sinal, confianca = classificador.prever(X[1])
    assert sinal == "SIM" and 0.5 < confianca <= 1.0
    assert set(classificador.probabilidades(X[0])) == {"OI", "SIM"}
    assert classificador.modelo.named_steps["modelo"].n_jobs == 1  # rápido para 1 previsão
    assert classificador.info["tam_features"] == config.TAM_FEATURES_JANELA


def test_modelo_ausente(dataset_vazio):
    with pytest.raises(ErroClassificador, match="treinar_modelo"):
        carregar_classificador()


def test_modelo_com_features_diferentes_e_recusado(dataset_vazio, monkeypatch):
    salvar_classificador(_modelo_treinado()[0], {})
    monkeypatch.setattr(config, "T_FRAMES", config.T_FRAMES + 5)
    with pytest.raises(ErroClassificador, match="outras features"):
        carregar_classificador()
