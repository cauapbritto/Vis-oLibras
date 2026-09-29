"""`python -m libras` abre a aplicação de demonstração (interface gráfica)."""

import sys


def main() -> int:
    try:
        from libras.interface import iniciar
    except ImportError as erro:
        print(f"[ERRO] {erro}\nInstale as dependências: pip install -r requirements.txt\n"
              "No Linux, o Tkinter vem à parte: sudo apt install python3-tk", file=sys.stderr)
        return 1
    iniciar()
    return 0


if __name__ == "__main__":
    sys.exit(main())
