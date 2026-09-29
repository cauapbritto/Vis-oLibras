"""Reconhecimento frame a frame: sequência temporal -> features -> classificador -> estabilizador.

O vetor é gerado na versão de features DO MODELO carregado (1 = janela
posicional, 2 = + movimento), então modelos antigos continuam funcionando.

Junta as peças do tempo real num só lugar, sem câmera nem tela, para que o
executar.py fique simples e o fluxo possa ser testado com landmarks sintéticos.

    reconhecedor = Reconhecedor(carregar_classificador())
    estado = reconhecedor.processar(para_linha_bruta(resultado, agora), agora)
    if estado.palavra: ...   # palavra aceita (no máximo uma por gesto)
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

from libras import config
from libras.classificador import Classificador
from libras.estabilizador import Estabilizador
from libras.features import BufferJanela, ErroJanela


@dataclass
class EstadoReconhecimento:
    sinal: str | None = None       # última previsão do modelo (candidato)
    confianca: float = 0.0
    palavra: str | None = None     # palavra ACEITA neste frame (quase sempre None)
    aviso: str | None = None       # ex.: ombros não visíveis
    tempo_inferencia_ms: float = 0.0
    inferiu: bool = False          # o modelo rodou NESTE frame (tempo_inferencia_ms é deste frame)


class Reconhecedor:
    def __init__(self, classificador: Classificador, estabilizador: Estabilizador | None = None,
                 passo_inferencia: int = config.PASSO_INFERENCIA) -> None:
        self.classificador = classificador
        self.estabilizador = estabilizador or Estabilizador()
        self.passo_inferencia = max(1, passo_inferencia)
        self.buffer = BufferJanela()
        self._frames = 0
        self._ultimo = EstadoReconhecimento()

    def limpar(self) -> None:
        """Descarta a janela atual e o histórico do estabilizador."""
        self.buffer.limpar()
        self.estabilizador.reiniciar()
        self._ultimo = EstadoReconhecimento()

    def processar(self, linha: np.ndarray, agora: float) -> EstadoReconhecimento:
        """Chamar uma vez por frame com a linha de landmarks crus."""
        self.buffer.adicionar(linha)
        self._frames += 1
        if self._frames % self.passo_inferencia or not self.buffer.pronta():
            # Entre inferências, repete a última previsão (sem palavra nova).
            return EstadoReconhecimento(self._ultimo.sinal, self._ultimo.confianca, None,
                                        self._ultimo.aviso, self._ultimo.tempo_inferencia_ms)

        estado = EstadoReconhecimento()
        if self.buffer.pct_com_maos() < config.MIN_PCT_MAOS_JANELA:
            # Sem mãos: nem chama o modelo. Conta como "soltar o sinal".
            estado.sinal, estado.confianca = config.CLASSE_NADA, 1.0
        else:
            try:
                vetor = self.buffer.vetor(self.classificador.versao_features)
            except ErroJanela:
                estado.aviso = "Ombros não visíveis: afaste-se da câmera"
                self._ultimo = estado
                return estado
            inicio = time.perf_counter()
            estado.sinal, estado.confianca = self.classificador.prever(vetor)
            estado.tempo_inferencia_ms = (time.perf_counter() - inicio) * 1000
            estado.inferiu = True

        estado.palavra = self.estabilizador.atualizar(estado.sinal, estado.confianca, agora)
        if estado.palavra:
            # O fim do gesto aceito não deve contaminar a próxima janela.
            self.buffer.limpar()
        self._ultimo = estado
        return estado
