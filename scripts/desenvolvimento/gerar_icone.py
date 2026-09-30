"""Gera o ícone do aplicativo (src/libras/recursos/icone.png e icone.ico).

O desenho fica em libras.desenho.icone_mao; rode este script de novo só se
mudar o desenho ou a cor.

Uso:
    python scripts/desenvolvimento/gerar_icone.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))  # funciona sem "pip install -e ."

from libras import config  # noqa: E402
from libras.desenho import icone_mao  # noqa: E402

COR_FUNDO = "#256abf"   # mesmo azul do botão principal da interface
COR_MAO = "#ffffff"
TAMANHOS_ICO = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def main() -> int:
    config.DIR_RECURSOS.mkdir(parents=True, exist_ok=True)
    grande = icone_mao(256, COR_MAO, COR_FUNDO)
    grande.save(config.ARQ_ICONE_PNG, optimize=True)
    # cada tamanho desenhado à parte (fica mais nítido que reduzir o de 256)
    imagens = [icone_mao(t, COR_MAO, COR_FUNDO) for t in TAMANHOS_ICO]
    imagens[-1].save(config.ARQ_ICONE_ICO, format="ICO", sizes=[(t, t) for t in TAMANHOS_ICO],
                     append_images=imagens[:-1])
    for arquivo in (config.ARQ_ICONE_PNG, config.ARQ_ICONE_ICO):
        print(f"{arquivo.relative_to(config.RAIZ_PROJETO)}  ({arquivo.stat().st_size / 1024:.1f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
