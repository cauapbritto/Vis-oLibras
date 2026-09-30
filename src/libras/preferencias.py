"""Preferências da aplicação (janela Configurações), salvas em preferencias.json.

Só guarda o que a pessoa mudou na janela; o resto continua vindo do config.py.
O arquivo fica na pasta do projeto e fora do Git (cada computador tem o seu).

    preferencias.carregar()            # na abertura: aplica o arquivo no config
    preferencias.definir("taxa_fala", 200)   # muda, aplica e salva
    preferencias.restaurar_padrao()
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from libras import config


@dataclass(frozen=True)
class Campo:
    atributo: str                     # nome no config.py
    tipo: type
    minimo: float | None = None
    maximo: float | None = None
    opcoes: tuple[str, ...] = ()


CAMPOS = {
    "limiar_confianca": Campo("LIMIAR_CONFIANCA", float, 0.5, 0.95),
    "confirmacao_adaptativa": Campo("CONFIRMACAO_ADAPTATIVA", bool),
    "modo_leve": Campo("MODO_LEVE", str, opcoes=("auto", "ligado", "desligado")),
    "finalizar_por_pausa": Campo("FINALIZAR_POR_PAUSA", bool),
    "pausa_frase_s": Campo("PAUSA_FRASE_S", float, 1.0, 6.0),
    "taxa_fala": Campo("TAXA_FALA", int, 100, 260),
    "falar_cada_palavra": Campo("FALAR_CADA_PALAVRA", bool),
    "indice_camera": Campo("INDICE_CAMERA", int, 0, 9),
}
# Estado da aplicação que também vale guardar (não vem do config.py)
ESTADOS = {"verificacao_feita": False}

PADROES = {nome: getattr(config, campo.atributo) for nome, campo in CAMPOS.items()}
_estado: dict = dict(ESTADOS)


def _validar(nome: str, valor):
    """Valor convertido e dentro dos limites, ou ValueError."""
    campo = CAMPOS[nome]
    if campo.tipo is bool:
        if not isinstance(valor, bool):
            raise ValueError(f"{nome}: esperado verdadeiro/falso")
        return valor
    if campo.opcoes:
        if valor not in campo.opcoes:
            raise ValueError(f"{nome}: use {', '.join(campo.opcoes)}")
        return valor
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        raise ValueError(f"{nome}: esperado um número")
    valor = campo.tipo(valor)
    if not campo.minimo <= valor <= campo.maximo:
        raise ValueError(f"{nome}: fora do intervalo {campo.minimo} a {campo.maximo}")
    return valor


def valores() -> dict:
    """Valores atuais (do config) de todos os campos."""
    return {nome: getattr(config, campo.atributo) for nome, campo in CAMPOS.items()}


def estado(nome: str):
    return _estado.get(nome, ESTADOS.get(nome))


def carregar(caminho: Path | None = None) -> list[str]:
    """Lê o arquivo e aplica no config. Devolve avisos (valores inválidos são ignorados)."""
    caminho = Path(caminho or config.ARQ_PREFERENCIAS)
    if not caminho.is_file():
        return []
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, ValueError) as erro:
        return [f"{caminho.name} ilegível ({erro}); usando o config.py"]
    avisos = []
    for nome, valor in dados.items():
        if nome in ESTADOS:
            _estado[nome] = valor
        elif nome in CAMPOS:
            try:
                setattr(config, CAMPOS[nome].atributo, _validar(nome, valor))
            except ValueError as erro:
                avisos.append(str(erro))
        else:
            avisos.append(f"{nome}: opção desconhecida, ignorada")
    return avisos


def _salvar(caminho: Path | None = None) -> None:
    caminho = Path(caminho or config.ARQ_PREFERENCIAS)
    mudados = {nome: v for nome, v in valores().items() if v != PADROES[nome]}
    mudados.update({nome: v for nome, v in _estado.items() if v != ESTADOS[nome]})
    if mudados:
        caminho.write_text(json.dumps(mudados, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    elif caminho.exists():
        caminho.unlink()


def definir(nome: str, valor, caminho: Path | None = None) -> None:
    """Muda uma preferência (ou estado), aplica no config e salva."""
    if nome in ESTADOS:
        _estado[nome] = valor
    else:
        setattr(config, CAMPOS[nome].atributo, _validar(nome, valor))
    _salvar(caminho)


def restaurar_padrao(caminho: Path | None = None) -> None:
    """Volta todos os campos ao config.py (mantém o estado, ex.: verificação feita)."""
    for nome, campo in CAMPOS.items():
        setattr(config, campo.atributo, PADROES[nome])
    _salvar(caminho)
