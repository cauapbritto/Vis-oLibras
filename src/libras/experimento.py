"""Testes controlados do protótipo em tempo real (modo desenvolvimento).

Protocolo: cada participante faz cada sinal N vezes (ordem aleatória, com
semente registrada). Para cada tentativa:

    CONTAGEM   "Faça: NOME" + contagem regressiva (mãos abaixadas)
    EXECUÇÃO   no "JÁ!" o cronômetro começa; a tentativa termina na primeira
               palavra aceita pelo estabilizador ou após a janela de tempo
    RESULTADO  mostra o resultado por alguns segundos; D descarta a tentativa
               (ex.: o participante errou o sinal) e ela é refeita

O que é registrado (somente o que foi medido, nada é estimado ou preenchido):
    sinal_esperado, sinal_reconhecido ("(nenhum)" se nada foi aceito), acerto,
    confianca, tempo_resposta_s (do "JÁ!" até o reconhecimento),
    latencia_sistema_s (do 1º frame com mãos após o "JÁ!" até o reconhecimento),
    fps_medio e inferencia_ms_media durante a tentativa.

Cada tentativa é gravada no CSV assim que termina: se o programa fechar, nada
do que já foi medido se perde. `resumir()` calcula as métricas a partir das
linhas do CSV.
"""

from __future__ import annotations

import csv
import random
import statistics
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable

from libras import config

NENHUM = "(nenhum)"
COLUNAS = ["sessao", "participante", "tentativa", "sinal_esperado", "sinal_reconhecido", "acerto",
           "confianca", "tempo_resposta_s", "latencia_sistema_s", "fps_medio", "inferencia_ms_media",
           "inicio", "modelo"]

AGUARDANDO, CONTAGEM, EXECUCAO, RESULTADO, FIM = "aguardando", "contagem", "execucao", "resultado", "fim"


@dataclass
class Tentativa:
    sessao: str
    participante: str
    tentativa: int
    sinal_esperado: str
    sinal_reconhecido: str
    acerto: bool
    confianca: float | None
    tempo_resposta_s: float | None
    latencia_sistema_s: float | None
    fps_medio: float | None
    inferencia_ms_media: float | None
    inicio: str
    modelo: str


def plano_de_tentativas(sinais: list[str], repeticoes: int, semente: int, aleatorio: bool = True) -> list[str]:
    """Lista com cada sinal `repeticoes` vezes, embaralhada com a semente (reprodutível)."""
    plano = [s for s in sinais for _ in range(repeticoes)]
    if aleatorio:
        random.Random(semente).shuffle(plano)
    return plano


# -----------------------------------------------------------------------------
# CSV
# -----------------------------------------------------------------------------

def _formatar(valor) -> str:
    if valor is None:
        return ""
    if isinstance(valor, bool):
        return "1" if valor else "0"
    if isinstance(valor, float):
        return f"{valor:.4f}"
    return str(valor)


class RegistroCSV:
    """Acrescenta uma linha por tentativa, gravando no disco na hora."""

    def __init__(self, caminho: Path) -> None:
        self.caminho = caminho
        caminho.parent.mkdir(parents=True, exist_ok=True)
        if not caminho.is_file():
            with open(caminho, "w", newline="", encoding="utf-8") as arquivo:
                csv.writer(arquivo).writerow(COLUNAS)

    def adicionar(self, tentativa: Tentativa) -> None:
        with open(self.caminho, "a", newline="", encoding="utf-8") as arquivo:
            dados = asdict(tentativa)
            csv.writer(arquivo).writerow([_formatar(dados[c]) for c in COLUNAS])


def ler_csv(caminhos: Iterable[Path]) -> list[dict]:
    """Linhas de um ou mais CSVs de testes, com os tipos convertidos."""
    linhas = []
    for caminho in caminhos:
        with open(caminho, newline="", encoding="utf-8") as arquivo:
            for bruto in csv.DictReader(arquivo):
                linha = dict(bruto)
                linha["tentativa"] = int(linha["tentativa"])
                linha["acerto"] = linha["acerto"] == "1"
                for chave in ("confianca", "tempo_resposta_s", "latencia_sistema_s", "fps_medio",
                              "inferencia_ms_media"):
                    linha[chave] = float(linha[chave]) if linha.get(chave) else None
                linhas.append(linha)
    return linhas


# -----------------------------------------------------------------------------
# Máquina de estados de uma sessão (não conhece câmera nem tela)
# -----------------------------------------------------------------------------

@dataclass
class _Medicoes:
    inicio: float = 0.0
    inicio_texto: str = ""
    inicio_maos: float | None = None
    fps: list[float] = field(default_factory=list)
    inferencias: list[float] = field(default_factory=list)


class SessaoTeste:
    """Conduz as tentativas. Chame `atualizar()` a cada frame com o estado do
    reconhecimento; `ao_iniciar_tentativa()` é chamado no "JÁ!" (para zerar o
    estabilizador) e `ao_registrar(tentativa)` quando uma tentativa é confirmada."""

    def __init__(self, plano: list[str], participante: str, sessao: str, modelo: str,
                 ao_registrar: Callable[[Tentativa], None],
                 ao_iniciar_tentativa: Callable[[], None] | None = None,
                 contagem_s: float = config.TESTE_CONTAGEM_S,
                 janela_s: float = config.TESTE_JANELA_S,
                 resultado_s: float = config.TESTE_RESULTADO_S) -> None:
        self.pendentes = list(plano)
        self.total = len(plano)
        self.participante, self.sessao, self.modelo = participante, sessao, modelo
        self.ao_registrar = ao_registrar
        self.ao_iniciar_tentativa = ao_iniciar_tentativa
        self.contagem_s, self.janela_s, self.resultado_s = contagem_s, janela_s, resultado_s
        self.estado = AGUARDANDO
        self.registradas: list[Tentativa] = []
        self.atual: str | None = None
        self.resultado: Tentativa | None = None
        self.fim_fase = 0.0
        self._med = _Medicoes()

    @property
    def numero_atual(self) -> int:
        return len(self.registradas) + 1

    def iniciar(self, agora: float) -> None:
        """Começa (ou retoma) as tentativas."""
        if self.estado == AGUARDANDO and self.pendentes:
            self._proxima(agora)

    def pausar(self) -> None:
        """Interrompe a tentativa em andamento (ela volta para a fila, sem registro)."""
        if self.estado in (CONTAGEM, EXECUCAO) and self.atual:
            self.pendentes.insert(0, self.atual)
        if self.estado == RESULTADO:
            self._confirmar()
        if self.estado != FIM:
            self.estado = AGUARDANDO

    def descartar(self) -> bool:
        """Durante o RESULTADO: descarta a tentativa; o mesmo sinal é refeito."""
        if self.estado != RESULTADO or self.resultado is None:
            return False
        self.pendentes.insert(0, self.resultado.sinal_esperado)
        self.resultado = None
        self.fim_fase = 0.0  # passa para a próxima tentativa no próximo frame
        return True

    def atualizar(self, agora: float, palavra: str | None, confianca: float, tem_maos: bool,
                  fps: float, inferencia_ms: float) -> None:
        if self.estado == CONTAGEM and agora >= self.fim_fase:
            self.estado = EXECUCAO
            self._med = _Medicoes(inicio=agora, inicio_texto=datetime.now().isoformat(timespec="seconds"))
            if self.ao_iniciar_tentativa:
                self.ao_iniciar_tentativa()
            return  # a palavra deste frame ainda pertence ao período anterior ao "JÁ!"

        if self.estado == EXECUCAO:
            if fps > 0:
                self._med.fps.append(fps)
            if inferencia_ms > 0:
                self._med.inferencias.append(inferencia_ms)
            if tem_maos and self._med.inicio_maos is None:
                self._med.inicio_maos = agora
            if palavra:
                self._encerrar(agora, palavra, confianca)
            elif agora - self._med.inicio >= self.janela_s:
                self._encerrar(agora, None, None)
            return

        if self.estado == RESULTADO and agora >= self.fim_fase:
            self._confirmar()
            if self.pendentes:
                self._proxima(agora)
            else:
                self.estado = FIM

    # --- internos --------------------------------------------------------------

    def _proxima(self, agora: float) -> None:
        self.atual = self.pendentes.pop(0)
        self.estado = CONTAGEM
        self.fim_fase = agora + self.contagem_s

    def _encerrar(self, agora: float, palavra: str | None, confianca: float | None) -> None:
        esperado = self.atual
        reconhecido = palavra or NENHUM
        if esperado == config.CLASSE_NADA:  # tentativa de "não sinalizar": acerto = nada aceito
            acerto = palavra is None
        else:
            acerto = palavra == esperado
        med = self._med
        inicio_maos = med.inicio_maos if med.inicio_maos is not None else med.inicio
        self.resultado = Tentativa(
            sessao=self.sessao, participante=self.participante, tentativa=self.numero_atual,
            sinal_esperado=esperado, sinal_reconhecido=reconhecido, acerto=acerto,
            confianca=confianca if palavra else None,
            tempo_resposta_s=agora - med.inicio if palavra else None,
            latencia_sistema_s=max(agora - inicio_maos, 0.0) if palavra else None,
            fps_medio=statistics.fmean(med.fps) if med.fps else None,
            inferencia_ms_media=statistics.fmean(med.inferencias) if med.inferencias else None,
            inicio=med.inicio_texto, modelo=self.modelo,
        )
        self.estado = RESULTADO
        self.fim_fase = agora + self.resultado_s

    def _confirmar(self) -> None:
        if self.resultado is not None:
            self.registradas.append(self.resultado)
            self.ao_registrar(self.resultado)
            self.resultado = None


# -----------------------------------------------------------------------------
# Resumo estatístico
# -----------------------------------------------------------------------------

def _estatisticas(valores: list[float]) -> dict:
    if not valores:
        return {"n": 0}
    ordenados = sorted(valores)
    p95 = ordenados[min(len(ordenados) - 1, int(round(0.95 * (len(ordenados) - 1))))]
    return {"n": len(valores), "media": statistics.fmean(valores), "mediana": statistics.median(valores),
            "desvio": statistics.stdev(valores) if len(valores) > 1 else 0.0,
            "p95": p95, "minimo": ordenados[0], "maximo": ordenados[-1]}


def resumir(linhas: list[dict]) -> dict:
    """Métricas calculadas SOMENTE a partir das tentativas registradas."""
    if not linhas:
        raise ValueError("nenhuma tentativa registrada: não há o que resumir")

    esperados = [l["sinal_esperado"] for l in linhas]
    reconhecidos = [l["sinal_reconhecido"] for l in linhas]
    # "_NADA" esperado e nada reconhecido contam como a mesma classe
    previstos = [config.CLASSE_NADA if (e == config.CLASSE_NADA and r == NENHUM) else r
                 for e, r in zip(esperados, reconhecidos)]
    classes = [c for c in config.CLASSES if c in set(esperados)] + \
              sorted(set(esperados) - set(config.CLASSES))
    rotulos_matriz = classes + sorted(set(previstos) - set(classes))

    por_classe = {}
    for classe in classes:
        vp = sum(1 for e, p in zip(esperados, previstos) if e == classe and p == classe)
        fp = sum(1 for e, p in zip(esperados, previstos) if e != classe and p == classe)
        fn = sum(1 for e, p in zip(esperados, previstos) if e == classe and p != classe)
        precisao = vp / (vp + fp) if vp + fp else 0.0
        recall = vp / (vp + fn) if vp + fn else 0.0
        f1 = 2 * precisao * recall / (precisao + recall) if precisao + recall else 0.0
        confusoes = Counter(p for e, p in zip(esperados, previstos) if e == classe and p != classe)
        por_classe[classe] = {
            "tentativas": vp + fn, "acertos": vp, "erros": fn,
            "nao_reconhecidos": confusoes.get(NENHUM, 0),
            "confundido_com": dict(confusoes.most_common()),
            "precision": precisao, "recall": recall, "f1": f1,
        }

    matriz = [[sum(1 for e, p in zip(esperados, previstos) if e == real and p == prev)
               for prev in rotulos_matriz] for real in classes]

    acertos_por_pessoa = defaultdict(list)
    for linha in linhas:
        acertos_por_pessoa[linha["participante"]].append(linha["acerto"])

    def coluna(nome, so_acertos=False):
        return [l[nome] for l in linhas if l[nome] is not None and (l["acerto"] or not so_acertos)]

    return {
        "tentativas": len(linhas),
        "participantes": sorted(acertos_por_pessoa),
        "sessoes": sorted({l["sessao"] for l in linhas}),
        "accuracy": sum(l["acerto"] for l in linhas) / len(linhas),
        "precision_macro": statistics.fmean(c["precision"] for c in por_classe.values()),
        "recall_macro": statistics.fmean(c["recall"] for c in por_classe.values()),
        "f1_macro": statistics.fmean(c["f1"] for c in por_classe.values()),
        "por_classe": por_classe,
        "matriz_confusao": {"linhas_sinal_real": classes, "colunas_reconhecido": rotulos_matriz,
                            "valores": matriz},
        "tempo_resposta_s_acertos": _estatisticas(coluna("tempo_resposta_s", so_acertos=True)),
        "latencia_sistema_s_acertos": _estatisticas(coluna("latencia_sistema_s", so_acertos=True)),
        "fps": _estatisticas(coluna("fps_medio")),
        "inferencia_ms": _estatisticas(coluna("inferencia_ms_media")),
        "accuracy_por_participante": {p: sum(a) / len(a) for p, a in sorted(acertos_por_pessoa.items())},
        "modelos": sorted({l["modelo"] for l in linhas}),
    }
