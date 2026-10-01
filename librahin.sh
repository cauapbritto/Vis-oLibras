#!/usr/bin/env bash
# Librahin no Linux: abre o mesmo menu de terminal do Windows (precisa do PowerShell).
# Primeira vez: ./librahin.sh instalar   (cria o .venv e instala as bibliotecas)
set -e
cd "$(dirname "$0")"

if [ "$1" = "instalar" ]; then
    python3 -m venv .venv
    .venv/bin/python -m pip install --upgrade pip
    .venv/bin/python -m pip install -r requirements.txt
    [ -d scripts/desenvolvimento ] && .venv/bin/python -m pip install -r requirements-dev.txt
    echo
    echo "Instalado. Abra o menu com: ./librahin.sh"
    exit 0
fi

if [ ! -x .venv/bin/python ]; then
    echo "O projeto ainda não foi instalado. Rode primeiro: ./librahin.sh instalar"
    exit 1
fi

if ! command -v pwsh >/dev/null 2>&1; then
    echo "O menu precisa do PowerShell (pwsh). Instale com:"
    echo "    sudo snap install powershell --classic"
    echo "ou veja: https://learn.microsoft.com/powershell/scripting/install/install-ubuntu"
    echo
    echo "Sem o menu, dá para usar os scripts direto, ex.: .venv/bin/python scripts/demonstracao/app.py"
    exit 1
fi

exec pwsh -NoProfile -File windows/menu.ps1
