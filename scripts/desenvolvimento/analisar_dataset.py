"""Valida e analisa o dataset de landmarks (Fase 2).

Mostra sinais cadastrados, amostras por sinal e por pessoa, tamanho do vetor de
características, amostras inválidas, classes com poucas amostras, possíveis
inconsistências e sinais parecidos. Salva o relatório em
reports/analise_dataset.txt e os gráficos em reports/analise_dataset.png.

Uso:
    python scripts/desenvolvimento/analisar_dataset.py
    python scripts/desenvolvimento/analisar_dataset.py --remover-invalidas   # pede confirmação
    python scripts/desenvolvimento/analisar_dataset.py --sem-grafico
"""

import argparse
import sys

import numpy as np

from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))  # funciona sem "pip install -e ."

from libras import config, dataset
from libras.dataset import PERFIS_MAOS, RelatorioDataset

# Paleta validada (skill dataviz, modo claro)
from libras.avaliacao import SUPERFICIE, TEXTO, TEXTO_SECUNDARIO  # noqa: E402

GRADE = "#e4e3df"
COR_SERIE = "#2a78d6"
COR_CRITICO = "#d03b3b"
CORES_PERFIL = {"ambas": "#2a78d6", "direita": "#eb6834", "esquerda": "#1baf7a", "nenhuma": "#eda100"}
RAMPA_SEQUENCIAL = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]


def montar_relatorio(rel: RelatorioDataset, detalhes: bool) -> list[str]:
    linhas = ["=" * 64, "ANÁLISE DO DATASET", "=" * 64]
    total, invalidas = len(rel.amostras), rel.invalidas()
    com_amostras = [c for c in config.CLASSES if rel.contagem(c) > 0]
    tamanhos = ", ".join(str(t) for t in sorted(rel.tamanhos_vetor)) or "—"

    linhas += [
        f"Pasta do dataset      : {config.DIR_RAW}",
        f"Sinais cadastrados    : {len(config.SINAIS)} + {config.CLASSE_NADA} "
        f"({len(com_amostras)} de {len(config.CLASSES)} classes com amostras)",
        f"Amostras              : {total} ({total - len(invalidas)} válidas, {len(invalidas)} inválidas)",
        f"Frame bruto           : {config.TAM_FRAME_BRUTO} valores",
        f"Vetor de features     : {tamanhos} valores "
        f"(esperado {config.TAM_FEATURES_JANELA} = {config.T_FRAMES} frames x {config.TAM_FEATURES_FRAME} "
        f"+ {config.TAM_MOVIMENTO} de movimento)",
        f"Versão das features   : {config.VERSAO_FEATURES}",
        "",
        "AMOSTRAS VÁLIDAS POR SINAL",
        f"  {'sinal':<10} {'amostras':>8}  {'pessoas':<24} mãos predominantes",
    ]
    for classe in config.CLASSES:
        n = rel.contagem(classe)
        pessoas = ", ".join(f"{p}:{q}" for p, q in sorted(rel.pessoas(classe).items())) or "—"
        perfis = ", ".join(f"{p} {q}" for p, q in rel.perfis(classe).most_common()) or "—"
        marca = "  <- poucas" if n < config.MIN_AMOSTRAS_POR_CLASSE else ""
        linhas.append(f"  {config.rotulo_exibicao(classe):<10} {n:>8}  {pessoas:<24} {perfis}{marca}")

    poucas = rel.classes_com_poucas_amostras()
    linhas += ["", f"CLASSES COM POUCAS AMOSTRAS (< {config.MIN_AMOSTRAS_POR_CLASSE}): "
               + (", ".join(f"{c} ({rel.contagem(c)})" for c in poucas) if poucas else "nenhuma")]

    linhas += ["", f"AMOSTRAS INVÁLIDAS ({len(invalidas)})"]
    motivos = {}
    for a in invalidas:
        motivos.setdefault(a.problemas[0].split(" (")[0].split(";")[0], []).append(a)
    for motivo, lista in sorted(motivos.items(), key=lambda m: -len(m[1])):
        linhas.append(f"  {len(lista):>4} x {motivo}")
    for a in invalidas[: None if detalhes else 10]:
        linhas.append(f"       {a.arquivo}: {'; '.join(a.problemas)}")
    if not detalhes and len(invalidas) > 10:
        linhas.append(f"       ... e mais {len(invalidas) - 10} (use --detalhes)")
    if not invalidas:
        linhas.append("  nenhuma")

    linhas += ["", f"INCONSISTÊNCIAS ({len(rel.inconsistencias)})"]
    linhas += [f"  - {i}" for i in rel.inconsistencias] or ["  nenhuma"]

    linhas += ["", f"AMOSTRAS SUSPEITAS ({len(rel.alertas)}) - confira com atenção"]
    for arquivo, motivo in rel.alertas[: None if detalhes else 10]:
        linhas.append(f"  - {arquivo}: {motivo}")
    if not detalhes and len(rel.alertas) > 10:
        linhas.append(f"  ... e mais {len(rel.alertas) - 10} (use --detalhes)")
    if not rel.alertas:
        linhas.append("  nenhuma")

    pares = dataset.pares_mais_parecidos(rel)
    if pares:
        linhas += ["", "SINAIS MAIS PARECIDOS (similaridade de -1 a 1; perto de 1 = risco de confusão)"]
        linhas += [f"  {config.rotulo_exibicao(a)} x {config.rotulo_exibicao(b)}: {s:.2f}" for a, b, s in pares]

    tabela = dataset.por_pessoa(rel)
    if tabela:
        linhas += ["", "AMOSTRAS POR PESSOA"]
        for pessoa, contagem in sorted(tabela.items()):
            linhas.append(f"  {pessoa:<12} {sum(contagem.values()):>5} amostras em {len(contagem)} classes")
    linhas.append("")
    return linhas


def salvar_graficos(rel: RelatorioDataset) -> str:
    import matplotlib
    matplotlib.use("Agg")  # só gera o arquivo, sem abrir janela
    import matplotlib.pyplot as plt
    import matplotlib.ticker
    from matplotlib.colors import LinearSegmentedColormap

    plt.rcParams.update({
        "font.size": 10, "text.color": TEXTO, "axes.labelcolor": TEXTO_SECUNDARIO,
        "xtick.color": TEXTO_SECUNDARIO, "ytick.color": TEXTO_SECUNDARIO,
        "axes.edgecolor": GRADE, "figure.facecolor": SUPERFICIE, "axes.facecolor": SUPERFICIE,
    })
    classes = config.CLASSES
    rotulos = [config.rotulo_exibicao(c) for c in classes]
    posicoes = np.arange(len(classes))

    fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(18, 6.5),
                                        gridspec_kw={"width_ratios": [1, 1, 1.15]})
    fig.suptitle("Análise do dataset", fontsize=15, x=0.01, ha="left", fontweight="bold")

    # 1. Amostras válidas por sinal
    contagens = [rel.contagem(c) for c in classes]
    cores = [COR_CRITICO if n < config.MIN_AMOSTRAS_POR_CLASSE else COR_SERIE for n in contagens]
    ax1.barh(posicoes, contagens, color=cores, height=0.6, edgecolor=SUPERFICIE, linewidth=2)
    ax1.axvline(config.MIN_AMOSTRAS_POR_CLASSE, color=TEXTO_SECUNDARIO, linestyle="--", linewidth=1)
    limite = max(contagens + [config.MIN_AMOSTRAS_POR_CLASSE]) * 1.45
    for y, n in zip(posicoes, contagens):
        texto = f"{n}" + ("  (!) abaixo do mínimo" if n < config.MIN_AMOSTRAS_POR_CLASSE else "")
        ax1.text(n + limite * 0.01, y, texto, va="center", fontsize=9, color=TEXTO)
    ax1.set_xlim(0, limite)
    ax1.set_title(f"Amostras válidas por sinal (mínimo {config.MIN_AMOSTRAS_POR_CLASSE}, tracejado)",
                  loc="left", fontsize=11)

    # 2. Mãos predominantes em cada sinal (100%)
    inicio = np.zeros(len(classes))
    for perfil in PERFIS_MAOS:
        fracoes = np.array([rel.perfis(c)[perfil] / max(rel.contagem(c), 1) for c in classes])
        ax2.barh(posicoes, fracoes, left=inicio, color=CORES_PERFIL[perfil], height=0.6,
                 edgecolor=SUPERFICIE, linewidth=2, label=perfil)
        inicio += fracoes
    ax2.set_xlim(0, 1)
    ax2.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    ax2.legend(ncol=4, loc="lower left", bbox_to_anchor=(0, 1.0), frameon=False, fontsize=9)
    ax2.set_title("Mãos predominantes por sinal", loc="left", fontsize=11, pad=24)

    for ax in (ax1, ax2):
        ax.set_yticks(posicoes, rotulos)
        ax.invert_yaxis()
        ax.grid(axis="x", color=GRADE, linewidth=0.8)
        ax.set_axisbelow(True)
        for lado in ("top", "right"):
            ax.spines[lado].set_visible(False)

    # 3. Similaridade entre sinais
    if rel.similaridade is not None:
        nomes, matriz = rel.similaridade
        exibida = np.where(np.eye(len(nomes), dtype=bool), np.nan, matriz)
        mapa = LinearSegmentedColormap.from_list("azul", RAMPA_SEQUENCIAL)
        imagem = ax3.imshow(np.clip(exibida, 0, 1), cmap=mapa, vmin=0, vmax=1)
        for i in range(len(nomes)):
            for j in range(len(nomes)):
                if i != j:
                    ax3.text(j, i, f"{matriz[i, j]:.2f}", ha="center", va="center", fontsize=8,
                             color="#ffffff" if matriz[i, j] > 0.55 else TEXTO)
        rot = [config.rotulo_exibicao(n) for n in nomes]
        ax3.set_xticks(range(len(nomes)), rot, rotation=45, ha="right")
        ax3.set_yticks(range(len(nomes)), rot)
        fig.colorbar(imagem, ax=ax3, fraction=0.046, pad=0.03, label="similaridade (negativos = 0)")
        ax3.set_title("Similaridade entre sinais (escuro = risco de confusão)", loc="left", fontsize=11)
    else:
        ax3.text(0.5, 0.5, "São necessárias amostras de\npelo menos 2 sinais",
                 ha="center", va="center", color=TEXTO_SECUNDARIO)
        ax3.set_axis_off()
    for lado in ax3.spines.values():
        lado.set_visible(False)

    fig.tight_layout()
    caminho = config.DIR_REPORTS / "analise_dataset.png"
    config.DIR_REPORTS.mkdir(parents=True, exist_ok=True)
    fig.savefig(caminho, dpi=110)
    plt.close(fig)
    return str(caminho)


def remover_invalidas(rel: RelatorioDataset, confirmar: bool) -> None:
    invalidas = rel.invalidas()
    if not invalidas:
        return
    if confirmar and input(f"Apagar {len(invalidas)} amostras inválidas? [s/N] ").strip().lower() != "s":
        print("Nada foi apagado.")
        return
    for amostra in invalidas:
        dataset.remover_amostra(config.DIR_DATA / amostra.arquivo)
    print(f"{len(invalidas)} amostras inválidas apagadas.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--detalhes", action="store_true", help="lista todas as amostras com problema")
    parser.add_argument("--sem-grafico", action="store_true", help="não gera o PNG")
    parser.add_argument("--remover-invalidas", action="store_true", help="apaga as amostras inválidas")
    parser.add_argument("--sim", action="store_true", help="não pede confirmação ao remover")
    args = parser.parse_args()

    rel = dataset.analisar_dataset()
    texto = "\n".join(montar_relatorio(rel, args.detalhes))
    print(texto)
    config.DIR_REPORTS.mkdir(parents=True, exist_ok=True)
    (config.DIR_REPORTS / "analise_dataset.txt").write_text(texto, encoding="utf-8")
    print(f"Relatório salvo em {config.DIR_REPORTS / 'analise_dataset.txt'}")

    if not args.sem_grafico:
        print(f"Gráficos salvos em {salvar_graficos(rel)}")
    if args.remover_invalidas:
        remover_invalidas(rel, confirmar=not args.sim)

    # Código de saída 1 se há problemas: útil para checagem automática.
    return 1 if rel.invalidas() or rel.inconsistencias else 0


if __name__ == "__main__":
    sys.exit(main())
