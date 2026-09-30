"""Peças da interface gráfica que não precisam abrir janela (sem monitor/X11)."""

import pytest

pytest.importorskip("tkinter")
ctk = pytest.importorskip("customtkinter")

from PIL import Image, ImageDraw  # noqa: E402

from libras import config, interface  # noqa: E402


def test_tela_vazia_tem_os_dois_temas_e_cantos_arredondados():
    imagem = interface._tela_vazia("Câmera desligada", "Clique em Iniciar câmera.")
    assert isinstance(imagem, ctk.CTkImage)
    assert imagem.cget("size") == interface.TAMANHO_VIDEO
    claro, escuro = imagem.cget("light_image"), imagem.cget("dark_image")
    for tema, img in enumerate((claro, escuro)):
        assert img.mode == "RGBA"
        assert img.getpixel((0, 0))[3] == 0                          # canto transparente
        cor = interface.FUNDO_VIDEO[tema].lstrip("#")
        assert img.getpixel((20, img.height // 2))[:3] == tuple(int(cor[i:i + 2], 16) for i in (0, 2, 4))
    assert interface._tela_vazia("Câmera desligada", "Clique em Iniciar câmera.") is imagem  # em cache


def test_quebra_de_linhas_respeita_a_largura():
    d = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    fonte = interface.fonte_com_acentos(15)
    linhas = interface._quebrar_linhas(d, "uma frase comprida " * 8, fonte, 200)
    assert len(linhas) > 1 and all(d.textlength(l, font=fonte) <= 200 for l in linhas)
    assert interface._quebrar_linhas(d, "palavragrandedemaisparacaber", fonte, 20) == ["palavragrandedemaisparacaber"]


def test_arredondar_video_deixa_so_os_cantos_transparentes():
    quadro = interface._arredondar(Image.new("RGB", (640, 360), (10, 20, 30)), interface.RAIO)
    assert quadro.mode == "RGBA"
    assert quadro.getpixel((0, 0))[3] == 0 and quadro.getpixel((320, 180)) == (10, 20, 30, 255)


def test_creditos_no_config():
    assert len(config.EQUIPE) == 4 and config.ORIENTADOR and config.TITULO_TRABALHO
