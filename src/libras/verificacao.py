"""Verificação do ambiente: luz, velocidade da câmera, ombros visíveis, distância e mãos.

Recebe amostras dos quadros da câmera por alguns segundos e diz o que está bom
e o que ajustar, com uma dica para cada problema. Não depende da interface.

    v = VerificacaoAmbiente()
    for quadro in ...: v.adicionar(brilho, fps, largura_ombros, tem_maos)
    for item in v.resultado(): print(item.nome, item.ok, item.texto)
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

DURACAO_S = 4.0
BRILHO_MINIMO = 70          # média de 0 a 255
BRILHO_MAXIMO = 205
FPS_MINIMO = 12
PCT_MINIMO_OMBROS = 0.6
OMBROS_LONGE = 0.18         # largura dos ombros como fração da largura da imagem
OMBROS_PERTO = 0.50


@dataclass(frozen=True)
class Item:
    nome: str
    ok: bool | None            # None = só informação
    texto: str


def brilho_medio(imagem_bgr: np.ndarray) -> float:
    """Brilho médio (0 a 255), com os pesos da luminância (amostra 1 a cada 4 pixels)."""
    amostra = imagem_bgr[::4, ::4].astype(np.float32)
    return float((amostra @ np.array([0.114, 0.587, 0.299], dtype=np.float32)).mean())


def largura_ombros(pose: np.ndarray | None, largura: int, altura: int) -> float | None:
    """Largura dos ombros como fração da largura da imagem (pose normalizada 0 a 1)."""
    if pose is None:
        return None
    esquerdo, direito = pose[11, :2], pose[12, :2]
    dx = float(esquerdo[0] - direito[0])
    dy = float(esquerdo[1] - direito[1]) * altura / max(largura, 1)
    return float(np.hypot(dx, dy))


@dataclass
class VerificacaoAmbiente:
    brilhos: list[float] = field(default_factory=list)
    fps: list[float] = field(default_factory=list)
    ombros: list[float | None] = field(default_factory=list)
    maos: list[bool] = field(default_factory=list)

    def adicionar(self, brilho: float, fps: float, largura_ombros_img: float | None, tem_maos: bool) -> None:
        self.brilhos.append(brilho)
        if fps > 0:
            self.fps.append(fps)
        self.ombros.append(largura_ombros_img)
        self.maos.append(tem_maos)

    @property
    def amostras(self) -> int:
        return len(self.brilhos)

    def resultado(self) -> list[Item]:
        if not self.brilhos:
            return [Item("Câmera", False, "Nenhuma imagem recebida da câmera.")]
        itens = []
        brilho = float(np.median(self.brilhos))
        if brilho < BRILHO_MINIMO:
            itens.append(Item("Luz", False, "Pouca luz. Acenda a luz ou fique de frente para uma janela."))
        elif brilho > BRILHO_MAXIMO:
            itens.append(Item("Luz", False, "Imagem clara demais. Evite luz forte ou janela atrás de você."))
        else:
            itens.append(Item("Luz", True, "Iluminação boa."))

        fps = float(np.median(self.fps)) if self.fps else 0.0
        if fps and fps < FPS_MINIMO:
            itens.append(Item("Câmera", False, f"Imagem lenta ({fps:.0f} quadros por segundo). Feche outros "
                                               "programas; o modo leve (Configurações) ajuda."))
        else:
            itens.append(Item("Câmera", True, f"{fps:.0f} quadros por segundo."))

        vistos = [o for o in self.ombros if o is not None]
        if len(vistos) < PCT_MINIMO_OMBROS * len(self.ombros):
            itens.append(Item("Ombros", False, "Os ombros não aparecem direito. Afaste-se até os ombros "
                                               "ficarem inteiros na imagem."))
            itens.append(Item("Distância", None, "Não foi possível medir sem os ombros."))
        else:
            itens.append(Item("Ombros", True, "Ombros visíveis."))
            largura = float(np.median(vistos))
            if largura < OMBROS_LONGE:
                itens.append(Item("Distância", False, "Longe demais. Chegue um pouco mais perto (cerca de 1 metro)."))
            elif largura > OMBROS_PERTO:
                itens.append(Item("Distância", False, "Perto demais. Afaste-se um pouco (cerca de 1 metro)."))
            else:
                itens.append(Item("Distância", True, "Distância boa."))

        if np.mean(self.maos) >= 0.3:
            itens.append(Item("Mãos", True, "Mãos detectadas."))
        else:
            itens.append(Item("Mãos", None, "Levante as mãos na frente do peito para conferir se aparecem."))
        return itens

    @property
    def tudo_ok(self) -> bool:
        return all(item.ok is not False for item in self.resultado())
