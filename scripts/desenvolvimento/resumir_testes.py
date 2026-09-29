"""Resumo estatístico dos testes controlados (modo desenvolvimento).

Lê os CSVs gravados pelo teste_controlado.py e calcula, SOMENTE com as
tentativas registradas: accuracy, precision, recall e F1 (por sinal e média),
matriz de confusão, erros por sinal, tempo de resposta e latência (média,
mediana, desvio, p95), FPS e tempo de inferência, e accuracy por participante.

Uso:
    python scripts/desenvolvimento/resumir_testes.py                 # todos os CSVs de reports/testes/
    python scripts/desenvolvimento/resumir_testes.py reports/testes/ana_*.csv

Saídas (em reports/testes/resumo/): resumo.txt, resumo.json, por_classe.csv,
matriz_confusao.csv e matriz_confusao.png - prontos para gráficos e relatório.
"""

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))  # funciona sem "pip install -e ."

import numpy as np  # noqa: E402

from libras import config  # noqa: E402
from libras.avaliacao import salvar_matriz_confusao  # noqa: E402
from libras.experimento import ler_csv, resumir  # noqa: E402


def _tempo(est: dict, unidade: str = "s", fator: float = 1.0) -> str:
    if not est.get("n"):
        return "sem dados"
    return (f"média {est['media'] * fator:.2f} {unidade} | mediana {est['mediana'] * fator:.2f} | "
            f"desvio {est['desvio'] * fator:.2f} | p95 {est['p95'] * fator:.2f} | n={est['n']}")


def texto_resumo(r: dict) -> str:
    linhas = [
        "=" * 64, "RESUMO DOS TESTES CONTROLADOS", "=" * 64,
        f"Tentativas: {r['tentativas']} | participantes: {', '.join(r['participantes'])} | "
        f"sessões: {len(r['sessoes'])}",
        f"Modelo(s): {'; '.join(r['modelos'])}",
        "",
        f"Accuracy geral : {r['accuracy']:.1%}",
        f"Precision macro: {r['precision_macro']:.3f}",
        f"Recall macro   : {r['recall_macro']:.3f}",
        f"F1 macro       : {r['f1_macro']:.3f}",
        "",
        f"{'sinal':<10}{'tent.':>6}{'acertos':>9}{'erros':>7}{'nada':>6}{'precision':>11}{'recall':>8}{'F1':>7}"
        "   confundido com",
    ]
    for classe, c in r["por_classe"].items():
        confusoes = ", ".join(f"{config.rotulo_exibicao(k)} {v}x" for k, v in c["confundido_com"].items()) or "-"
        linhas.append(f"{config.rotulo_exibicao(classe):<10}{c['tentativas']:>6}{c['acertos']:>9}{c['erros']:>7}"
                      f"{c['nao_reconhecidos']:>6}{c['precision']:>11.3f}{c['recall']:>8.3f}{c['f1']:>7.3f}"
                      f"   {confusoes}")
    linhas += [
        "",
        "TEMPOS (somente tentativas acertadas)",
        f"  Tempo de resposta (do 'JÁ!' ao reconhecimento): {_tempo(r['tempo_resposta_s_acertos'])}",
        f"  Latência do sistema (das mãos ao reconhecimento): {_tempo(r['latencia_sistema_s_acertos'])}",
        "",
        "DESEMPENHO",
        f"  FPS (média por tentativa): {_tempo(r['fps'], 'fps')}",
        f"  Inferência do modelo     : {_tempo(r['inferencia_ms'], 'ms')}",
        "",
        "ACCURACY POR PARTICIPANTE",
    ]
    linhas += [f"  {p:<12} {a:.1%}" for p, a in r["accuracy_por_participante"].items()]
    return "\n".join(linhas) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("csvs", nargs="*", type=Path, help="CSVs de testes (padrão: reports/testes/*.csv)")
    parser.add_argument("--saida", type=Path, default=config.DIR_TESTES / "resumo")
    parser.add_argument("--sem-grafico", action="store_true")
    args = parser.parse_args()

    caminhos = args.csvs or sorted(config.DIR_TESTES.glob("*.csv"))
    if not caminhos:
        print(f"[ERRO] nenhum CSV em {config.DIR_TESTES}. Rode antes o teste_controlado.py.", file=sys.stderr)
        return 1
    try:
        r = resumir(ler_csv(caminhos))
    except (ValueError, KeyError) as erro:
        print(f"[ERRO] {erro}", file=sys.stderr)
        return 1

    args.saida.mkdir(parents=True, exist_ok=True)
    texto = texto_resumo(r)
    print(texto)
    (args.saida / "resumo.txt").write_text(texto, encoding="utf-8")
    (args.saida / "resumo.json").write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")

    with open(args.saida / "por_classe.csv", "w", newline="", encoding="utf-8") as arquivo:
        escritor = csv.writer(arquivo)
        escritor.writerow(["sinal", "tentativas", "acertos", "erros", "nao_reconhecidos",
                           "precision", "recall", "f1"])
        for classe, c in r["por_classe"].items():
            escritor.writerow([classe, c["tentativas"], c["acertos"], c["erros"], c["nao_reconhecidos"],
                               f"{c['precision']:.4f}", f"{c['recall']:.4f}", f"{c['f1']:.4f}"])

    m = r["matriz_confusao"]
    with open(args.saida / "matriz_confusao.csv", "w", newline="", encoding="utf-8") as arquivo:
        escritor = csv.writer(arquivo)
        escritor.writerow(["real \\ reconhecido"] + m["colunas_reconhecido"])
        for real, valores in zip(m["linhas_sinal_real"], m["valores"]):
            escritor.writerow([real] + valores)
    if not args.sem_grafico:
        salvar_matriz_confusao(np.array(m["valores"]), m["linhas_sinal_real"],
                               f"Testes controlados ({r['tentativas']} tentativas)",
                               "matriz_confusao.png", colunas=m["colunas_reconhecido"], pasta=args.saida)
    print(f"Arquivos em {args.saida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
