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
from collections import deque
from dataclasses import dataclass

import numpy as np

from libras import config
from libras.classificador import Classificador
from libras.estabilizador import Estabilizador
from libras.features import BufferJanela, ErroJanela, referencia_corpo


@dataclass
class EstadoReconhecimento:
    sinal: str | None = None       # última previsão do modelo (candidato)
    confianca: float = 0.0
    palavra: str | None = None     # palavra ACEITA neste frame (quase sempre None)
    aviso: str | None = None       # ex.: ombros não visíveis
    tempo_inferencia_ms: float = 0.0
    inferiu: bool = False          # o modelo rodou NESTE frame (tempo_inferencia_ms é deste frame)
    em_movimento: bool = False     # as mãos estão se mexendo (a pessoa está sinalizando)


INTERVALO_VELOCIDADE_S = 0.2  # intervalo usado para medir a velocidade das mãos


class Reconhecedor:
    def __init__(self, classificador: Classificador, estabilizador: Estabilizador | None = None,
                 passo_inferencia: int = config.PASSO_INFERENCIA) -> None:
        self.classificador = classificador
        self.estabilizador = estabilizador or Estabilizador()
        self.passo_inferencia = max(1, passo_inferencia)
        self.buffer = BufferJanela()
        self._frames = 0
        self._ultimo = EstadoReconhecimento()
        self.gatilho_fim_movimento = config.GATILHO_FIM_MOVIMENTO
        self._recentes: deque[np.ndarray] = deque()
        self._velocidade = 0.0      # punho, em larguras de ombro por segundo
        self._em_movimento = False

    def limpar(self) -> None:
        """Descarta a janela atual e o histórico do estabilizador."""
        self.buffer.limpar()
        self.estabilizador.reiniciar()
        self._ultimo = EstadoReconhecimento()
        self._recentes.clear()
        self._velocidade, self._em_movimento = 0.0, False

    def _parou_de_mexer(self, linha: np.ndarray) -> bool:
        """True no frame em que as mãos, depois de se mexerem, param: o sinal
        provavelmente terminou e está inteiro na janela. A velocidade é medida
        pelo deslocamento do punho em ~0,2 s (e não quadro a quadro), para o
        tremor natural dos pontos não parecer movimento."""
        agora = float(linha[config.COL_TIMESTAMP])
        self._recentes.append(linha)
        while len(self._recentes) > 2 and agora - float(self._recentes[1][config.COL_TIMESTAMP]) >= INTERVALO_VELOCIDADE_S:
            self._recentes.popleft()
        anterior = self._recentes[0]
        dt = agora - float(anterior[config.COL_TIMESTAMP])
        referencia = referencia_corpo(linha)
        if referencia is None or dt < INTERVALO_VELOCIDADE_S * 0.75:
            return False
        _, largura_ombros = referencia
        deslocamento = 0.0
        for i, colunas in enumerate((config.COL_MAO_DIREITA, config.COL_MAO_ESQUERDA)):
            flag = config.COL_FLAGS.start + i
            if linha[flag] > 0.5 and anterior[flag] > 0.5:
                deslocamento = max(deslocamento, float(np.linalg.norm(linha[colunas][:2] - anterior[colunas][:2])))
        self._velocidade = deslocamento / largura_ombros / dt
        if self._velocidade > config.VELOCIDADE_MOVIMENTO:
            self._em_movimento = True
        elif self._em_movimento and self._velocidade < config.VELOCIDADE_PARADA:
            self._em_movimento = False
            return True
        return False

    def processar(self, linha: np.ndarray, agora: float) -> EstadoReconhecimento:
        """Chamar uma vez por frame com a linha de landmarks crus."""
        self.buffer.adicionar(linha)
        self._frames += 1
        parou = self._parou_de_mexer(linha) and self.gatilho_fim_movimento
        mexendo = self._velocidade > config.VELOCIDADE_PARADA
        if parou:
            self._frames = 0  # o próximo passo regular conta a partir daqui
        if (self._frames % self.passo_inferencia and not parou) or not self.buffer.pronta():
            # Entre inferências, repete a última previsão (sem palavra nova).
            return EstadoReconhecimento(self._ultimo.sinal, self._ultimo.confianca, None,
                                        self._ultimo.aviso, self._ultimo.tempo_inferencia_ms,
                                        em_movimento=mexendo)

        estado = EstadoReconhecimento(em_movimento=mexendo)
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
