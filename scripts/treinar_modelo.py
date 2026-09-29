"""Treina o classificador de sinais (Fase 3).

Etapas:
 1. carrega data/processed/dataset.npz (gerado com as MESMAS features da coleta
    e do tempo real) e valida os dados;
 2. separa treino e teste de forma estratificada (mesma proporção de cada sinal);
 3. compara Random Forest, SVM e MLP com validação cruzada no treino;
 4. avalia o escolhido no teste: accuracy, precision/recall/F1 por classe,
    matriz de confusão e sinais confundidos;
 5. (com 2+ pessoas) testa com pessoas que o modelo nunca viu;
 6. retreina com todas as amostras e salva modelo, classes e configurações.

Uso:
    python scripts/treinar_modelo.py                 # escolhe o algoritmo automaticamente
    python scripts/treinar_modelo.py --modelo rf     # força Random Forest (rf, svm, mlp)
    python scripts/treinar_modelo.py --reconstruir   # regera o dataset.npz antes
"""

import argparse
import platform
import sys
import time
import warnings
from collections import Counter
from datetime import datetime

import numpy as np
import sklearn
from sklearn.base import clone
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import RandomForestClassifier
from sklearn.exceptions import ConvergenceWarning
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

from libras import config, dataset
from libras.classificador import ajustar_para_tempo_real, salvar_classificador

# Mesmas cores do analisar_dataset.py (paleta validada, modo claro)
SUPERFICIE, TEXTO, TEXTO_SECUNDARIO = "#fcfcfb", "#0b0b0b", "#52514e"
RAMPA_SEQUENCIAL = ["#f4f8fe", "#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]


def candidatos() -> dict[str, tuple[str, Pipeline]]:
    """Algoritmos comparados. Todos são Pipelines: a padronização (quando existe)
    fica DENTRO do modelo salvo, então o tempo real aplica exatamente a mesma."""
    s = config.SEMENTE
    return {
        "rf": ("Random Forest", Pipeline([
            ("modelo", RandomForestClassifier(n_estimators=config.N_ARVORES, class_weight="balanced",
                                              n_jobs=-1, random_state=s)),
        ])),
        "svm": ("SVM (kernel RBF)", Pipeline([
            ("padronizar", StandardScaler()),
            # CalibratedClassifierCV fornece as probabilidades (confiança) do SVM
            ("modelo", CalibratedClassifierCV(
                SVC(kernel="rbf", C=10, gamma="scale", class_weight="balanced", random_state=s),
                ensemble=False, cv=3)),
        ])),
        "mlp": ("MLP (rede neural pequena: 256-128)", Pipeline([
            ("padronizar", StandardScaler()),
            ("modelo", MLPClassifier(hidden_layer_sizes=(256, 128), alpha=1e-3, max_iter=1000,
                                     random_state=s)),
        ])),
    }


def comparar(nomes: list[str], X: np.ndarray, y: np.ndarray, mostrar=print) -> dict[str, dict]:
    """F1 macro de cada candidato em validação cruzada estratificada (só no treino)."""
    menor_classe = min(Counter(y).values())
    n_folds = min(config.N_FOLDS_CV, menor_classe)
    if n_folds < 2:
        mostrar("  (poucas amostras para validação cruzada; usando Random Forest)")
        return {}
    folds = StratifiedKFold(n_splits=n_folds, shuffle=True, random_state=config.SEMENTE)
    resultados = {}
    for nome in nomes:
        descricao, pipeline = candidatos()[nome]
        inicio = time.perf_counter()
        notas = cross_val_score(pipeline, X, y, cv=folds, scoring="f1_macro", n_jobs=1)
        resultados[nome] = {"descricao": descricao, "f1_macro_media": float(notas.mean()),
                            "f1_macro_desvio": float(notas.std()), "folds": n_folds,
                            "tempo_s": time.perf_counter() - inicio}
        mostrar(f"  {descricao:<36} F1 = {notas.mean():.3f} ± {notas.std():.3f}"
                f"   ({resultados[nome]['tempo_s']:.1f}s)")
    return resultados


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


def testar_pessoas_novas(pipeline: Pipeline, dados: dataset.DadosTreino) -> dict[str, dict]:
    """Deixa uma pessoa de fora, treina com as outras e testa nela (para cada pessoa)."""
    resultados = {}
    for pessoa in sorted(set(dados.pessoas)):
        teste = dados.pessoas == pessoa
        if len(set(dados.y[~teste])) < 2:
            continue
        modelo = clone(pipeline).fit(dados.X[~teste], dados.y[~teste])
        previsto = modelo.predict(dados.X[teste])
        resultados[pessoa] = {"amostras": int(teste.sum()),
                              "accuracy": float(accuracy_score(dados.y[teste], previsto)),
                              "f1_macro": float(f1_score(dados.y[teste], previsto, average="macro",
                                                         zero_division=0))}
    return resultados


def salvar_matriz_confusao(matriz: np.ndarray, classes: list[str], titulo: str) -> str:
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

    tamanho = 2.5 + 0.62 * len(classes)
    fig, ax = plt.subplots(figsize=(tamanho + 1.6, tamanho))
    imagem = ax.imshow(fracao, cmap=LinearSegmentedColormap.from_list("azul", RAMPA_SEQUENCIAL),
                       vmin=0, vmax=1)
    for i in range(len(classes)):
        for j in range(len(classes)):
            if matriz[i, j]:
                ax.text(j, i, str(matriz[i, j]), ha="center", va="center", fontsize=9,
                        color="#ffffff" if fracao[i, j] > 0.5 else TEXTO)
    ax.set_xticks(range(len(classes)), rotulos, rotation=45, ha="right")
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
    caminho = config.DIR_REPORTS / "matriz_confusao.png"
    fig.savefig(caminho, dpi=120)
    plt.close(fig)
    return str(caminho)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--modelo", choices=["auto", *candidatos()], default="auto",
                        help="algoritmo (auto = melhor F1 na validação cruzada)")
    parser.add_argument("--reconstruir", action="store_true", help="regera o dataset.npz a partir de data/raw")
    parser.add_argument("--sem-grafico", action="store_true", help="não gera a matriz de confusão em PNG")
    args = parser.parse_args()
    warnings.filterwarnings("ignore", category=ConvergenceWarning)
    relatorio: list[str] = []

    def mostrar(texto: str = "") -> None:
        print(texto)
        relatorio.append(texto)

    # 1. Carregar e validar
    try:
        if args.reconstruir or dataset.precisa_reconstruir():
            print(f"Construindo dataset.npz (features v{config.VERSAO_FEATURES}) a partir de data/raw ...")
            dados, _ = dataset.construir_dados_treino()
            dataset.salvar_dados_treino(dados)
        dados = dataset.carregar_dados_treino()
    except dataset.ErroDataset as erro:
        print(f"[ERRO] {erro}", file=sys.stderr)
        return 1

    contagem = Counter(dados.y)
    classes = [c for c in config.CLASSES if c in contagem]
    mostrar("=" * 64)
    mostrar(f"TREINAMENTO - {datetime.now():%d/%m/%Y %H:%M}")
    mostrar("=" * 64)
    mostrar(f"Dataset: {len(dados.y)} amostras, {len(classes)} classes, {dados.X.shape[1]} features "
            f"(versão {config.VERSAO_FEATURES}), "
            f"pessoas: {', '.join(sorted(set(dados.pessoas)))}")
    ausentes = [c for c in config.CLASSES if c not in contagem]
    if ausentes:
        mostrar(f"[AVISO] classes sem amostras (o modelo não vai reconhecê-las): {', '.join(ausentes)}")
    poucas = [f"{c} ({contagem[c]})" for c in classes if contagem[c] < config.MIN_AMOSTRAS_POR_CLASSE]
    if poucas:
        mostrar(f"[AVISO] classes com menos de {config.MIN_AMOSTRAS_POR_CLASSE} amostras: {', '.join(poucas)}")

    # 2. Separação estratificada
    try:
        X_tr, X_te, y_tr, y_te = train_test_split(dados.X, dados.y, test_size=config.FRACAO_TESTE,
                                                  stratify=dados.y, random_state=config.SEMENTE)
    except ValueError as erro:
        print(f"[ERRO] não foi possível separar treino/teste: {erro}. Grave mais amostras.", file=sys.stderr)
        return 1
    mostrar(f"Treino: {len(y_tr)} amostras | Teste: {len(y_te)} amostras "
            f"({config.FRACAO_TESTE:.0%}, estratificado, random_state={config.SEMENTE})")

    # 3. Comparar algoritmos (validação cruzada só no treino; o teste fica intocado)
    mostrar("\nCOMPARAÇÃO DE ALGORITMOS (validação cruzada no treino, F1 macro)")
    nomes = list(candidatos()) if args.modelo == "auto" else [args.modelo]
    comparacao = comparar(nomes, X_tr, y_tr, mostrar)
    escolhido = max(comparacao, key=lambda n: comparacao[n]["f1_macro_media"]) if comparacao else \
        (args.modelo if args.modelo != "auto" else "rf")
    descricao, pipeline = candidatos()[escolhido]
    mostrar(f"Escolhido: {descricao}")

    # 4. Avaliação no teste
    modelo = ajustar_para_tempo_real(clone(pipeline).fit(X_tr, y_tr))
    previsto = modelo.predict(X_te)
    inicio = time.perf_counter()
    for vetor in X_te[:50]:
        modelo.predict_proba(vetor.reshape(1, -1))
    tempo_ms = (time.perf_counter() - inicio) / min(len(X_te), 50) * 1000

    accuracy = accuracy_score(y_te, previsto)
    f1_macro = f1_score(y_te, previsto, average="macro", zero_division=0)
    mostrar(f"\nRESULTADO NO TESTE ({len(y_te)} amostras nunca vistas no treino)")
    mostrar(f"  Accuracy : {accuracy:.1%}  ({int((previsto == y_te).sum())} de {len(y_te)} acertos)")
    mostrar(f"  F1 macro : {f1_macro:.3f}")
    mostrar(f"  Tempo de uma previsão: {tempo_ms:.1f} ms")
    rotulos = [config.rotulo_exibicao(c) for c in classes]
    mostrar("\n" + classification_report(y_te, previsto, labels=classes, target_names=rotulos,
                                         digits=3, zero_division=0))
    por_classe = classification_report(y_te, previsto, labels=classes, output_dict=True, zero_division=0)

    matriz = confusion_matrix(y_te, previsto, labels=classes)
    confusoes = sinais_confundidos(matriz, classes)
    mostrar("SINAIS CONFUNDIDOS (real -> previsto)")
    for c in confusoes[:10]:
        mostrar(f"  {config.rotulo_exibicao(c['real'])} -> {config.rotulo_exibicao(c['previsto'])}: "
                f"{c['vezes']}x ({c['pct_do_real']:.0%} das amostras de {config.rotulo_exibicao(c['real'])})")
    if not confusoes:
        mostrar("  nenhuma confusão no conjunto de teste")

    # 5. Pessoas novas
    pessoas_novas = {}
    if len(set(dados.pessoas)) >= 2:
        mostrar("\nTESTE COM PESSOAS NOVAS (treina sem a pessoa e testa nela)")
        pessoas_novas = testar_pessoas_novas(pipeline, dados)
        for pessoa, r in pessoas_novas.items():
            mostrar(f"  {pessoa:<12} accuracy {r['accuracy']:.1%}  F1 {r['f1_macro']:.3f}  ({r['amostras']} amostras)")
        if pessoas_novas:
            media = np.mean([r["accuracy"] for r in pessoas_novas.values()])
            mostrar(f"  Média: {media:.1%}  <- estimativa mais realista para quem nunca gravou")
    else:
        mostrar("\n[AVISO] só 1 pessoa no dataset: não dá para medir o desempenho com pessoas novas")

    # 6. Modelo final (todas as amostras) + registros
    final = clone(pipeline).fit(dados.X, dados.y)
    estimador = final.named_steps["modelo"]
    info = {
        "criado_em": datetime.now().isoformat(timespec="seconds"),
        "algoritmo": escolhido, "descricao": descricao,
        "etapas_pipeline": [nome for nome, _ in final.steps],
        "parametros": {k: v for k, v in estimador.get_params().items()},
        "random_state": config.SEMENTE, "fracao_teste": config.FRACAO_TESTE, "n_folds_cv": config.N_FOLDS_CV,
        "modelo_final": "retreinado com todas as amostras após a avaliação",
        "amostras": {"total": len(dados.y), "treino": len(y_tr), "teste": len(y_te),
                     "por_classe": {c: contagem[c] for c in classes}},
        "pessoas": sorted(set(dados.pessoas)),
        "comparacao_cv": comparacao,
        "metricas_teste": {"accuracy": accuracy, "f1_macro": f1_macro,
                           "por_classe": {c: por_classe[c] for c in classes}},
        "sinais_confundidos": confusoes,
        "teste_pessoas_novas": pessoas_novas,
        "tempo_previsao_ms": tempo_ms,
        "versoes": {"python": platform.python_version(), "scikit_learn": sklearn.__version__,
                    "numpy": np.__version__},
    }
    salvar_classificador(final, info)
    mostrar(f"\nModelo salvo em {config.ARQ_MODELO}")
    mostrar(f"Classes salvas em {config.ARQ_CLASSES}")
    mostrar(f"Configurações e métricas em {config.ARQ_MODELO_INFO}")

    config.DIR_REPORTS.mkdir(parents=True, exist_ok=True)
    if not args.sem_grafico:
        mostrar(f"Matriz de confusão em {salvar_matriz_confusao(matriz, classes, f'Matriz de confusão - {descricao} (teste: {len(y_te)} amostras)')}")
    (config.DIR_REPORTS / "classification_report.txt").write_text("\n".join(relatorio), encoding="utf-8")
    print(f"Relatório em {config.DIR_REPORTS / 'classification_report.txt'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
