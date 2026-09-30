"""Gerenciador de sentença: organiza os sinais reconhecidos em uma sequência.

Independente da visão computacional: recebe palavras (strings) e tempos, então
funciona igual na interface gráfica, no modo OpenCV e nos testes.

Quatro estados diferentes, que a interface mostra separadamente:

    sinal_atual         o que o modelo está vendo AGORA (ainda não confirmado)
    ultimo_confirmado   a última palavra aceita pelo estabilizador
    palavras            a sequência confirmada da frase em construção
    frase_final         a última frase encerrada (a que é mostrada e falada)

O sistema NÃO traduz a gramática da Libras. A frase é a sequência de sinais
(glosa), na ordem em que foram feitos - "EU NOME CAUA" - e, se houver uma
`tabela` (traducao.TabelaFrases, lida do frases.txt), os trechos cadastrados
pelo grupo viram português ("EU NOME" -> "Meu nome é"). Sem tabela, tudo
funciona como antes: frase = glosa. As duas versões ficam disponíveis:

    frase_atual / frase_final   português onde houve frase cadastrada, glosa no resto
    glosa_atual / glosa_final   só a sequência de sinais

`regras` (lista de funções palavras -> palavras) continua disponível e é
aplicada antes da tabela.
"""

from __future__ import annotations

from typing import Callable

from libras import config
from libras.traducao import TabelaFrases, Traducao

RegraTexto = Callable[[list[str]], list[str]]


class GerenciadorSentenca:
    def __init__(
        self,
        ao_finalizar: Callable[[str], None] | None = None,
        regras: list[RegraTexto] | None = None,
        janela_repeticao_s: float = config.JANELA_REPETICAO_S,
        pausa_s: float = config.PAUSA_FRASE_S,
        max_palavras: int = config.MAX_PALAVRAS,
        tabela: TabelaFrases | None = None,
    ) -> None:
        """`ao_finalizar(texto)` é chamado sempre que uma frase é encerrada
        (manualmente, por pausa ou por estar cheia) - ex.: mostrar e falar.
        `texto` é a frase em português (= glosa sem tabela); a glosa fica em
        `glosa_final`."""
        self.ao_finalizar = ao_finalizar
        self.regras = regras or []
        self.tabela = tabela
        self.janela_repeticao_s = janela_repeticao_s
        self.pausa_s = pausa_s
        self.max_palavras = max_palavras

        self.sinal_atual: str | None = None
        self.confianca_atual = 0.0
        self.ultimo_confirmado: str | None = None
        self.momento_ultimo = float("-inf")
        self.palavras: list[str] = []
        self.frase_final = ""
        self.glosa_final = ""

    # --- sinal atual (não confirmado) --------------------------------------

    def atualizar_deteccao(self, sinal: str | None, confianca: float = 0.0) -> None:
        """O que o modelo está vendo agora. NÃO entra na sequência."""
        self.sinal_atual = None if sinal == config.CLASSE_NADA else sinal
        self.confianca_atual = confianca if self.sinal_atual else 0.0

    # --- sequência ----------------------------------------------------------

    def adicionar(self, palavra: str, agora: float) -> bool:
        """Acrescenta uma palavra confirmada. Devolve False se ela foi ignorada:
        vazia, "nenhum sinal" ou repetição involuntária (a mesma palavra de novo
        em menos de `janela_repeticao_s` segundos). O estabilizador já evita a
        maioria das repetições; esta é uma segunda proteção, independente dele."""
        palavra = palavra.strip() if palavra else ""
        if not palavra or palavra == config.CLASSE_NADA:
            return False
        if (palavra == self.ultimo_confirmado and self.palavras
                and agora - self.momento_ultimo < self.janela_repeticao_s):
            return False
        if len(self.palavras) >= self.max_palavras:
            self.finalizar()
        self.palavras.append(palavra)
        self.ultimo_confirmado, self.momento_ultimo = palavra, agora
        return True

    def remover_ultima(self) -> str | None:
        """Remove e devolve a última palavra da sequência (None se vazia)."""
        if not self.palavras:
            return None
        removida = self.palavras.pop()
        self.ultimo_confirmado = self.palavras[-1] if self.palavras else None
        return removida

    def limpar(self) -> None:
        """Limpa tudo: sequência, último confirmado e frase final."""
        self.palavras.clear()
        self.ultimo_confirmado = None
        self.momento_ultimo = float("-inf")
        self.frase_final = ""
        self.glosa_final = ""

    # --- frase ----------------------------------------------------------------

    def finalizar(self) -> str | None:
        """Encerra a frase em construção; devolve o texto (None se vazia)."""
        if not self.palavras:
            return None
        traducao = self.traducao_atual
        self.frase_final, self.glosa_final = traducao.texto, traducao.glosa
        self.palavras.clear()
        if self.ao_finalizar:
            self.ao_finalizar(self.frase_final)
        return self.frase_final

    def pausa_detectada(self, agora: float) -> bool:
        return bool(self.palavras) and agora - self.momento_ultimo >= self.pausa_s

    def verificar_pausa(self, agora: float) -> str | None:
        """Encerra a frase se passou `pausa_s` sem palavras novas."""
        return self.finalizar() if self.pausa_detectada(agora) else None

    # --- textos para a tela e para a voz --------------------------------------

    @property
    def sequencia(self) -> list[str]:
        """Palavras como devem aparecer na tela ("NAO" -> "NÃO")."""
        return [config.rotulo_exibicao(p) for p in self.palavras]

    @property
    def traducao_atual(self) -> Traducao:
        """A frase em construção nas duas versões (após as regras e a tabela)."""
        palavras = list(self.palavras)
        for regra in self.regras:
            palavras = regra(palavras)
        return (self.tabela or TabelaFrases()).traduzir(palavras)

    @property
    def frase_atual(self) -> str:
        """A frase em construção: português onde houver frase cadastrada, glosa no resto."""
        return self.traducao_atual.texto

    @property
    def glosa_atual(self) -> str:
        """A frase em construção como sequência de sinais (após as regras)."""
        return self.traducao_atual.glosa

    @staticmethod
    def texto_para_fala(frase: str) -> str:
        """Minúsculas: sintetizadores leem palavras em MAIÚSCULAS como siglas."""
        return frase.lower()
