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


def test_modelo_da_versao_1_continua_funcionando(dataset_vazio, monkeypatch):
    """Modelo treinado antes das features de movimento: o tempo real gera o vetor v1."""
    from sinteticos import amostra

    from libras.features import janela_para_vetor
    from libras.reconhecedor import Reconhecedor

    X = np.stack([janela_para_vetor(amostra(semente=i), versao=1) for i in range(6)]
                 + [janela_para_vetor(amostra((0.5, 0.6), (0.8, 0.6), semente=i), versao=1) for i in range(6)])
    y = ["OI"] * 6 + ["SIM"] * 6
    modelo = Pipeline([("modelo", RandomForestClassifier(n_estimators=20, random_state=0))]).fit(X, y)
    versao_atual, tamanho_atual = config.VERSAO_FEATURES, config.TAM_FEATURES_JANELA
    monkeypatch.setattr(config, "VERSAO_FEATURES", 1)
    monkeypatch.setattr(config, "TAM_FEATURES_JANELA", config.TAM_FEATURES_POSICIONAIS)
    salvar_classificador(modelo, {})
    monkeypatch.setattr(config, "VERSAO_FEATURES", versao_atual)  # volta para a versão atual
    monkeypatch.setattr(config, "TAM_FEATURES_JANELA", tamanho_atual)

    with pytest.warns(UserWarning):
        classificador = carregar_classificador()
    assert classificador.versao_features == 1
    reconhecedor = Reconhecedor(classificador, passo_inferencia=1)
    estado = None
    for l in amostra(n_frames=45):
        estado = reconhecedor.processar(l, float(l[config.COL_TIMESTAMP]))
    assert estado.sinal in {"OI", "SIM"}


def test_versao_de_features_desconhecida_e_recusada(dataset_vazio):
    salvar_classificador(_modelo_treinado()[0], {})
    info = json.loads(config.ARQ_MODELO_INFO.read_text(encoding="utf-8"))
    info["versao_features"] = 99
    config.ARQ_MODELO_INFO.write_text(json.dumps(info), encoding="utf-8")
    with pytest.raises(ErroClassificador, match="v99"):
        carregar_classificador()
