"""Avaliação de modelos (modo desenvolvimento): confusões e matriz de confusão.

Usado por treinar_modelo.py e avaliar_modelo.py. Não é carregado pela aplicação.
"""

from __future__ import annotations

import numpy as np

from libras import config

# Paleta validada (modo claro), a mesma do analisar_dataset.py
SUPERFICIE, TEXTO, TEXTO_SECUNDARIO = "#fcfcfb", "#0b0b0b", "#52514e"
RAMPA_SEQUENCIAL = ["#f4f8fe", "#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]


def sinais_confundidos(matriz: np.ndarray, classes: list[str]) -> list[dict]:
    """Pares (real -> previsto) fora da diagonal, do mais frequente ao menos."""
    pares = []
    for i, real in enumerate(classes):
        total = int(matriz[i].sum())
        for j, previsto in enumerate(classes):
            if i != j and matriz[i, j] > 0:
                pares.append({"real": real, "previsto": previsto, "vezes": int(matriz[i, j]),
                              "pct_do_real": matriz[i, j] / total})
    return sorted(pares, key=lambda p: (-p["vezes"], -p["pct_do_real"]))


def salvar_matriz_confusao(matriz: np.ndarray, classes: list[str], titulo: str,
                           nome_arquivo: str = "matriz_confusao.png",
                           colunas: list[str] | None = None, pasta=None) -> str:
    """Salva a matriz de confusão (linhas = sinal real, colunas = previsto).
    `colunas` permite colunas extras (ex.: "(nenhum)"); `pasta` padrão: reports/."""
    colunas = colunas or classes
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.ticker
    from matplotlib.colors import LinearSegmentedColormap

    plt.rcParams.update({"font.size": 10, "text.color": TEXTO, "axes.labelcolor": TEXTO_SECUNDARIO,
                         "xtick.color": TEXTO_SECUNDARIO, "ytick.color": TEXTO_SECUNDARIO,
                         "figure.facecolor": SUPERFICIE, "axes.facecolor": SUPERFICIE})
    totais = matriz.sum(axis=1, keepdims=True)
    fracao = np.divide(matriz, totais, out=np.zeros(matriz.shape, dtype=float), where=totais > 0)
    rotulos = [config.rotulo_exibicao(c) for c in classes]
    rotulos_colunas = [config.rotulo_exibicao(c) for c in colunas]

    tamanho = 2.5 + 0.62 * len(classes)
    fig, ax = plt.subplots(figsize=(2.5 + 0.62 * len(colunas) + 1.6, tamanho))
    imagem = ax.imshow(fracao, cmap=LinearSegmentedColormap.from_list("azul", RAMPA_SEQUENCIAL),
                       vmin=0, vmax=1)
    for i in range(len(classes)):
        for j in range(len(colunas)):
            if matriz[i, j]:
                ax.text(j, i, str(matriz[i, j]), ha="center", va="center", fontsize=9,
                        color="#ffffff" if fracao[i, j] > 0.5 else TEXTO)
    ax.set_xticks(range(len(colunas)), rotulos_colunas, rotation=45, ha="right")
    ax.set_yticks(range(len(classes)), rotulos)
    ax.set_xlabel("Sinal previsto pelo modelo")
    ax.set_ylabel("Sinal real")
    ax.set_title(titulo, loc="left", fontsize=11)
    for lado in ax.spines.values():
        lado.set_visible(False)
    fig.colorbar(imagem, ax=ax, fraction=0.046, pad=0.03,
                 label="fração das amostras do sinal real").ax.yaxis.set_major_formatter(
        matplotlib.ticker.PercentFormatter(1.0))
    fig.tight_layout()
    from pathlib import Path
    pasta = Path(pasta) if pasta is not None else config.DIR_REPORTS
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = pasta / nome_arquivo
    fig.savefig(caminho, dpi=120)
    plt.close(fig)
    return str(caminho)
