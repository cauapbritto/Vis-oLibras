"""Testa a voz: experimenta cada motor de voz deste sistema, um de cada vez.

Uso:
    python scripts/demonstracao/testar_voz.py

Para cada motor, mostra a voz escolhida e fala uma frase. Anote qual você OUVIU.
Se o automático não funcionar e outro funcionar, escolha-o em
src/libras/config.py (MOTOR_VOZ).
"""

import platform
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))  # funciona sem "pip install -e ."

from libras import config, voz  # noqa: E402

VOZES_WINDOWS = (
    "Add-Type -AssemblyName System.Speech; "
    "(New-Object System.Speech.Synthesis.SpeechSynthesizer).GetInstalledVoices() | "
    "ForEach-Object { '   - ' + $_.VoiceInfo.Name + ' (' + $_.VoiceInfo.Culture.Name + ')' + "
    "$(if ($_.Enabled) { '' } else { ' [desativada]' }) }"
)


def listar_vozes_windows() -> None:
    print("Vozes instaladas no Windows:")
    try:
        saida = subprocess.run(["powershell", "-NoProfile", "-Command", VOZES_WINDOWS],
                               capture_output=True, text=True, timeout=30).stdout.strip()
    except (OSError, subprocess.TimeoutExpired) as erro:
        saida = f"   (não foi possível listar: {erro})"
    print(saida or "   nenhuma")
    if "pt-BR" not in saida:
        print("   [AVISO] Nenhuma voz em português (pt-BR). Configurações > Hora e idioma >"
              " Idioma e região > Português (Brasil) > Opções > instalar Fala/Conversão de texto em fala.")
    print()


def testar(nome: str, numero: int) -> bool:
    print(f"[{numero}] Motor '{nome}'")
    try:
        motor = voz.MOTORES[nome]()
    except Exception as erro:
        print(f"    não iniciou: {erro}\n")
        return False
    print(f"    voz: {motor.nome_voz}")
    print("    falando agora... (escute)")
    inicio = time.time()
    try:
        motor.falar_bloqueante(f"Teste de voz número {numero}. Olá, eu sou o Vis o Libras.")
    except Exception as erro:
        print(f"    erro ao falar: {erro}\n")
        return False
    print(f"    terminou em {time.time() - inicio:.1f} s, sem erro\n")
    return True


def testar_aplicacao() -> None:
    """Do jeito que a aplicação usa: em segundo plano, com o motor automático."""
    print(f"[A] Como na aplicação (MOTOR_VOZ = \"{config.MOTOR_VOZ}\", em segundo plano)")
    v = voz.Voz(politica="enfileirar")
    if not v.disponivel:
        print(f"    indisponível: {v.erro}\n")
        return
    print(f"    voz: {v.nome_voz}")
    print("    falando duas frases... (escute)")
    v.falar("Primeira frase da aplicação.")
    v.falar("Segunda frase da aplicação.")
    fim = time.time() + 30
    while v.falando and time.time() < fim:
        time.sleep(0.1)
    v.encerrar()
    print(f"    {'erro: ' + v.erro if v.erro else 'terminou sem erro'}\n")


def main() -> int:
    print(f"Sistema: {platform.system()} {platform.release()} | Python {platform.python_version()}\n")
    if platform.system() == "Windows":
        listar_vozes_windows()
    motores = voz.motores_do_sistema()
    resultados = {nome: testar(nome, i) for i, nome in enumerate(motores, start=1)}
    testar_aplicacao()
    print("Resumo (sem erro não garante que saiu som: confira o que você ouviu):")
    for i, (nome, ok) in enumerate(resultados.items(), start=1):
        print(f"   [{i}] {nome:8s} {'sem erro' if ok else 'FALHOU'}")
    print("\nSe ouviu só um dos testes, abra src/libras/config.py e troque MOTOR_VOZ = \"auto\"")
    print("pelo nome do motor que funcionou (ex.: MOTOR_VOZ = \"pyttsx3\").")
    print("Não ouviu nada? Confira o volume, a saída de som do sistema e os fones.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
