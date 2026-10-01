"""Gera o pacote do MODO USUÁRIO: só o necessário para a demonstração (desenvolvimento).

Inclui o núcleo e a aplicação (libras.MODULOS_NUCLEO + MODULOS_APLICACAO), os
scripts de demonstração, a tabela de frases (frases.txt), o instalador de um clique do Windows (INSTALAR.bat,
Librahin.bat e windows/), o requirements.txt e os modelos (classificador
treinado e, se já baixados, os modelos do MediaPipe - útil em redes que
bloqueiam o download). NÃO inclui dataset, relatórios, testes, scripts de
treino nem módulos de desenvolvimento.

Uso:
    python scripts/desenvolvimento/empacotar_app.py
    python scripts/desenvolvimento/empacotar_app.py --saida dist/demo.zip

No computador da apresentação: descompactar e dar dois cliques em INSTALAR.bat
(Windows), ou seguir os comandos do LEIA-ME.txt do zip.
"""

import argparse
import sys
import warnings
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))  # funciona sem "pip install -e ."

import libras  # noqa: E402
from libras import config  # noqa: E402
from libras.classificador import ErroClassificador, carregar_classificador  # noqa: E402

LEIA_ME = """LIBRAHIN - PACOTE DE DEMONSTRAÇÃO
=================================

Requisitos: Python 3.10 a 3.12 (recomendado 3.11) e uma webcam.
No Linux: sudo apt install python3-tk espeak-ng alsa-utils libegl1 libgles2

Windows, jeito fácil (precisa de internet só na instalação):

    1. Dois cliques em INSTALAR.bat (instala o Python, se faltar, e as bibliotecas).
       Se aparecer "O Windows protegeu o computador": Mais informações > Executar assim mesmo.
    2. Dois cliques no atalho "Librahin" da Área de Trabalho > opção 1.

Windows (PowerShell), passo a passo, dentro desta pasta:

    py -3.11 -m venv .venv
    .venv\\Scripts\\Activate.ps1
    python -m pip install --upgrade pip
    pip install -r requirements.txt
    python scripts/demonstracao/app.py

Linux/macOS:

    python3.11 -m venv .venv
    source .venv/bin/activate
    python -m pip install --upgrade pip
    pip install -r requirements.txt
    python scripts/demonstracao/app.py

Versão simples (janela do OpenCV): python scripts/demonstracao/executar.py

Modelo incluído: {modelo}
Sinais reconhecidos: {classes}
"""


def arquivos_do_pacote(raiz: Path) -> list[Path]:
    """Arquivos (relativos à raiz do projeto) que a aplicação precisa."""
    modulos = ("__init__",) + libras.MODULOS_NUCLEO + libras.MODULOS_APLICACAO
    arquivos = [Path("src/libras") / f"{m}.py" for m in modulos]
    arquivos += sorted(p.relative_to(raiz) for p in config.DIR_RECURSOS.glob("*") if p.is_file())  # ícone
    arquivos += sorted(p.relative_to(raiz) for p in (raiz / "scripts/demonstracao").glob("*.py"))
    arquivos.append(Path("requirements.txt"))
    if config.ARQ_FRASES.is_file():
        arquivos.append(config.ARQ_FRASES.relative_to(raiz))
    arquivos += [Path("INSTALAR.bat"), Path("Librahin.bat"), Path("librahin.sh")]
    arquivos += sorted(p.relative_to(raiz) for p in (raiz / "windows").glob("*.ps1"))
    for modelo in (config.ARQ_MODELO, config.ARQ_CLASSES, config.ARQ_MODELO_INFO,
                   config.ARQ_HAND_LANDMARKER, config.ARQ_POSE_LANDMARKER):
        if modelo.is_file():
            arquivos.append(modelo.relative_to(raiz))
    return arquivos


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--saida", type=Path, default=config.RAIZ_PROJETO / "dist" / "Librahin-demo.zip")
    parser.add_argument("--sem-modelo", action="store_true",
                        help="empacota mesmo sem modelo treinado (a aplicação só mostrará os landmarks)")
    args = parser.parse_args()

    raiz = config.RAIZ_PROJETO
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            classificador = carregar_classificador()
        modelo = f"{classificador.info.get('descricao')} (criado em {classificador.info.get('criado_em')})"
        classes = ", ".join(config.rotulo_exibicao(c) for c in classificador.classes)
    except ErroClassificador as erro:
        if not args.sem_modelo:
            print(f"[ERRO] {erro}\nTreine antes ou use --sem-modelo.", file=sys.stderr)
            return 1
        modelo, classes = "nenhum (só landmarks)", "-"

    arquivos = arquivos_do_pacote(raiz)
    faltando = [a for a in arquivos if not (raiz / a).is_file()]
    if faltando:
        print(f"[ERRO] arquivos não encontrados: {faltando}", file=sys.stderr)
        return 1

    args.saida.parent.mkdir(parents=True, exist_ok=True)
    prefixo = Path("Librahin-demo")
    with zipfile.ZipFile(args.saida, "w", zipfile.ZIP_DEFLATED) as pacote:
        for arquivo in arquivos:
            pacote.write(raiz / arquivo, (prefixo / arquivo).as_posix())
        pacote.writestr((prefixo / "LEIA-ME.txt").as_posix(), LEIA_ME.format(modelo=modelo, classes=classes))

    print(f"Pacote de demonstração: {args.saida} ({args.saida.stat().st_size / 1e6:.1f} MB)")
    for arquivo in arquivos:
        print(f"  {arquivo.as_posix()}")
    if not config.ARQ_HAND_LANDMARKER.is_file():
        print("[AVISO] modelos do MediaPipe não incluídos (serão baixados na 1ª execução). Para incluí-los,"
              " rode a aplicação uma vez antes de empacotar.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
