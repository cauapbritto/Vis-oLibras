"""Separação entre MODO USUÁRIO (aplicação) e MODO DESENVOLVIMENTO (treino).

Regras (ver src/libras/__init__.py):
- núcleo só importa o núcleo;
- aplicação só importa núcleo + aplicação;
- nenhum módulo do núcleo ou da aplicação importa bibliotecas de treino.
"""

import ast
import re
import subprocess
import sys
from pathlib import Path

import libras

RAIZ = Path(__file__).resolve().parents[1]
PACOTE = RAIZ / "src" / "libras"
BIBLIOTECAS_DE_TREINO = {"matplotlib", "pytest"}


def _imports(modulo: str) -> tuple[set[str], set[str]]:
    """(módulos do libras, bibliotecas externas) importados por um módulo, em qualquer lugar."""
    arvore = ast.parse((PACOTE / f"{modulo}.py").read_text(encoding="utf-8"))
    internos, externos = set(), set()
    for no in ast.walk(arvore):
        nomes = []
        if isinstance(no, ast.Import):
            nomes = [a.name for a in no.names]
        elif isinstance(no, ast.ImportFrom) and no.module:
            nomes = [no.module] + ([f"{no.module}.{a.name}" for a in no.names] if no.module == "libras" else [])
        for nome in nomes:
            partes = nome.split(".")
            if partes[0] == "libras":
                if len(partes) > 1 and partes[1] in _todos():
                    internos.add(partes[1])
            else:
                externos.add(partes[0])
    return internos, externos


def _todos() -> set[str]:
    return set(libras.MODULOS_NUCLEO) | set(libras.MODULOS_APLICACAO) | set(libras.MODULOS_DESENVOLVIMENTO)


def test_todo_modulo_tem_uma_camada():
    arquivos = {p.stem for p in PACOTE.glob("*.py")} - {"__init__"}
    assert arquivos == _todos(), "adicione o módulo novo a uma das listas em libras/__init__.py"
    camadas = [set(libras.MODULOS_NUCLEO), set(libras.MODULOS_APLICACAO), set(libras.MODULOS_DESENVOLVIMENTO)]
    assert sum(len(c) for c in camadas) == len(set().union(*camadas))  # nenhum em duas camadas


def test_nucleo_so_importa_o_nucleo():
    for modulo in libras.MODULOS_NUCLEO:
        internos, externos = _imports(modulo)
        assert internos <= set(libras.MODULOS_NUCLEO), f"{modulo} importa {internos - set(libras.MODULOS_NUCLEO)}"
        assert not externos & BIBLIOTECAS_DE_TREINO, f"{modulo} importa {externos & BIBLIOTECAS_DE_TREINO}"


def test_aplicacao_nao_depende_do_desenvolvimento():
    permitidos = set(libras.MODULOS_NUCLEO) | set(libras.MODULOS_APLICACAO)
    for modulo in libras.MODULOS_APLICACAO:
        internos, externos = _imports(modulo)
        assert internos <= permitidos, f"{modulo} importa {internos - permitidos} (modo desenvolvimento)"
        assert not externos & BIBLIOTECAS_DE_TREINO, f"{modulo} importa {externos & BIBLIOTECAS_DE_TREINO}"


def test_carregar_a_aplicacao_nao_carrega_modulos_de_treino():
    codigo = ("import sys, libras.pipeline, libras.captura, libras.frase, libras.voz, libras.classificador;"
              "print(sorted(m for m in sys.modules if m.startswith('libras.')))")
    saida = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True, check=True).stdout
    for modulo in libras.MODULOS_DESENVOLVIMENTO:
        assert f"libras.{modulo}" not in saida


def _requisitos(arquivo: str) -> set[str]:
    linhas = (RAIZ / arquivo).read_text(encoding="utf-8").splitlines()
    return {l.strip() for l in linhas if l.strip() and not l.startswith(("#", "-r"))}


def test_requirements_e_pyproject_iguais():
    texto = (RAIZ / "pyproject.toml").read_text(encoding="utf-8")
    dependencias = set(re.findall(r'"([^"]+)"', texto.split("dependencies = [")[1].split("]")[0]))
    desenvolvimento = set(re.findall(r'"([^"]+)"', texto.split("desenvolvimento = [")[1].split("]")[0]))
    assert dependencias == _requisitos("requirements.txt")
    assert desenvolvimento == _requisitos("requirements-dev.txt")


def test_aplicacao_nao_exige_bibliotecas_de_treino():
    nomes = {re.split(r"[<>=]", r)[0] for r in _requisitos("requirements.txt")}
    assert not nomes & BIBLIOTECAS_DE_TREINO
    assert "opencv-python" not in nomes  # conflita com o opencv-contrib-python do MediaPipe


def test_pacote_de_demonstracao_so_leva_o_necessario(tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "empacotar_app", RAIZ / "scripts" / "desenvolvimento" / "empacotar_app.py")
    empacotar = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(empacotar)
    arquivos = {a.as_posix() for a in empacotar.arquivos_do_pacote(RAIZ)}
    assert "src/libras/interface.py" in arquivos and "scripts/demonstracao/app.py" in arquivos
    assert "requirements.txt" in arquivos
    assert {"INSTALAR.bat", "Vis-oLibras.bat", "windows/instalar.ps1", "windows/menu.ps1",
            "windows/comum.ps1"} <= arquivos
    for proibido in ("src/libras/dataset.py", "src/libras/avaliacao.py", "src/libras/experimento.py",
                     "requirements-dev.txt"):
        assert proibido not in arquivos
    assert not any(a.startswith(("data/", "reports/", "tests/", "scripts/desenvolvimento/")) for a in arquivos)


def test_instalador_windows_tem_finais_de_linha_do_windows():
    """.bat com final de linha do Linux pode quebrar no cmd; o .gitattributes garante CRLF."""
    for arquivo in ("INSTALAR.bat", "Vis-oLibras.bat", *sorted((RAIZ / "windows").glob("*.ps1"))):
        conteudo = (RAIZ / arquivo).read_bytes()
        assert b"\n" in conteudo and conteudo.count(b"\n") == conteudo.count(b"\r\n"), arquivo
