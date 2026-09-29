"""Compara as versões de features no SEU dataset (não treina o modelo final).

Treina o mesmo algoritmo (Random Forest) com:
  v1 - janela posicional (forma + posição das mãos em cada frame)
  v2 - v1 + características de movimento (velocidade, trajetória, direção...)
e mostra accuracy, F1 macro e o F1 de cada sinal, lado a lado. Útil para
decidir se o movimento ajuda e para mostrar na apresentação.

Uso:
    python scripts/desenvolvimento/comparar_features.py
"""

import argparse
import sys
from collections import Counter

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict

from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))  # funciona sem "pip install -e ."

from libras import config, dataset
from libras.features import janela_para_vetor


def main() -> int:
    argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    validas = [a for a in dataset.ler_amostras() if a.valida]
    contagem = Counter(a.sinal for a in validas)
    if len(contagem) < 2 or min(contagem.values()) < 3:
        print("[ERRO] são necessárias pelo menos 2 classes com 3 amostras válidas cada", file=sys.stderr)
        return 1

    frames = [np.load(config.DIR_DATA / a.arquivo) for a in validas]
    y = np.array([a.sinal for a in validas])
    classes = [c for c in config.CLASSES if c in contagem]
    folds = StratifiedKFold(n_splits=min(config.N_FOLDS_CV, min(contagem.values())),
                            shuffle=True, random_state=config.SEMENTE)
    modelo = RandomForestClassifier(n_estimators=config.N_ARVORES, class_weight="balanced",
                                    n_jobs=-1, random_state=config.SEMENTE)

    print(f"{len(y)} amostras, {len(classes)} classes, validação cruzada com {folds.n_splits} folds\n")
    resultados = {}
    for versao in (1, 2):
        X = np.stack([janela_para_vetor(f, versao) for f in frames])
        previsto = cross_val_predict(modelo, X, y, cv=folds)
        resultados[versao] = {
            "features": X.shape[1],
            "accuracy": accuracy_score(y, previsto),
            "f1": f1_score(y, previsto, average="macro"),
            "por_classe": dict(zip(classes, f1_score(y, previsto, labels=classes, average=None))),
        }

    v1, v2 = resultados[1], resultados[2]
    print(f"{'':<12}{'v1 (posição)':>16}{'v2 (+ movimento)':>18}{'diferença':>12}")
    print(f"{'features':<12}{v1['features']:>16}{v2['features']:>18}")
    print(f"{'accuracy':<12}{v1['accuracy']:>16.1%}{v2['accuracy']:>18.1%}{v2['accuracy'] - v1['accuracy']:>+12.1%}")
    print(f"{'F1 macro':<12}{v1['f1']:>16.3f}{v2['f1']:>18.3f}{v2['f1'] - v1['f1']:>+12.3f}")
    print("\nF1 por sinal:")
    for classe in classes:
        a, b = v1["por_classe"][classe], v2["por_classe"][classe]
        marca = "  <- melhorou" if b - a >= 0.05 else "  <- piorou" if a - b >= 0.05 else ""
        print(f"  {config.rotulo_exibicao(classe):<10}{a:>16.3f}{b:>18.3f}{b - a:>+12.3f}{marca}")
    print(f"\nO projeto usa a versão {config.VERSAO_FEATURES} (config.VERSAO_FEATURES).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
