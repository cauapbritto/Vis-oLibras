"""Sequência de palavras reconhecidas -> frase em português.

- Cada palavra aceita pelo estabilizador entra na sequência.
- Uma pausa de PAUSA_FRASE_S sem novas palavras encerra a frase (na Fase 6 ela
  será falada). ESPAÇO encerra na hora; BACKSPACE apaga a última; C limpa.
- config/frases.json traduz combinações conhecidas ("BOM DIA" -> "Bom dia!").
  O MVP não faz tradução gramatical: o resto é exibido palavra por palavra.
"""

from __future__ import annotations

import json
from pathlib import Path

from libras import config


def carregar_frases(caminho: Path = config.ARQ_FRASES) -> dict[tuple[str, ...], str]:
    """{("BOM", "DIA"): "Bom dia!", ...}. Arquivo ausente = dicionário vazio."""
    if not caminho.is_file():
        return {}
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    return {tuple(config.identificador_sinal(p) for p in chave.split()): texto
            for chave, texto in dados.items()}


def traduzir(palavras: list[str], frases: dict[tuple[str, ...], str]) -> str:
    """Substitui, da esquerda para a direita, a MAIOR combinação conhecida.
    ["OI", "BOM", "DIA", "EU"] -> "Oi, bom dia! Eu"."""
    maior = max((len(k) for k in frases), default=1)
    partes, i = [], 0
    while i < len(palavras):
        for tamanho in range(min(maior, len(palavras) - i), 0, -1):
            trecho = tuple(palavras[i:i + tamanho])
            if trecho in frases:
                partes.append(frases[trecho])
                i += tamanho
                break
        else:
            partes.append(config.rotulo_exibicao(palavras[i]).lower())
            i += 1
    texto = " ".join(partes)
    return texto[:1].upper() + texto[1:]


class Frase:
    def __init__(self, frases: dict[tuple[str, ...], str] | None = None,
                 pausa_s: float = config.PAUSA_FRASE_S, max_palavras: int = config.MAX_PALAVRAS) -> None:
        self.frases = carregar_frases() if frases is None else frases
        self.pausa_s = pausa_s
        self.max_palavras = max_palavras
        self.palavras: list[str] = []
        self.momento_ultima = 0.0
        self.ultima_frase = ""  # a última frase encerrada (continua visível na tela)

    def adicionar(self, palavra: str, agora: float) -> str | None:
        """Acrescenta a palavra. Se a frase já estava cheia, ela é encerrada antes
        e o texto dela é devolvido."""
        encerrada = self.finalizar() if len(self.palavras) >= self.max_palavras else None
        self.palavras.append(palavra)
        self.momento_ultima = agora
        return encerrada

    def remover_ultima(self) -> None:
        if self.palavras:
            self.palavras.pop()

    def limpar(self) -> None:
        self.palavras.clear()
        self.ultima_frase = ""

    def glosa(self) -> str:
        """Palavras como reconhecidas: 'OI · BOM · DIA'."""
        return " · ".join(config.rotulo_exibicao(p) for p in self.palavras)

    def texto(self) -> str:
        return traduzir(self.palavras, self.frases)

    def pausa_detectada(self, agora: float) -> bool:
        return bool(self.palavras) and agora - self.momento_ultima >= self.pausa_s

    def finalizar(self) -> str | None:
        """Encerra a frase atual e devolve o texto em português (None se vazia)."""
        if not self.palavras:
            return None
        self.ultima_frase = self.texto()
        self.palavras.clear()
        return self.ultima_frase
