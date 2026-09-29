"""Treino de ponta a ponta com um dataset sintético pequeno."""

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest

from libras import config, dataset
from sinteticos import amostra

_spec = importlib.util.spec_from_file_location(
    "treinar_modelo", Path(__file__).parents[1] / "scripts" / "desenvolvimento" / "treinar_modelo.py")
treinar_modelo = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(treinar_modelo)


def _popular():
    trajetorias = {"OI": ((0.6, 0.75), (0.6, 0.45)), "SIM": ((0.5, 0.6), (0.8, 0.6)),
                   "_NADA": ((0.6, 0.9), (0.6, 0.9))}
    for sinal, (ini, fim) in trajetorias.items():
        for i in range(12):
            dataset.salvar_amostra(amostra(ini, fim, ruido=0.02, semente=i), sinal, ["ana", "bia"][i % 2])


def _treinar(monkeypatch, *args):
    monkeypatch.setattr(sys, "argv", ["treinar_modelo.py", "--sem-grafico", *args])
    return treinar_modelo.main()


def test_treino_completo_e_reprodutivel(dataset_vazio, monkeypatch):
    _popular()
    assert _treinar(monkeypatch, "--modelo", "rf") == 0
    info = json.loads(config.ARQ_MODELO_INFO.read_text(encoding="utf-8"))
    assert info["algoritmo"] == "rf" and info["random_state"] == config.SEMENTE
    assert info["classes"] == ["OI", "SIM", "_NADA"]
    assert info["amostras"] == {"total": 36, "treino": 27, "teste": 9,
                                "por_classe": {"OI": 12, "SIM": 12, "_NADA": 12}}
    assert set(info["teste_pessoas_novas"]) == {"ana", "bia"}
    assert 0.0 <= info["metricas_teste"]["accuracy"] <= 1.0
    assert (config.DIR_REPORTS / "classification_report.txt").is_file()
    assert config.ARQ_MODELO.is_file() and config.ARQ_CLASSES.is_file()

    primeiro = info["metricas_teste"]
    assert _treinar(monkeypatch, "--modelo", "rf") == 0
    assert json.loads(config.ARQ_MODELO_INFO.read_text(encoding="utf-8"))["metricas_teste"] == primeiro


def test_escolha_automatica_compara_os_tres(dataset_vazio, monkeypatch):
    _popular()
    assert _treinar(monkeypatch) == 0
    info = json.loads(config.ARQ_MODELO_INFO.read_text(encoding="utf-8"))
    assert set(info["comparacao_cv"]) == {"rf", "svm", "mlp"}
    melhor = max(info["comparacao_cv"], key=lambda n: info["comparacao_cv"][n]["f1_macro_media"])
    assert info["algoritmo"] == melhor


def test_sem_dados_retorna_erro(dataset_vazio, monkeypatch):
    assert _treinar(monkeypatch) == 1


def test_sinais_confundidos_ordenados():
    matriz = np.array([[8, 2, 0], [1, 9, 0], [0, 0, 5]])
    pares = treinar_modelo.sinais_confundidos(matriz, ["EU", "MEU", "OI"])
    assert [(p["real"], p["previsto"], p["vezes"]) for p in pares] == [("EU", "MEU", 2), ("MEU", "EU", 1)]
    assert pares[0]["pct_do_real"] == pytest.approx(0.2)
