#!/bin/sh
# Coloca os modelos do MediaPipe da imagem em models/ (que costuma ser uma pasta
# do computador montada no container) e executa o comando pedido.
set -e
mkdir -p /app/models
for modelo in /opt/mediapipe/*.task; do
    destino="/app/models/$(basename "$modelo")"
    [ -f "$destino" ] || cp "$modelo" "$destino"
done
export PYTHONPATH="/app/src${PYTHONPATH:+:$PYTHONPATH}"
exec "$@"
