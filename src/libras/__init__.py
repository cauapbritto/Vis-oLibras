"""Vis-oLibras: tradução de Libras para texto e voz.

Os módulos são organizados em três camadas (ver docs/ARQUITETURA.md, seção 2):

- NÚCLEO: usado pelos dois modos (câmera, landmarks, pré-processamento, desenho).
- APLICAÇÃO (modo usuário/demonstração): reconhecer, montar a frase, falar e a
  interface. Só importa o núcleo e a própria aplicação.
- DESENVOLVIMENTO (modo treinamento): dataset, treino e avaliação. Pode usar
  tudo, mas nada da aplicação depende dele.

A regra é verificada automaticamente em tests/test_modos.py, e o pacote de
demonstração (scripts/desenvolvimento/empacotar_app.py) leva só o núcleo e a
aplicação.
"""

__version__ = "0.2.0"

MODULOS_NUCLEO = ("config", "camera", "extrator", "features", "temporal", "desenho", "metricas")
MODULOS_APLICACAO = ("classificador", "estabilizador", "reconhecedor", "frase", "voz",
                     "pipeline", "captura", "interface", "__main__")
MODULOS_DESENVOLVIMENTO = ("dataset", "avaliacao", "experimento")
