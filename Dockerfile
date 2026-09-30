# Vis-oLibras em container.
#
# - Treino, análise do dataset e testes: funcionam em qualquer sistema com Docker.
# - Câmera, janela e som (coleta e interface): só no Linux (ver docs/DOCKER.md).
#
# Montar a imagem:   docker compose build
# Rede corporativa que intercepta HTTPS (erro de certificado)? Passe o certificado:
#   docker build --secret id=ca,src=certificado-da-rede.crt -t vis-olibras .
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_CERT=/etc/ssl/certs/ca-certificates.crt \
    PATH=/opt/venv/bin:$PATH \
    MPLCONFIGDIR=/tmp/matplotlib

# Certificado extra opcional (rede que intercepta HTTPS); sem ele, nada muda.
RUN --mount=type=secret,id=ca \
    apt-get update && apt-get install -y --no-install-recommends ca-certificates \
    && if [ -s /run/secrets/ca ]; then \
        cp /run/secrets/ca /usr/local/share/ca-certificates/rede-extra.crt && update-ca-certificates; \
    fi \
    && rm -rf /var/lib/apt/lists/*

# Python 3.12 do Ubuntu + bibliotecas: MediaPipe (EGL/GLES), OpenCV (GL, glib),
# interface (Tk), voz (eSpeak + ALSA) e fonte com acentos.
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-venv python3-tk \
        libegl1 libgles2 libgl1 libglib2.0-0 \
        espeak-ng alsa-utils \
        fonts-dejavu-core curl \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m venv /opt/venv

WORKDIR /app
COPY requirements.txt requirements-dev.txt ./
RUN pip install --upgrade pip && pip install -r requirements-dev.txt

# Modelos do MediaPipe dentro da imagem: o container funciona sem internet.
# (Copiados para models/ na primeira execução, se ainda não existirem lá.)
RUN mkdir -p /opt/mediapipe \
    && curl -fsSL -o /opt/mediapipe/hand_landmarker.task \
       https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task \
    && curl -fsSL -o /opt/mediapipe/pose_landmarker_lite.task \
       https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task

COPY pyproject.toml ./
COPY src ./src
COPY scripts ./scripts
COPY tests ./tests
COPY docs ./docs
COPY data ./data
COPY models ./models
COPY reports ./reports
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

ENTRYPOINT ["entrypoint.sh"]
CMD ["python", "-m", "libras.config"]
