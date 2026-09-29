"""Dataset de landmarks: gravar, ler, validar e analisar amostras.

Organização em disco (ver docs/ARQUITETURA.md, seção 6):

    data/raw/<SINAL>/<pessoa>_<data>_<hora>.npy   -> (F, config.TAM_FRAME_BRUTO) float32
    data/metadata.csv                             -> uma linha por amostra

As regras de validação ficam aqui e são as MESMAS na coleta (para descartar
amostras ruins na hora) e na análise do dataset (para encontrar as que passaram).
"""

from __future__ import annotations

import csv
import hashlib
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np

from libras import config
from libras.features import ErroJanela, janela_para_vetor, referencia_corpo

COLUNAS_METADATA = [
    "arquivo", "sinal", "pessoa", "data_hora", "num_frames",
    "fps_medio", "pct_frames_com_mao", "pct_frames_com_ombros",
]

PERFIS_MAOS = ("ambas", "direita", "esquerda", "nenhuma")

_PADRAO_PESSOA = re.compile(r"^[a-z0-9]+$")


# -----------------------------------------------------------------------------
# Estatísticas e validação de uma amostra
# -----------------------------------------------------------------------------

def estatisticas_amostra(frames: np.ndarray) -> dict[str, float]:
    """Números usados na validação, no metadata.csv e na análise."""
    tempos = frames[:, config.COL_TIMESTAMP]
    flags = frames[:, config.COL_FLAGS]
    duracao = float(tempos[-1] - tempos[0]) if len(frames) > 1 else 0.0
    return {
        "num_frames": len(frames),
        "duracao": duracao,
        "fps_medio": (len(frames) - 1) / duracao if duracao > 0 else 0.0,
        "pct_frames_com_mao": float((flags.max(axis=1) > 0.5).mean()),
        "pct_mao_direita": float((flags[:, 0] > 0.5).mean()),
        "pct_mao_esquerda": float((flags[:, 1] > 0.5).mean()),
        "pct_frames_com_ombros": float(np.mean([referencia_corpo(l) is not None for l in frames])),
    }


def perfil_maos(estatisticas: dict[str, float]) -> str:
    """Quais mãos aparecem na maior parte da amostra: ambas, direita, esquerda ou nenhuma."""
    direita = estatisticas["pct_mao_direita"] > 0.5
    esquerda = estatisticas["pct_mao_esquerda"] > 0.5
    if direita and esquerda:
        return "ambas"
    return "direita" if direita else "esquerda" if esquerda else "nenhuma"


def validar_amostra(frames: np.ndarray, sinal: str) -> list[str]:
    """Lista de problemas da amostra (vazia = amostra válida)."""
    if frames.ndim != 2 or frames.shape[1] != config.TAM_FRAME_BRUTO:
        return [f"formato {frames.shape}, esperado (F, {config.TAM_FRAME_BRUTO})"]
    if not np.isfinite(frames).all():
        return ["contém valores inválidos (NaN/infinito)"]
    if len(frames) < config.MIN_FRAMES_AMOSTRA:
        return [f"poucos frames ({len(frames)} < {config.MIN_FRAMES_AMOSTRA}); a câmera está lenta"]

    problemas = []
    est = estatisticas_amostra(frames)
    if est["duracao"] < 0.8 * config.DURACAO_AMOSTRA:
        problemas.append(f"duração curta ({est['duracao']:.2f}s)")
    if np.any(np.diff(frames[:, config.COL_TIMESTAMP]) <= 0):
        problemas.append("timestamps fora de ordem")
    if sinal != config.CLASSE_NADA and est["pct_frames_com_mao"] < config.MIN_PCT_FRAMES_COM_MAO:
        problemas.append(f"mãos em só {est['pct_frames_com_mao']:.0%} dos frames")
    if est["pct_frames_com_ombros"] < config.MIN_PCT_FRAMES_COM_OMBROS:
        problemas.append(f"ombros visíveis em só {est['pct_frames_com_ombros']:.0%} dos frames; afaste-se da câmera")
    if not problemas:
        try:
            vetor = janela_para_vetor(frames)
        except ErroJanela as erro:
            problemas.append(f"não gera vetor: {erro}")
        else:
            if vetor.shape != (config.TAM_FEATURES_JANELA,):
                problemas.append(f"vetor com tamanho {vetor.size}, esperado {config.TAM_FEATURES_JANELA}")
    return problemas


# -----------------------------------------------------------------------------
# Gravação e leitura
# -----------------------------------------------------------------------------

def validar_pessoa(nome: str) -> str:
    """Nome da pessoa vira parte do nome do arquivo: só letras minúsculas e números."""
    nome = config.identificador_sinal(nome).lower()
    if not _PADRAO_PESSOA.match(nome):
        raise ValueError("use só letras e números no nome da pessoa (ex.: ana, joao2)")
    return nome


def pessoa_do_arquivo(caminho: Path) -> str:
    return caminho.stem.split("_", 1)[0]


def caminho_relativo(caminho: Path) -> str:
    """Caminho relativo à pasta data/, com '/', igual em qualquer sistema."""
    return caminho.resolve().relative_to(config.DIR_DATA.resolve()).as_posix()


def listar_amostras(sinal: str | None = None) -> list[Path]:
    """Arquivos .npy gravados (de um sinal ou de todos), em ordem."""
    padrao = f"{sinal}/*.npy" if sinal else "*/*.npy"
    return sorted(config.DIR_RAW.glob(padrao))


def contar_amostras(sinal: str, pessoa: str | None = None) -> int:
    return sum(1 for c in listar_amostras(sinal) if pessoa is None or pessoa_do_arquivo(c) == pessoa)


def carregar_metadata() -> list[dict[str, str]]:
    if not config.ARQ_METADATA.is_file():
        return []
    with open(config.ARQ_METADATA, newline="", encoding="utf-8") as arquivo:
        return list(csv.DictReader(arquivo))


def _escrever_metadata(linhas: list[dict[str, str]]) -> None:
    config.ARQ_METADATA.parent.mkdir(parents=True, exist_ok=True)
    with open(config.ARQ_METADATA, "w", newline="", encoding="utf-8") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=COLUNAS_METADATA, extrasaction="ignore")
        escritor.writeheader()
        escritor.writerows(linhas)


def salvar_amostra(frames: np.ndarray, sinal: str, pessoa: str) -> Path:
    """Grava a amostra em data/raw/<sinal>/ e acrescenta a linha no metadata.csv."""
    agora = datetime.now()
    pasta = config.DIR_RAW / sinal
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = pasta / f"{pessoa}_{agora:%Y%m%d_%H%M%S_%f}.npy"
    np.save(caminho, frames.astype(np.float32))

    est = estatisticas_amostra(frames)
    linha = {
        "arquivo": caminho_relativo(caminho),
        "sinal": sinal,
        "pessoa": pessoa,
        "data_hora": agora.isoformat(timespec="seconds"),
        "num_frames": est["num_frames"],
        "fps_medio": f"{est['fps_medio']:.1f}",
        "pct_frames_com_mao": f"{est['pct_frames_com_mao']:.2f}",
        "pct_frames_com_ombros": f"{est['pct_frames_com_ombros']:.2f}",
    }
    novo = not config.ARQ_METADATA.is_file()
    config.ARQ_METADATA.parent.mkdir(parents=True, exist_ok=True)
    with open(config.ARQ_METADATA, "a", newline="", encoding="utf-8") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=COLUNAS_METADATA)
        if novo:
            escritor.writeheader()
        escritor.writerow(linha)
    return caminho


def remover_amostra(caminho: Path) -> None:
    """Apaga o arquivo e a linha correspondente no metadata.csv."""
    relativo = caminho_relativo(caminho)
    caminho.unlink(missing_ok=True)
    linhas = carregar_metadata()
    restantes = [l for l in linhas if l.get("arquivo") != relativo]
    if len(restantes) != len(linhas):
        _escrever_metadata(restantes)


# -----------------------------------------------------------------------------
# Análise do dataset inteiro
# -----------------------------------------------------------------------------

@dataclass
class Amostra:
    arquivo: str                   # relativo a data/
    sinal: str
    pessoa: str
    problemas: list[str] = field(default_factory=list)
    perfil: str = ""
    vetor: np.ndarray | None = None

    @property
    def valida(self) -> bool:
        return not self.problemas


@dataclass
class RelatorioDataset:
    amostras: list[Amostra]
    inconsistencias: list[str]                     # problemas de organização do dataset
    alertas: list[tuple[str, str]]                 # (arquivo, motivo): suspeitas, não erros
    tamanhos_vetor: set[int]
    similaridade: tuple[list[str], np.ndarray] | None  # classes, matriz de similaridade

    def validas(self, sinal: str | None = None) -> list[Amostra]:
        return [a for a in self.amostras if a.valida and (sinal is None or a.sinal == sinal)]

    def invalidas(self) -> list[Amostra]:
        return [a for a in self.amostras if not a.valida]

    def contagem(self, sinal: str) -> int:
        return len(self.validas(sinal))

    def pessoas(self, sinal: str) -> Counter:
        return Counter(a.pessoa for a in self.validas(sinal))

    def perfis(self, sinal: str) -> Counter:
        return Counter(a.perfil for a in self.validas(sinal))

    def classes_com_poucas_amostras(self) -> list[str]:
        return [c for c in config.CLASSES if self.contagem(c) < config.MIN_AMOSTRAS_POR_CLASSE]


def _verificar_organizacao(inconsistencias: list[str]) -> None:
    """Pastas desconhecidas, arquivos estranhos e divergências com o metadata.csv."""
    if not config.DIR_RAW.is_dir():
        inconsistencias.append(f"pasta {config.DIR_RAW} não existe")
        return
    for pasta in sorted(p for p in config.DIR_RAW.iterdir() if p.is_dir()):
        if pasta.name not in config.CLASSES:
            n = len(list(pasta.glob("*.npy")))
            inconsistencias.append(f"pasta data/raw/{pasta.name}/ não está em config.CLASSES ({n} amostras ignoradas)")
        for arquivo in pasta.iterdir():
            if arquivo.suffix != ".npy" and arquivo.name != ".gitkeep":
                inconsistencias.append(f"arquivo inesperado: {caminho_relativo(arquivo)}")
    for classe in config.CLASSES:
        if not (config.DIR_RAW / classe).is_dir():
            inconsistencias.append(f"classe {classe} não tem pasta em data/raw/")

    no_disco = {caminho_relativo(c) for c in listar_amostras()}
    metadata = carregar_metadata()
    no_metadata = Counter(l.get("arquivo", "") for l in metadata)
    for arquivo in sorted(no_disco - set(no_metadata)):
        inconsistencias.append(f"{arquivo} não está no metadata.csv")
    for arquivo in sorted(set(no_metadata) - no_disco):
        inconsistencias.append(f"metadata.csv cita {arquivo}, que não existe")
    for arquivo, vezes in no_metadata.items():
        if vezes > 1:
            inconsistencias.append(f"{arquivo} aparece {vezes} vezes no metadata.csv")
    for linha in metadata:
        pasta = linha.get("arquivo", "").split("/")[1:2]
        if pasta and pasta[0] != linha.get("sinal"):
            inconsistencias.append(f"{linha['arquivo']}: sinal '{linha.get('sinal')}' no metadata, mas está na pasta {pasta[0]}")


def _outliers(amostras: list[Amostra]) -> list[Amostra]:
    """Amostras muito distantes da mediana da própria classe (sinal gravado errado?)."""
    if len(amostras) < 5:
        return []
    vetores = np.stack([a.vetor for a in amostras])
    distancias = np.linalg.norm(vetores - np.median(vetores, axis=0), axis=1)
    mediana = np.median(distancias)
    mad = 1.4826 * np.median(np.abs(distancias - mediana))
    if mad == 0:
        return []
    return [a for a, d in zip(amostras, distancias) if d > mediana + config.LIMIAR_OUTLIER * mad]


def _similaridade_classes(relatorio: RelatorioDataset) -> tuple[list[str], np.ndarray] | None:
    """Similaridade de cosseno entre as médias das classes (com as features padronizadas).
    Valores altos indicam sinais que o modelo pode confundir."""
    classes = [c for c in config.CLASSES if relatorio.contagem(c) > 0]
    if len(classes) < 2:
        return None
    todas = np.stack([a.vetor for a in relatorio.validas()])
    media, desvio = todas.mean(axis=0), todas.std(axis=0) + 1e-6
    centroides = np.stack([
        ((np.stack([a.vetor for a in relatorio.validas(c)]) - media) / desvio).mean(axis=0)
        for c in classes
    ])
    normas = np.linalg.norm(centroides, axis=1, keepdims=True) + 1e-9
    unitarios = centroides / normas
    return classes, unitarios @ unitarios.T


def ler_amostras() -> list[Amostra]:
    """Lê e valida todas as amostras das classes de config.CLASSES.

    Cada amostra válida já vem com o vetor de features (janela_para_vetor), o
    mesmo usado no tempo real. Arquivos ilegíveis e duplicatas são marcados como
    inválidos. Usado pela análise do dataset e pela montagem do dataset de treino.
    """
    amostras: list[Amostra] = []
    hashes: dict[str, str] = {}
    for caminho in listar_amostras():
        sinal = caminho.parent.name
        if sinal not in config.CLASSES:
            continue
        amostra = Amostra(caminho_relativo(caminho), sinal, pessoa_do_arquivo(caminho))
        amostras.append(amostra)
        try:
            frames = np.load(caminho)
        except (OSError, ValueError) as erro:
            amostra.problemas.append(f"não foi possível ler o arquivo ({erro})")
            continue

        resumo = hashlib.sha1(frames.tobytes()).hexdigest()
        if resumo in hashes:
            amostra.problemas.append(f"duplicata de {hashes[resumo]}")
            continue
        hashes[resumo] = amostra.arquivo

        amostra.problemas = validar_amostra(frames, sinal)
        if amostra.valida:
            amostra.perfil = perfil_maos(estatisticas_amostra(frames))
            amostra.vetor = janela_para_vetor(frames)
    return amostras


def analisar_dataset() -> RelatorioDataset:
    inconsistencias: list[str] = []
    alertas: list[tuple[str, str]] = []
    _verificar_organizacao(inconsistencias)
    amostras = ler_amostras()

    relatorio = RelatorioDataset(amostras, inconsistencias, alertas,
                                 {a.vetor.size for a in amostras if a.vetor is not None}, None)
    if len(relatorio.tamanhos_vetor) > 1:
        inconsistencias.append(f"vetores com tamanhos diferentes: {sorted(relatorio.tamanhos_vetor)}")

    contagens = {c: relatorio.contagem(c) for c in config.CLASSES}
    com_amostras = [n for n in contagens.values() if n > 0]
    if com_amostras and max(com_amostras) > config.MAX_DESBALANCEAMENTO * min(com_amostras):
        maior = max(contagens, key=contagens.get)
        menor = min((c for c in contagens if contagens[c] > 0), key=contagens.get)
        inconsistencias.append(
            f"classes desbalanceadas: {maior} tem {contagens[maior]} amostras e {menor} só {contagens[menor]}")
    for classe in config.CLASSES:
        n_pessoas = len(relatorio.pessoas(classe))
        if 0 < n_pessoas < config.MIN_PESSOAS_POR_CLASSE:
            inconsistencias.append(f"{classe}: amostras de só {n_pessoas} pessoa(s); o modelo pode não generalizar")

    for classe in config.CLASSES:
        validas = relatorio.validas(classe)
        for amostra in _outliers(validas):
            alertas.append((amostra.arquivo, "muito diferente das demais amostras do sinal (gravado errado?)"))
        if classe == config.CLASSE_NADA or len(validas) < 5:
            continue
        perfil, n = relatorio.perfis(classe).most_common(1)[0]
        if n / len(validas) >= 0.7:
            for amostra in validas:
                if amostra.perfil != perfil:
                    alertas.append((amostra.arquivo,
                                    f"usa mão(s) '{amostra.perfil}', mas o sinal costuma usar '{perfil}'"))

    relatorio.similaridade = _similaridade_classes(relatorio)
    return relatorio


def pares_mais_parecidos(relatorio: RelatorioDataset, n: int = 3) -> list[tuple[str, str, float]]:
    if relatorio.similaridade is None:
        return []
    classes, matriz = relatorio.similaridade
    pares = [(classes[i], classes[j], float(matriz[i, j]))
             for i in range(len(classes)) for j in range(i + 1, len(classes))]
    return sorted(pares, key=lambda p: -p[2])[:n]


def por_pessoa(relatorio: RelatorioDataset) -> dict[str, dict[str, int]]:
    """{pessoa: {sinal: quantidade de amostras válidas}}"""
    tabela: dict[str, dict[str, int]] = defaultdict(dict)
    for classe in config.CLASSES:
        for pessoa, n in relatorio.pessoas(classe).items():
            tabela[pessoa][classe] = n
    return dict(tabela)


# -----------------------------------------------------------------------------
# Dataset de treino (data/processed/dataset.npz)
# -----------------------------------------------------------------------------

class ErroDataset(ValueError):
    """dataset.npz ausente, desatualizado ou com dados inconsistentes."""


@dataclass
class DadosTreino:
    X: np.ndarray         # (n_amostras, config.TAM_FEATURES_JANELA)
    y: np.ndarray         # rótulos (identificadores dos sinais)
    pessoas: np.ndarray   # quem gravou cada amostra (para testar com pessoas novas)
    arquivos: np.ndarray  # origem de cada linha, relativa a data/


def construir_dados_treino() -> tuple[DadosTreino, list[Amostra]]:
    """Monta X/y com as amostras válidas. Devolve também as inválidas (ignoradas)."""
    amostras = ler_amostras()
    validas = [a for a in amostras if a.valida]
    if not validas:
        raise ErroDataset(f"nenhuma amostra válida em {config.DIR_RAW}; grave amostras com coletar_dados.py")
    dados = DadosTreino(
        X=np.stack([a.vetor for a in validas]).astype(np.float32),
        y=np.array([a.sinal for a in validas]),
        pessoas=np.array([a.pessoa for a in validas]),
        arquivos=np.array([a.arquivo for a in validas]),
    )
    return dados, [a for a in amostras if not a.valida]


def salvar_dados_treino(dados: DadosTreino) -> None:
    config.ARQ_DATASET.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        config.ARQ_DATASET, X=dados.X, y=dados.y, pessoas=dados.pessoas, arquivos=dados.arquivos,
        versao_features=config.VERSAO_FEATURES, t_frames=config.T_FRAMES,
    )


def precisa_reconstruir() -> bool:
    """dataset.npz ausente ou gerado com outra versão de features / T_FRAMES?"""
    if not config.ARQ_DATASET.is_file():
        return True
    try:
        with np.load(config.ARQ_DATASET, allow_pickle=False) as arquivo:
            return (int(arquivo["versao_features"]) != config.VERSAO_FEATURES
                    or int(arquivo["t_frames"]) != config.T_FRAMES)
    except (OSError, ValueError, KeyError):
        return True


def carregar_dados_treino() -> DadosTreino:
    """Carrega e VALIDA o dataset.npz (versão das features, formato e rótulos)."""
    if not config.ARQ_DATASET.is_file():
        raise ErroDataset(f"{config.ARQ_DATASET} não existe; rode scripts/desenvolvimento/construir_dataset.py")
    with np.load(config.ARQ_DATASET, allow_pickle=False) as arquivo:
        versao, t_frames = int(arquivo["versao_features"]), int(arquivo["t_frames"])
        dados = DadosTreino(arquivo["X"], arquivo["y"], arquivo["pessoas"], arquivo["arquivos"])

    if versao != config.VERSAO_FEATURES or t_frames != config.T_FRAMES:
        raise ErroDataset(
            f"dataset.npz foi gerado com features v{versao}/T={t_frames}, mas o config.py usa "
            f"v{config.VERSAO_FEATURES}/T={config.T_FRAMES}; rode scripts/desenvolvimento/construir_dataset.py")
    problemas = validar_dados_treino(dados)
    if problemas:
        raise ErroDataset("dataset.npz inválido:\n  - " + "\n  - ".join(problemas))
    return dados


def validar_dados_treino(dados: DadosTreino) -> list[str]:
    """Problemas que impedem o treino (lista vazia = pode treinar)."""
    problemas = []
    n = len(dados.y)
    if dados.X.ndim != 2 or dados.X.shape != (n, config.TAM_FEATURES_JANELA):
        problemas.append(f"X tem formato {dados.X.shape}, esperado ({n}, {config.TAM_FEATURES_JANELA})")
    if not (len(dados.pessoas) == len(dados.arquivos) == n):
        problemas.append("X, y, pessoas e arquivos têm quantidades diferentes")
    if dados.X.size and not np.isfinite(dados.X).all():
        problemas.append("X contém NaN ou infinito")
    desconhecidas = sorted(set(dados.y) - set(config.CLASSES))
    if desconhecidas:
        problemas.append(f"rótulos fora de config.CLASSES: {desconhecidas}")
    contagem = Counter(dados.y)
    if len(contagem) < 2:
        problemas.append("são necessárias pelo menos 2 classes")
    poucas = sorted(c for c, q in contagem.items() if q < 2)
    if poucas:
        problemas.append(f"classes com menos de 2 amostras (impossível estratificar): {poucas}")
    return problemas
