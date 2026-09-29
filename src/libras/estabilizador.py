"""Estabilização temporal (anti-repetição).

O classificador roda várias vezes por segundo sobre janelas que se sobrepõem;
sem este filtro, um único NOME viraria "NOME NOME NOME NOME...". Regras (valores
em config.py):

1. Confiança mínima (LIMIAR_CONFIANCA).
2. Estabilidade: o mesmo sinal em N_CONSECUTIVAS previsões seguidas.
3. Cooldown geral (COOLDOWN_S) depois de qualquer palavra aceita.
4. Mesma palavra de novo: só depois de COOLDOWN_MESMO_SINAL_S e, com
   EXIGIR_LIBERACAO, depois de o sinal ser "solto" (_NADA / mãos fora da imagem).

Não depende de câmera: recebe (sinal, confiança, tempo) e devolve a palavra
aceita ou None, então é fácil de testar.
"""

from __future__ import annotations

from libras import config


class Estabilizador:
    def __init__(
        self,
        limiar: float = config.LIMIAR_CONFIANCA,
        n_consecutivas: int = config.N_CONSECUTIVAS,
        cooldown_s: float = config.COOLDOWN_S,
        cooldown_mesmo_sinal_s: float = config.COOLDOWN_MESMO_SINAL_S,
        exigir_liberacao: bool = config.EXIGIR_LIBERACAO,
        classe_nada: str = config.CLASSE_NADA,
    ) -> None:
        self.limiar = limiar
        self.n_consecutivas = max(1, n_consecutivas)
        self.cooldown_s = cooldown_s
        self.cooldown_mesmo_sinal_s = cooldown_mesmo_sinal_s
        self.exigir_liberacao = exigir_liberacao
        self.classe_nada = classe_nada
        self.reiniciar()

    def reiniciar(self) -> None:
        """Esquece tudo (usado ao limpar a sequência)."""
        self.candidato: str | None = None
        self.contagem = 0
        self.ultima_palavra: str | None = None
        self.momento_ultima = float("-inf")
        self.liberado = True

    def em_cooldown(self, agora: float) -> bool:
        return agora - self.momento_ultima < self.cooldown_s

    @property
    def progresso(self) -> float:
        """0 a 1: quanto falta para o candidato atual ser aceito (para a tela)."""
        return min(self.contagem / self.n_consecutivas, 1.0)

    def atualizar(self, sinal: str, confianca: float, agora: float) -> str | None:
        """Recebe uma previsão; devolve a palavra aceita ou None."""
        if sinal == self.classe_nada:
            self.liberado = True  # a pessoa "soltou" o sinal
            self.candidato, self.contagem = None, 0
            return None
        if confianca < self.limiar:
            self.candidato, self.contagem = None, 0
            return None

        if sinal == self.candidato:
            self.contagem += 1
        else:
            self.candidato, self.contagem = sinal, 1
        if self.contagem < self.n_consecutivas or self.em_cooldown(agora):
            return None

        if sinal == self.ultima_palavra:
            if agora - self.momento_ultima < self.cooldown_mesmo_sinal_s:
                return None
            if self.exigir_liberacao and not self.liberado:
                return None

        self.ultima_palavra, self.momento_ultima = sinal, agora
        self.liberado = False
        self.candidato, self.contagem = None, 0
        return sinal
