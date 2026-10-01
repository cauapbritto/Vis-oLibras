"""Diagnóstico da câmera: testa cada câmera em cada modo e mostra a imagem de cada um.

Uso (com a aplicação fechada, para a câmera estar livre):
    python scripts/demonstracao/diagnosticar_camera.py

Gera reports/diagnostico_camera.png com uma miniatura de cada combinação, diz qual
deu imagem boa (e com mais quadros por segundo) e oferece usar essa combinação na
aplicação, no teste de câmera e na gravação.
"""

import os
import platform
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))  # funciona sem "pip install -e ."

import libras  # noqa: E402,F401  (configura o OpenCV antes de importá-lo)

import cv2  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

from libras import config, preferencias  # noqa: E402
from libras.camera import NOMES_MODOS, TesteCamera, diagnosticar, melhor_combinacao  # noqa: E402
from libras.desenho import fonte_com_acentos  # noqa: E402

LARGURA_MINI, ALTURA_MINI = 320, 240


def folha_de_contato(resultados: list[TesteCamera], destino: Path) -> None:
    testados = [r for r in resultados if r.abriu]
    if not testados:
        return
    colunas = 3
    linhas = (len(testados) + colunas - 1) // colunas
    folha = Image.new("RGB", (colunas * (LARGURA_MINI + 16) + 16, linhas * (ALTURA_MINI + 60) + 16), (26, 26, 25))
    d = ImageDraw.Draw(folha)
    titulo, texto = fonte_com_acentos(16, negrito=True), fonte_com_acentos(13)
    for i, r in enumerate(testados):
        x = 16 + (i % colunas) * (LARGURA_MINI + 16)
        y = 16 + (i // colunas) * (ALTURA_MINI + 60)
        if r.frame is not None:
            mini = Image.fromarray(cv2.cvtColor(r.frame, cv2.COLOR_BGR2RGB)).resize((LARGURA_MINI, ALTURA_MINI))
            folha.paste(mini, (x, y))
        else:
            d.rectangle([x, y, x + LARGURA_MINI, y + ALTURA_MINI], fill=(60, 60, 58))
        cor = (12, 163, 12) if r.bom else (250, 178, 25)
        d.text((x, y + ALTURA_MINI + 6), f"Câmera {r.indice + 1} - {NOMES_MODOS.get(r.modo, r.modo)}",
               font=titulo, fill=(244, 244, 242))
        d.text((x, y + ALTURA_MINI + 28), r.descricao, font=texto, fill=cor)
    destino.parent.mkdir(parents=True, exist_ok=True)
    folha.save(destino)


def main() -> int:
    loja = any(m in sys.base_prefix for m in ("WindowsApps", "PythonSoftwareFoundation"))
    print(f"Python: {sys.base_prefix}{'  (Microsoft Store)' if loja else ''}")
    if loja:
        print("[AVISO] Este é o Python da Microsoft Store, que costuma receber imagem preta da câmera.")
        print("        Instale o Python 3.11 do python.org e rode o INSTALAR.bat de novo.\n")
    print("Testando as câmeras em cada modo (leva alguns segundos por câmera)...")
    print("Feche a aplicação e outros programas que usam a câmera (Teams, Zoom, navegador).\n")
    resultados = diagnosticar()
    for r in resultados:
        print(f"   Câmera {r.indice + 1}  {NOMES_MODOS.get(r.modo, r.modo):<18} {r.descricao}")

    destino = config.DIR_REPORTS / "diagnostico_camera.png"
    folha_de_contato(resultados, destino)
    if destino.exists():
        print(f"\nImagens de cada teste: {destino}")
        if platform.system() == "Windows":
            os.startfile(destino)  # abre no visualizador de imagens

    melhor = melhor_combinacao(resultados)
    if melhor is None:
        print("\nNenhuma combinação deu imagem boa.")
        if any(r.defeito == "preta" for r in resultados):
            print("Imagem preta quase sempre é a câmera bloqueada, não defeito do programa:")
            print("   - tampa de privacidade: várias webcams Logitech têm uma tampinha deslizante na frente;")
            print("   - Windows: Configurações > Privacidade e segurança > Câmera > ligue \"Acesso à câmera\"")
            print("     e \"Permitir que aplicativos da área de trabalho acessem a câmera\";")
            print("   - teclado de notebook: algumas marcas têm uma tecla (F8/F10) que desliga a câmera;")
            print("   - antivírus com \"proteção de webcam\" (Kaspersky, ESET, Bitdefender, Avast) entrega imagem")
            print("     preta a programas que ele não conhece: libere o python.exe ou o Librahin no antivírus;")
            if platform.system() == "Windows":
                resposta = input("Abrir agora a tela de privacidade da câmera do Windows? [S/n] ").strip().lower()
                if not resposta.startswith("n"):
                    os.startfile("ms-settings:privacy-webcam")
        if any(r.lenta for r in resultados):
            print("Poucos quadros por segundo costuma ser a porta USB ou falta de luz:")
            print("   - ligue a webcam direto no computador (sem hub nem extensão), de preferência USB 3 (azul);")
            print("   - no Logi Tune / Logitech Capture, desligue \"RightLight\" / pouca luz, que reduz o FPS;")
        print("Tente também:")
        print("   - abrir o app Câmera do Windows: se lá também falhar, o problema é a câmera ou o driver;")
        print("   - trocar a webcam de porta USB (de preferência direto no computador, sem hub);")
        print("   - fechar programas da própria câmera (ex.: Logitech Capture, Logi Tune);")
        print("   - reinstalar o driver da câmera pelo Gerenciador de Dispositivos.")
        return 1

    print(f"\nMelhor: Câmera {melhor.indice + 1} no modo {NOMES_MODOS[melhor.modo]} ({melhor.descricao}).")
    resposta = input("Usar essa combinação na aplicação e na gravação? [S/n] ").strip().lower()
    if resposta.startswith("n"):
        return 0
    preferencias.carregar()
    preferencias.definir("indice_camera", melhor.indice)
    preferencias.definir("modo_camera", melhor.modo)
    print("Salvo. Abra a aplicação de novo (opção 1).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
