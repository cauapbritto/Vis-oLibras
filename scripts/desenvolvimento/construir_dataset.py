"""Converte data/raw/ em data/processed/dataset.npz (X, y, pessoa) (Fase 3).

Cada amostra válida vira uma linha de X com config.TAM_FEATURES_JANELA valores,
calculados por features.janela_para_vetor() - a mesma função do tempo real.
Amostras inválidas (as mesmas regras do coletor) são ignoradas e listadas.

Uso:
    python scripts/desenvolvimento/construir_dataset.py
"""

import argparse
import sys
from collections import Counter

from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))  # funciona sem "pip install -e ."

from libras import config, dataset


def main() -> int:
    argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter).parse_args()
    try:
        dados, invalidas = dataset.construir_dados_treino()
    except dataset.ErroDataset as erro:
        print(f"[ERRO] {erro}", file=sys.stderr)
        return 1
    dataset.salvar_dados_treino(dados)

    print(f"Dataset salvo em {config.ARQ_DATASET}")
    print(f"  X: {dados.X.shape[0]} amostras x {dados.X.shape[1]} features")
    print(f"  Pessoas: {', '.join(sorted(set(dados.pessoas)))}")
    contagem = Counter(dados.y)
    for classe in config.CLASSES:
        print(f"  {config.rotulo_exibicao(classe):<10} {contagem.get(classe, 0):>5}")
    if invalidas:
        print(f"  {len(invalidas)} amostras inválidas ignoradas (detalhes: scripts/desenvolvimento/analisar_dataset.py)")

    problemas = dataset.validar_dados_treino(dados)
    for problema in problemas:
        print(f"[AVISO] {problema}", file=sys.stderr)
    return 1 if problemas else 0


if __name__ == "__main__":
    sys.exit(main())
