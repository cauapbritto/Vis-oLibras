"""Avalia o modelo SALVO nas gravações de data/raw (modo desenvolvimento).

O treino (treinar_modelo.py) já avalia o modelo no momento em que é criado.
Este script serve para medir o modelo pronto depois, por exemplo com as
gravações de uma pessoa nova, que o modelo nunca viu:

    python scripts/desenvolvimento/avaliar_modelo.py --pessoa dani
    python scripts/desenvolvimento/avaliar_modelo.py            # todas as amostras

Avaliar com amostras usadas no treino dá números otimistas (o modelo já as viu);
o script avisa quando isso acontece.

Saídas: reports/avaliacao_report.txt e reports/matriz_confusao_avaliacao.png
"""

import argparse
import sys
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))  # funciona sem "pip install -e ."

import numpy as np  # noqa: E402
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score  # noqa: E402

from libras import config, dataset  # noqa: E402
from libras.avaliacao import salvar_matriz_confusao, sinais_confundidos  # noqa: E402
from libras.classificador import ErroClassificador, carregar_classificador  # noqa: E402
from libras.features import janela_para_vetor  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pessoa", action="append", help="avalia só as amostras desta pessoa (pode repetir)")
    parser.add_argument("--sem-grafico", action="store_true", help="não gera a matriz de confusão em PNG")
    args = parser.parse_args()

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            classificador = carregar_classificador()
    except ErroClassificador as erro:
        print(f"[ERRO] {erro}", file=sys.stderr)
        return 1

    conhecidas = set(classificador.classes)
    amostras = [a for a in dataset.ler_amostras() if a.valida and a.sinal in conhecidas
                and (not args.pessoa or a.pessoa in args.pessoa)]
    if not amostras:
        print("[ERRO] nenhuma amostra válida para avaliar (confira --pessoa e data/raw)", file=sys.stderr)
        return 1

    X = np.stack([janela_para_vetor(np.load(config.DIR_DATA / a.arquivo), classificador.versao_features)
                  for a in amostras])
    y = np.array([a.sinal for a in amostras])
    previsto = classificador.modelo.predict(X)
    classes = [c for c in classificador.classes if c in set(y)]
    rotulos = [config.rotulo_exibicao(c) for c in classes]

    linhas = [
        "=" * 64, "AVALIAÇÃO DO MODELO SALVO", "=" * 64,
        f"Modelo: {classificador.info.get('descricao')} (criado em {classificador.info.get('criado_em')}, "
        f"features v{classificador.versao_features})",
        f"Amostras avaliadas: {len(y)} | pessoas: {', '.join(sorted({a.pessoa for a in amostras}))}",
    ]
    vistas = sorted({a.pessoa for a in amostras} & set(classificador.info.get("pessoas", [])))
    if vistas:
        linhas.append(f"[AVISO] {', '.join(vistas)} participou(aram) do treino: resultado otimista. "
                      "Para medir de verdade, avalie com uma pessoa nova (--pessoa).")
    linhas += [
        "",
        f"Accuracy : {accuracy_score(y, previsto):.1%}  ({int((previsto == y).sum())} de {len(y)} acertos)",
        f"F1 macro : {f1_score(y, previsto, average='macro', zero_division=0):.3f}",
        "",
        classification_report(y, previsto, labels=classes, target_names=rotulos, digits=3, zero_division=0),
        "SINAIS CONFUNDIDOS (real -> previsto)",
    ]
    matriz = confusion_matrix(y, previsto, labels=classes)
    confusoes = sinais_confundidos(matriz, classes)
    linhas += [f"  {config.rotulo_exibicao(c['real'])} -> {config.rotulo_exibicao(c['previsto'])}: "
               f"{c['vezes']}x ({c['pct_do_real']:.0%})" for c in confusoes[:10]] or ["  nenhuma"]

    texto = "\n".join(linhas)
    print(texto)
    config.DIR_REPORTS.mkdir(parents=True, exist_ok=True)
    (config.DIR_REPORTS / "avaliacao_report.txt").write_text(texto, encoding="utf-8")
    if not args.sem_grafico:
        caminho = salvar_matriz_confusao(matriz, classes, f"Avaliação do modelo salvo ({len(y)} amostras)",
                                         "matriz_confusao_avaliacao.png")
        print(f"\nMatriz de confusão em {caminho}")
    print(f"Relatório em {config.DIR_REPORTS / 'avaliacao_report.txt'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
