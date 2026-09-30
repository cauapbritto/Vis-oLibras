"""Confere a tabela de frases (frases.txt) sem abrir a câmera.

Uso:
    python scripts/demonstracao/testar_frases.py               revisa o arquivo e testa cada frase
    python scripts/demonstracao/testar_frases.py EU NOME OI    mostra como essa sequência aparece
    python scripts/demonstracao/testar_frases.py --arquivo outro.txt
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))  # funciona sem "pip install -e ."

from libras import config  # noqa: E402
from libras.traducao import TabelaFrases  # noqa: E402


def mostrar(tabela: TabelaFrases, sinais: list[str]) -> None:
    resultado = tabela.traduzir(sinais)
    situacao = "tudo convertido" if resultado.completa else (
        "convertido em parte" if resultado.convertida else "sem frase cadastrada: fica como glosa")
    print(f"   sinais : {resultado.glosa}")
    print(f"   texto  : {resultado.texto}")
    print(f"            ({situacao})\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("sinais", nargs="*", help="sequência de sinais, ex.: EU NOME")
    parser.add_argument("--arquivo", type=Path, default=config.ARQ_FRASES)
    args = parser.parse_args()

    tabela = TabelaFrases.ler(args.arquivo)
    print(f"Arquivo: {args.arquivo}  ({len(tabela)} frases)\n")
    if tabela.avisos:
        print("Avisos:")
        for aviso in tabela.avisos:
            print(f"   - {aviso}")
        print()

    if args.sinais:
        mostrar(tabela, [config.identificador_sinal(s) for s in args.sinais])
    else:
        print("Frases cadastradas:")
        for sinais, texto in tabela.frases.items():
            print(f"   {' '.join(sinais):20s} -> {texto}")
        print("\nTeste uma sequência: python scripts/demonstracao/testar_frases.py EU NOME OBRIGADO")
    return 1 if tabela.avisos else 0


if __name__ == "__main__":
    sys.exit(main())
