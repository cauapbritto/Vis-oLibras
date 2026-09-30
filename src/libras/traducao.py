"""Tabela de frases: converte sequências de sinais cadastradas em português.

O reconhecimento produz a GLOSA - os sinais na ordem em que foram feitos
("EU NOME"). Esta tabela, escrita e revisada pelo grupo no arquivo frases.txt,
diz como algumas sequências conhecidas devem aparecer e ser faladas em
português ("Meu nome é"). NÃO é um tradutor de Libras: sequências que não
estão na tabela continuam como glosa, em maiúsculas, para ficar claro que não
foram convertidas.

Formato do frases.txt (uma frase por linha; "#" começa um comentário):

    BOM DIA   = Bom dia!
    MEU NOME  = Meu nome é

Conversão: da esquerda para a direita, sempre com a frase cadastrada MAIS
LONGA que encaixa naquele ponto ("BOM DIA" ganha de "BOM" sozinho). Letras do
alfabeto seguidas viram uma palavra soletrada, sem precisar de tabela:
"MEU NOME C A U A" -> "Meu nome é Caua" (glosa: MEU NOME C-A-U-A).

    tabela = TabelaFrases.ler()          # config.ARQ_FRASES
    tabela.traduzir(["OI", "BOM", "DIA"]).texto   # "Oi! Bom dia!"
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from libras import config

PONTUACAO_FINAL = ".!?…"


@dataclass(frozen=True)
class Parte:
    """Um pedaço da sequência: os sinais e o português (None = sem frase cadastrada)."""
    sinais: tuple[str, ...]
    texto: str | None
    soletrada: bool = False    # letras do alfabeto juntadas numa palavra

    @property
    def glosa(self) -> str:
        """Como a parte aparece na glosa: letras soletradas unidas por hífen (C-A-U-A)."""
        separador = "-" if self.soletrada else " "
        return separador.join(config.rotulo_exibicao(s) for s in self.sinais)


def agrupar_letras(palavras) -> list[tuple[str, ...]]:
    """Agrupa letras seguidas: [EU, C, A, U, A] -> [(EU,), (C, A, U, A)]."""
    grupos: list[tuple[str, ...]] = []
    for palavra in palavras:
        if config.eh_letra(palavra) and grupos and config.eh_letra(grupos[-1][-1]):
            grupos[-1] = grupos[-1] + (palavra,)
        else:
            grupos.append((palavra,))
    return grupos


def palavra_soletrada(letras) -> str:
    """("C", "A", "U", "A") -> "Caua" (nomes próprios, a principal razão de soletrar)."""
    return "".join(config.rotulo_exibicao(l) for l in letras).capitalize()


@dataclass(frozen=True)
class Traducao:
    texto: str                 # para mostrar e falar (português + glosa onde não houve frase)
    glosa: str                 # a sequência de sinais, como hoje ("EU NOME")
    partes: tuple[Parte, ...]

    @property
    def convertida(self) -> bool:
        """Alguma parte virou português."""
        return any(p.texto is not None for p in self.partes)

    @property
    def completa(self) -> bool:
        """Toda a sequência virou português."""
        return bool(self.partes) and all(p.texto is not None for p in self.partes)


@dataclass
class TabelaFrases:
    frases: dict[tuple[str, ...], str] = field(default_factory=dict)
    avisos: list[str] = field(default_factory=list)  # problemas encontrados ao ler o arquivo

    def __len__(self) -> int:
        return len(self.frases)

    # --- leitura -----------------------------------------------------------------

    @classmethod
    def de_texto(cls, conteudo: str, sinais_conhecidos=None) -> "TabelaFrases":
        conhecidos = set(config.SINAIS if sinais_conhecidos is None else sinais_conhecidos)
        tabela = cls()
        for numero, linha in enumerate(conteudo.splitlines(), start=1):
            linha = linha.split("#", 1)[0].strip()
            if not linha:
                continue
            if "=" not in linha:
                tabela.avisos.append(f"linha {numero}: falta o '=' (formato: SINAIS = texto)")
                continue
            esquerda, texto = (parte.strip() for parte in linha.split("=", 1))
            sinais = tuple(config.identificador_sinal(s) for s in esquerda.split())
            if not sinais or not texto:
                tabela.avisos.append(f"linha {numero}: falta {'os sinais' if not sinais else 'o texto'}")
                continue
            if config.CLASSE_NADA in sinais:
                tabela.avisos.append(f"linha {numero}: {config.CLASSE_NADA} não pode fazer parte de uma frase")
                continue
            desconhecidos = [s for s in sinais if s not in conhecidos]
            if desconhecidos:
                tabela.avisos.append(f"linha {numero}: sinal desconhecido {', '.join(desconhecidos)} "
                                     "(confira a grafia; essa frase não vai aparecer)")
            if sinais in tabela.frases:
                tabela.avisos.append(f"linha {numero}: '{' '.join(sinais)}' repetida; vale a última")
            tabela.frases[sinais] = texto
        return tabela

    @classmethod
    def ler(cls, caminho: Path | None = None, sinais_conhecidos=None) -> "TabelaFrases":
        """Lê o arquivo. Sem arquivo, devolve uma tabela vazia (o programa segue só com glosa)."""
        caminho = Path(caminho or config.ARQ_FRASES)
        if not caminho.is_file():
            return cls(avisos=[f"{caminho.name} não encontrado: as frases aparecem só como glosa"])
        dados = caminho.read_bytes()
        try:
            conteudo = dados.decode("utf-8-sig")
        except UnicodeDecodeError:  # Bloco de Notas antigo salva em ANSI
            conteudo = dados.decode("cp1252", errors="replace")
        return cls.de_texto(conteudo, sinais_conhecidos)

    # --- conversão ---------------------------------------------------------------

    def traduzir(self, palavras: list[str]) -> Traducao:
        palavras = list(palavras)
        maior = max((len(s) for s in self.frases), default=0)
        partes: list[Parte] = []
        i = 0
        while i < len(palavras):
            if config.eh_letra(palavras[i]):
                fim = i
                while fim < len(palavras) and config.eh_letra(palavras[fim]):
                    fim += 1
                letras = tuple(palavras[i:fim])
                partes.append(Parte(letras, palavra_soletrada(letras), soletrada=True))
                i = fim
                continue
            for tamanho in range(min(maior, len(palavras) - i), 0, -1):
                chave = tuple(palavras[i:i + tamanho])
                if chave in self.frases:
                    partes.append(Parte(chave, self.frases[chave]))
                    i += tamanho
                    break
            else:
                partes.append(Parte((palavras[i],), None))
                i += 1
        glosa = " ".join(parte.glosa for parte in partes)
        return Traducao(_montar_texto(partes), glosa, tuple(partes))


def _montar_texto(partes: list[Parte]) -> str:
    """Junta as partes. Frases da tabela começam com maiúscula no início, depois de
    ponto/exclamação/interrogação ou depois de um trecho em glosa, e com minúscula
    logo após outra frase da tabela sem pontuação ("Meu nome é obrigado!")."""
    pedacos: list[str] = []
    anterior_glosa = False
    for parte in partes:
        if parte.texto is None:
            pedacos.append(" ".join(config.rotulo_exibicao(s) for s in parte.sinais))
            anterior_glosa = True
            continue
        texto = parte.texto
        inicio_de_frase = not pedacos or anterior_glosa or pedacos[-1][-1:] in PONTUACAO_FINAL
        anterior_glosa = False
        if not parte.soletrada:  # palavra soletrada é nome próprio: sempre com maiúscula
            texto = (texto[:1].upper() if inicio_de_frase else texto[:1].lower()) + texto[1:]
        pedacos.append(texto)
    return " ".join(pedacos)


def carregar_tabela_padrao() -> TabelaFrases | None:
    """A tabela do config.ARQ_FRASES, ou None se config.USAR_TABELA_FRASES = False."""
    return TabelaFrases.ler() if config.USAR_TABELA_FRASES else None
