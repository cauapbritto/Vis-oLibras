"""Salva e carrega o modelo treinado; prevê (sinal, confiança) para uma janela.

Arquivos em models/:
    classificador.joblib     o Pipeline do scikit-learn
    classes.json             os rótulos, na ordem das saídas do modelo
    classificador_info.json  configurações do treino, métricas e parâmetros das features

Ao carregar, conferimos se o modelo foi treinado com as MESMAS features do
config.py atual (versão, T_FRAMES, tamanho do vetor). Se não, é preciso retreinar.

Uso no tempo real:

    classificador = carregar_classificador()
    sinal, confianca = classificador.prever(features.janela_para_vetor(frames))
"""

from __future__ import annotations

import json
import warnings
from dataclasses import dataclass
from typing import Any

import joblib
import numpy as np

from libras import config


class ErroClassificador(RuntimeError):
    """Modelo ausente, corrompido ou incompatível com o config.py atual."""


@dataclass
class Classificador:
    modelo: Any           # Pipeline do scikit-learn com predict_proba
    info: dict[str, Any]

    @property
    def classes(self) -> list[str]:
        return [str(c) for c in self.modelo.classes_]

    def probabilidades(self, vetor: np.ndarray) -> dict[str, float]:
        """Probabilidade de cada classe para um vetor de features."""
        proba = self.modelo.predict_proba(np.asarray(vetor, dtype=np.float32).reshape(1, -1))[0]
        return dict(zip(self.classes, proba.tolist()))

    def prever(self, vetor: np.ndarray) -> tuple[str, float]:
        """(sinal mais provável, confiança de 0 a 1)."""
        proba = self.modelo.predict_proba(np.asarray(vetor, dtype=np.float32).reshape(1, -1))[0]
        indice = int(np.argmax(proba))
        return self.classes[indice], float(proba[indice])


def ajustar_para_tempo_real(modelo: Any) -> Any:
    """Usa 1 núcleo nas previsões: paralelizar UMA previsão (n_jobs=-1) custa mais
    caro que ela mesma (~150 ms contra ~10 ms no Random Forest)."""
    for _, etapa in getattr(modelo, "steps", []):
        if "n_jobs" in etapa.get_params():
            etapa.set_params(n_jobs=1)
    return modelo


def salvar_classificador(modelo: Any, info: dict[str, Any]) -> None:
    config.DIR_MODELOS.mkdir(parents=True, exist_ok=True)
    ajustar_para_tempo_real(modelo)
    classes = [str(c) for c in modelo.classes_]
    info = {**info, "classes": classes, "versao_features": config.VERSAO_FEATURES,
            "t_frames": config.T_FRAMES, "tam_features": config.TAM_FEATURES_JANELA,
            "duracao_janela": config.DURACAO_JANELA}
    joblib.dump(modelo, config.ARQ_MODELO)
    config.ARQ_CLASSES.write_text(json.dumps(classes, ensure_ascii=False, indent=2), encoding="utf-8")
    config.ARQ_MODELO_INFO.write_text(
        json.dumps(info, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def carregar_classificador() -> Classificador:
    for arquivo in (config.ARQ_MODELO, config.ARQ_MODELO_INFO, config.ARQ_CLASSES):
        if not arquivo.is_file():
            raise ErroClassificador(f"{arquivo} não existe; treine com scripts/treinar_modelo.py")
    try:
        modelo = joblib.load(config.ARQ_MODELO)
        info = json.loads(config.ARQ_MODELO_INFO.read_text(encoding="utf-8"))
        classes = json.loads(config.ARQ_CLASSES.read_text(encoding="utf-8"))
    except Exception as erro:  # arquivo corrompido ou de outra versão do scikit-learn
        raise ErroClassificador(f"não foi possível carregar o modelo ({erro}); treine novamente") from erro

    esperado = {"versao_features": config.VERSAO_FEATURES, "t_frames": config.T_FRAMES,
                "tam_features": config.TAM_FEATURES_JANELA}
    diferencas = [f"{k}: modelo={info.get(k)}, config={v}" for k, v in esperado.items() if info.get(k) != v]
    if diferencas:
        raise ErroClassificador("o modelo foi treinado com outras features ("
                                + "; ".join(diferencas) + "); treine novamente")
    if [str(c) for c in modelo.classes_] != classes:
        raise ErroClassificador("classes.json não corresponde ao modelo; treine novamente")
    if not hasattr(modelo, "predict_proba"):
        raise ErroClassificador("o modelo não fornece probabilidades (predict_proba)")

    faltando = sorted(set(config.CLASSES) - set(classes))
    if faltando:
        warnings.warn(f"o modelo não conhece os sinais {faltando}; grave amostras e treine novamente",
                      stacklevel=2)
    return Classificador(ajustar_para_tempo_real(modelo), info)
