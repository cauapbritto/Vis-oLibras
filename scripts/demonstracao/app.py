"""Aplicação de demonstração com interface gráfica (CustomTkinter).

Mostra a webcam com os landmarks, o sinal detectado e a confiança, o último
sinal confirmado, a sequência de palavras e a frase final, com botões para
iniciar/parar a câmera, finalizar, limpar, remover a última palavra e falar.

Uso:
    python scripts/demonstracao/app.py
    python scripts/demonstracao/app.py --camera 1 --tema claro

Para a versão simples em janela do OpenCV: python scripts/demonstracao/executar.py
"""

import argparse
import sys

from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))  # funciona sem "pip install -e ."

from libras import config


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--camera", type=int, default=config.INDICE_CAMERA, help="índice da webcam")
    parser.add_argument("--tema", choices=["escuro", "claro"], default="escuro", help="aparência da janela")
    args = parser.parse_args()
    try:
        from libras.interface import iniciar
    except ImportError as erro:
        print(f"[ERRO] {erro}\nInstale as dependências: pip install -r requirements.txt\n"
              "No Linux, o Tkinter vem à parte: sudo apt install python3-tk", file=sys.stderr)
        return 1
    iniciar(args.camera, "dark" if args.tema == "escuro" else "light")
    return 0


if __name__ == "__main__":
    sys.exit(main())
