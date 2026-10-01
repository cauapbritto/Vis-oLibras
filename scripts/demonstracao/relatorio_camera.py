"""Relatório detalhado da câmera, para descobrir o erro de verdade quando a imagem não vem.

Uso (com a aplicação e o app Câmera fechados):
    python scripts/demonstracao/relatorio_camera.py

Abre a câmera com o registro de depuração do OpenCV ligado (ele mostra o código de erro
que o Windows devolve), lê alguns quadros em cada modo e junta informações do sistema:
versão do Windows, câmeras instaladas, permissões, antivírus e programas que costumam
usar a câmera. Salva tudo em reports/relatorio_camera.txt e abre no Bloco de Notas.
"""

import os
import platform
import subprocess
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
DESTINO = RAIZ / "reports" / "relatorio_camera.txt"

# Roda em outro processo: o OpenCV escreve o registro de depuração direto na saída do
# processo, que só dá para capturar de fora.
TESTE = r"""
import sys, time
import cv2
indice, modo = int(sys.argv[1]), sys.argv[2]
backend = cv2.CAP_MSMF if modo.startswith("msmf") else cv2.CAP_DSHOW
print("opencv", cv2.__version__, flush=True)
inicio = time.perf_counter()
captura = cv2.VideoCapture(indice, backend)
print("abriu:", captura.isOpened(), "em %.2f s" % (time.perf_counter() - inicio), flush=True)
if captura.isOpened():
    if modo == "dshow_mjpg":
        captura.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    if not modo.endswith("_nativo"):
        print("pedir 640x480:", captura.set(cv2.CAP_PROP_FRAME_WIDTH, 640),
              captura.set(cv2.CAP_PROP_FRAME_HEIGHT, 480), flush=True)
    fourcc = int(captura.get(cv2.CAP_PROP_FOURCC))
    print("formato:", "".join(chr((fourcc >> 8 * i) & 0xFF) for i in range(4)) if fourcc > 0 else fourcc,
          "| tamanho: %dx%d" % (captura.get(cv2.CAP_PROP_FRAME_WIDTH), captura.get(cv2.CAP_PROP_FRAME_HEIGHT)),
          "| fps: %.1f" % captura.get(cv2.CAP_PROP_FPS),
          "| backend:", captura.getBackendName(), flush=True)
    for i in range(8):
        inicio = time.perf_counter()
        ok, frame = captura.read()
        duracao = time.perf_counter() - inicio
        if ok and frame is not None:
            print("quadro %d: ok %s média %.1f desvio %.1f (%.2f s)"
                  % (i, frame.shape, frame.mean(), frame.std(), duracao), flush=True)
        else:
            print("quadro %d: FALHOU (%.2f s)" % (i, duracao), flush=True)
    captura.release()
"""

POWERSHELL = r"""
$ErrorActionPreference = 'SilentlyContinue'
'--- Windows'
Get-CimInstance Win32_OperatingSystem | ForEach-Object { "$($_.Caption) $($_.Version) build $($_.BuildNumber)" }
Get-CimInstance Win32_ComputerSystem | ForEach-Object { "Modelo: $($_.Manufacturer) $($_.Model)" }
'--- Câmeras instaladas'
Get-PnpDevice -Class Camera,Image | ForEach-Object { "$($_.Status) | $($_.FriendlyName) | $($_.InstanceId)" }
'--- Driver das câmeras'
Get-CimInstance Win32_PnPSignedDriver | Where-Object { $_.DeviceClass -in 'CAMERA','IMAGE' } |
    ForEach-Object { "$($_.DeviceName) | driver $($_.DriverVersion) | $($_.DriverProviderName) | $($_.InfName)" }
'--- Permissões da câmera (Allow = liberado)'
$base = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\webcam'
"Usuário: $((Get-ItemProperty $base).Value)"
"Apps da área de trabalho: $((Get-ItemProperty "$base\NonPackaged").Value)"
$m = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\webcam'
"Computador: $((Get-ItemProperty $m).Value)"
"Política LetAppsAccessCamera: $((Get-ItemProperty 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\AppPrivacy').LetAppsAccessCamera)"
"Política AllowCamera: $((Get-ItemProperty 'HKLM:\SOFTWARE\Policies\Microsoft\Camera').AllowCamera)"
'--- Último uso da câmera por programas da área de trabalho'
Get-ChildItem "$base\NonPackaged" | ForEach-Object {
    $p = Get-ItemProperty $_.PSPath
    $fim = if ($p.LastUsedTimeStop) { [DateTime]::FromFileTime($p.LastUsedTimeStop) } else { '' }
    "$($_.PSChildName.Replace('#', '\')) | parou: $fim"
}
'--- Serviços da câmera'
Get-Service FrameServer, FrameServerMonitor | ForEach-Object { "$($_.Name): $($_.Status)" }
'--- Antivírus'
Get-CimInstance -Namespace root/SecurityCenter2 -ClassName AntiVirusProduct |
    ForEach-Object { "$($_.displayName) (estado $($_.productState))" }
'--- Programas abertos que costumam mexer na câmera'
Get-Process | Where-Object { $_.ProcessName -match 'lenovo|vantage|logi|camera|webcam|teams|zoom|discord|obs|skype|kaspersky|avp|eset|ekrn|avast|avg|bitdefender|bdservice|norton|mcafee|sophos|trend|panda|deep|faronics|netsupport|veyon|lanschool|deepfreeze|kiosk' } |
    ForEach-Object { "$($_.ProcessName) | $($_.Path)" }
"""


def _rodar(comando: list[str], ambiente: dict | None = None, limite: int = 60) -> str:
    try:
        r = subprocess.run(comando, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           env=ambiente, timeout=limite, cwd=RAIZ)
        return (r.stdout + r.stderr).strip()
    except subprocess.TimeoutExpired:
        return f"(passou de {limite} s e foi interrompido)"
    except OSError as erro:
        return f"(não foi possível rodar: {erro})"


def teste_com_registro(indice: int, modo: str, transformacoes_hw: bool = False) -> str:
    ambiente = dict(os.environ, OPENCV_LOG_LEVEL="DEBUG", OPENCV_VIDEOIO_DEBUG="1",
                    OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS="1" if transformacoes_hw else "0")
    saida = _rodar([sys.executable, "-c", TESTE, str(indice), modo], ambiente)
    # o registro de depuração repete muito: mantém o começo e o fim
    linhas = saida.splitlines()
    if len(linhas) > 80:
        linhas = linhas[:50] + [f"... ({len(linhas) - 70} linhas omitidas) ..."] + linhas[-20:]
    return "\n".join(linhas)


def montar_relatorio(indice: int = 0) -> str:
    partes = [f"RELATÓRIO DA CÂMERA - Librahin - {datetime.now():%d/%m/%Y %H:%M}",
              f"Python: {sys.version.split()[0]} | {sys.executable}",
              f"Base do Python: {sys.base_prefix}",
              f"Pasta do projeto: {RAIZ}"]
    try:
        import cv2
        partes.append(f"OpenCV: {cv2.__version__}")
        video = cv2.getBuildInformation().split("Video I/O:")[-1].split("Parallel framework")[0]
        partes.append("Video I/O do OpenCV:" + video.rstrip())
    except Exception as erro:  # noqa: BLE001 - o relatório tem que sair mesmo assim
        partes.append(f"OpenCV não carregou: {erro}")
    try:
        import mediapipe
        partes.append(f"MediaPipe: {mediapipe.__version__}")
    except Exception as erro:  # noqa: BLE001
        partes.append(f"MediaPipe não carregou: {erro}")

    if platform.system() == "Windows":
        partes.append("\n=== SISTEMA ===")
        partes.append(_rodar(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", POWERSHELL]))
        modos = [("msmf", False), ("msmf", True), ("msmf_nativo", False), ("dshow", False), ("dshow_mjpg", False)]
    else:
        modos = []
    for modo, hw in modos:
        partes.append(f"\n=== CÂMERA {indice + 1} | {modo}{' | transformações por hardware LIGADAS' if hw else ''} ===")
        partes.append(teste_com_registro(indice, modo, hw))
    return "\n".join(partes) + "\n"


def main() -> int:
    indice = int(sys.argv[1]) - 1 if len(sys.argv) > 1 else 0
    print(f"Gerando o relatório da câmera {indice + 1} (leva até 1 minuto)...")
    texto = montar_relatorio(indice)
    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    DESTINO.write_text(texto, encoding="utf-8")
    print(f"Relatório salvo em: {DESTINO}")
    print("Abra o arquivo, copie tudo (Ctrl+A, Ctrl+C) e mande para quem está ajudando.")
    if platform.system() == "Windows":
        os.startfile(DESTINO)  # abre no Bloco de Notas
    return 0


if __name__ == "__main__":
    sys.exit(main())
