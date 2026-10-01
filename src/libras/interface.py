"""Interface gráfica para demonstração (CustomTkinter).

Organização das threads:
- thread da interface (Tk): desenha a janela e, a cada ~30 ms (`after`), lê o
  último quadro e os eventos da câmera. Nunca espera pela câmera.
- thread de carregamento: na abertura, importa o MediaPipe e carrega o modelo
  enquanto a janela já aparece com "Carregando". Nunca mexe em widgets.
- thread da câmera (captura.ProcessadorCamera): câmera -> MediaPipe ->
  reconhecimento. Nunca mexe em widgets.
- thread da voz (voz.Voz): fala sem bloquear nenhuma das outras.

A frase (frase.GerenciadorSentenca) vive na thread da interface: as palavras
chegam como eventos e os botões mexem nela diretamente, sem disputa entre threads.

Visual: cores neutras com um único azul de destaque; verde, amarelo e vermelho
só para estados (câmera, modelo, mãos, voz), sempre com o texto ao lado; fonte
do sistema (Segoe UI no Windows).
"""

from __future__ import annotations

import queue
import sys
import threading
import time
import tkinter
import warnings
from functools import lru_cache

import customtkinter as ctk
import cv2
from PIL import Image, ImageDraw

import libras
from libras import config, preferencias
from libras.camera import listar_cameras
from libras.classificador import ErroClassificador, carregar_classificador
from libras.desenho import descrever_maos, fonte_com_acentos, icone_mao
from libras.estabilizador import Estabilizador
from libras.frase import GerenciadorSentenca
from libras.traducao import carregar_tabela_padrao
from libras.verificacao import DURACAO_S as DURACAO_VERIFICACAO_S
from libras.verificacao import VerificacaoAmbiente, brilho_medio, largura_ombros
from libras.voz import Voz

WINDOWS = sys.platform.startswith("win")
INTERVALO_MS = 30
TAMANHO_VIDEO = (640, 480)
RAIO = 10  # cantos arredondados dos painéis e do vídeo

# Cores: (tema claro, tema escuro)
FUNDO_JANELA = ("#f1f1ef", "#111110")
SUPERFICIE = ("#fcfcfb", "#1a1a19")
BORDA = ("#e1e0d9", "#2c2c2a")
TEXTO = ("#0b0b0b", "#f4f4f2")
TEXTO_SECUNDARIO = ("#52514e", "#c3c2b7")
TEXTO_APAGADO = ("#898781", "#898781")
DESTAQUE = "#256abf"
DESTAQUE_HOVER = "#1c5cab"
BOTAO = ("#ffffff", "#242423")
BOTAO_HOVER = ("#efefec", "#2e2e2c")
BORDA_BOTAO = ("#d6d5ce", "#3a3a37")
FUNDO_ETIQUETA = ("#ebeae6", "#2a2a28")          # teclas e palavras da sequência
FUNDO_ETIQUETA_NOVA = ("#dbe7f8", "#1c3350")     # a palavra confirmada por último
FUNDO_VIDEO = ("#e9e8e4", "#0d0d0c")             # painel da câmera sem imagem
MAO_VIDEO = ("#c9c7c0", "#3a3936")
# Medidor de confiança: (preenchimento, trilho) por tema. O trilho é um tom claro
# da mesma cor; acima do limite é azul, abaixo é amarelo (com o texto explicando).
MEDIDOR_ACEITO = (("#2a78d6", "#cde2fb"), ("#3987e5", "#133f73"))
MEDIDOR_BAIXO = (("#fab219", "#fcefd2"), ("#fab219", "#4a3a17"))
# Estados (sempre acompanhados de texto)
STATUS_OK = "#0ca30c"
STATUS_ATENCAO = "#fab219"
STATUS_ERRO = "#d03b3b"
STATUS_NEUTRO = "#898781"

TEXTOS_VAZIOS = {
    "desligada": ("Câmera desligada",
                  "Clique em Iniciar câmera. Fique a cerca de 1 metro, com os ombros e as mãos visíveis."),
    "iniciando": ("Iniciando a câmera", "Abrindo a câmera..."),
}


def _som(texto: str) -> str:
    """Como o texto soa: sem maiúsculas, pontuação nem hífens ("Sim." e "SIM" soam igual)."""
    return " ".join("".join(c for c in texto.lower() if c.isalnum() or c.isspace()).split())


def _fonte(tamanho: int, forte: bool = False) -> ctk.CTkFont:
    """Segoe UI (Semibold) no Windows; nos outros sistemas, a fonte padrão do CustomTkinter."""
    if WINDOWS:
        return ctk.CTkFont(family="Segoe UI Semibold" if forte else "Segoe UI", size=tamanho)
    return ctk.CTkFont(size=tamanho, weight="bold" if forte else "normal")


# --- imagens do painel da câmera ------------------------------------------------------

@lru_cache(maxsize=32)
def _mascara(tamanho: tuple[int, int], raio: int) -> Image.Image:
    mascara = Image.new("L", tamanho, 0)
    ImageDraw.Draw(mascara).rounded_rectangle([0, 0, tamanho[0] - 1, tamanho[1] - 1], radius=raio, fill=255)
    return mascara


def _arredondar(imagem: Image.Image, raio: int) -> Image.Image:
    """Cantos transparentes: a imagem fica com a mesma forma dos painéis."""
    if imagem.mode != "RGB":
        imagem = imagem.convert("RGB")
    imagem.putalpha(_mascara(imagem.size, raio))
    return imagem


def _quebrar_linhas(desenho: ImageDraw.ImageDraw, texto: str, fonte, largura_max: float) -> list[str]:
    linhas, atual = [], ""
    for palavra in texto.split():
        tentativa = f"{atual} {palavra}".strip()
        if not atual or desenho.textlength(tentativa, font=fonte) <= largura_max:
            atual = tentativa
        else:
            linhas.append(atual)
            atual = palavra
    return linhas + ([atual] if atual else [])


@lru_cache(maxsize=16)
def _tela_vazia(titulo: str, dica: str = "") -> ctk.CTkImage:
    """Painel da câmera sem imagem (carregando, desligada, iniciando, erro), nos dois
    temas. Desenhado com o dobro da resolução para o texto ficar nítido com a escala
    de tela do Windows (125%, 150%...)."""
    k = 2
    largura, altura = TAMANHO_VIDEO[0] * k, TAMANHO_VIDEO[1] * k
    fonte_titulo = fonte_com_acentos(22 * k, negrito=True)
    fonte_dica = fonte_com_acentos(15 * k)
    imagens = []
    for tema in (0, 1):
        imagem = Image.new("RGB", (largura, altura), FUNDO_VIDEO[tema])
        d = ImageDraw.Draw(imagem)
        mao = icone_mao(76 * k, MAO_VIDEO[tema])
        linhas = _quebrar_linhas(d, dica, fonte_dica, 440 * k) if dica else []
        altura_linha = 23 * k
        total = mao.height + 22 * k + 30 * k + (12 * k + altura_linha * len(linhas) if linhas else 0)
        y = (altura - total) // 2
        imagem.paste(mao, ((largura - mao.width) // 2, y), mao)
        y += mao.height + 22 * k
        d.text((largura / 2, y), titulo, font=fonte_titulo, fill=TEXTO[tema], anchor="mt")
        y += 30 * k + 12 * k
        for linha in linhas:
            d.text((largura / 2, y), linha, font=fonte_dica, fill=TEXTO_SECUNDARIO[tema], anchor="mt")
            y += altura_linha
        imagens.append(_arredondar(imagem, RAIO * k))
    return ctk.CTkImage(light_image=imagens[0], dark_image=imagens[1], size=TAMANHO_VIDEO)


# --- componentes -------------------------------------------------------------------------

class Medidor(ctk.CTkFrame):
    """Barra de confiança (0 a 100%) com uma marca no limite de aceitação."""

    def __init__(self, master, limite: float) -> None:
        super().__init__(master, fg_color="transparent", height=16)
        self._limite = limite
        self._valor = 0.0
        self._aceito = True
        self._canvas = tkinter.Canvas(self, highlightthickness=0, borderwidth=0)
        self._canvas.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._canvas.bind("<Configure>", lambda _e: self._desenhar())

    def definir(self, valor: float, aceito: bool) -> None:
        valor = min(max(valor, 0.0), 1.0)
        if (valor, aceito) != (self._valor, self._aceito):
            self._valor, self._aceito = valor, aceito
            self._desenhar()

    def definir_limite(self, limite: float) -> None:
        self._limite = limite
        self._desenhar()

    def _set_appearance_mode(self, modo) -> None:
        super()._set_appearance_mode(modo)
        self._desenhar()

    def _desenhar(self) -> None:
        c = self._canvas
        fundo = self._apply_appearance_mode(SUPERFICIE)
        c.configure(bg=fundo)
        c.delete("all")
        largura, altura = c.winfo_width(), c.winfo_height()
        if largura < 20 or altura < 4:
            return
        escala = self._get_widget_scaling()
        espessura = max(3, round(6 * escala))
        y = altura / 2
        x0, x1 = espessura / 2 + 1, largura - espessura / 2 - 1
        tema = 1 if ctk.get_appearance_mode() == "Dark" else 0
        cheio, trilho = (MEDIDOR_ACEITO if self._aceito else MEDIDOR_BAIXO)[tema]
        if self._valor == 0:
            trilho = BORDA[tema]  # sem sinal: trilho neutro, para não parecer preenchido
        c.create_line(x0, y, x1, y, width=espessura, capstyle="round", fill=trilho)
        if self._valor > 0:
            c.create_line(x0, y, x0 + (x1 - x0) * self._valor, y, width=espessura, capstyle="round", fill=cheio)
        x_limite = x0 + (x1 - x0) * self._limite
        marca = max(1, round(2 * escala))
        c.create_line(x_limite, 0, x_limite, altura, width=marca + 2 * max(1, round(escala)), fill=fundo)
        c.create_line(x_limite, 1, x_limite, altura - 1, width=marca,
                      fill=self._apply_appearance_mode(TEXTO_SECUNDARIO))


class Indicador(ctk.CTkFrame):
    """Item da barra de status: um ponto colorido e o texto (a cor nunca aparece sozinha)."""

    def __init__(self, master, fonte) -> None:
        super().__init__(master, fg_color="transparent")
        self._ponto = ctk.CTkFrame(self, width=8, height=8, corner_radius=4, fg_color=STATUS_NEUTRO)
        self._ponto.pack(side="left", padx=(0, 7))
        self._texto = ctk.CTkLabel(self, text="", font=fonte, text_color=TEXTO_SECUNDARIO, height=20)
        self._texto.pack(side="left")
        self._estado = None

    def definir(self, texto: str, cor: str) -> None:
        if (texto, cor) != self._estado:
            self._estado = (texto, cor)
            self._ponto.configure(fg_color=cor)
            self._texto.configure(text=texto)


def _janela_auxiliar(app, titulo: str) -> ctk.CTkToplevel:
    """Janela secundária com o visual da aplicação (ícone, cor, fecha com Esc)."""
    janela = ctk.CTkToplevel(app)
    janela.title(titulo)
    janela.configure(fg_color=SUPERFICIE)
    janela.transient(app)
    app._definir_icone(janela)
    janela.bind("<Escape>", lambda _e: janela.destroy())
    return janela


def _centralizar(app, janela) -> None:
    janela.update_idletasks()
    x = app.winfo_rootx() + (app.winfo_width() - janela.winfo_reqwidth()) // 2
    y = app.winfo_rooty() + (app.winfo_height() - janela.winfo_reqheight()) // 3
    janela.wm_geometry(f"+{max(0, x)}+{max(0, y)}")
    janela.after(60, lambda: AplicacaoLibras._focar_janela(janela))


def _titulo_secao(master, texto: str, fonte) -> None:
    ctk.CTkLabel(master, text=texto, font=fonte, text_color=TEXTO, anchor="w").pack(fill="x", pady=(16, 4))


class JanelaConfiguracoes:
    """Configurações salvas neste computador (preferencias.json), aplicadas na hora."""

    def __init__(self, app: "AplicacaoLibras") -> None:
        self.app = app
        self._agendados: dict = {}
        v = preferencias.valores()
        j = self.janela = _janela_auxiliar(app, "Configurações")
        j.resizable(False, False)
        corpo = ctk.CTkFrame(j, fg_color="transparent")
        corpo.pack(padx=26, pady=(12, 20), fill="both")
        f_secao, f_texto, f_peq = _fonte(15, forte=True), app._f_texto, app._f_pequeno

        _titulo_secao(corpo, "Reconhecimento", f_secao)
        self._slider(corpo, "Confiança mínima para confirmar um sinal", "limiar_confianca", 0.5, 0.95, 9,
                     v["limiar_confianca"], lambda x: f"{x:.0%}")
        self._chave(corpo, f"Confirmação rápida quando a confiança passa de {config.LIMIAR_CONFIRMACAO_RAPIDA:.0%}",
                    "confirmacao_adaptativa", v["confirmacao_adaptativa"])
        ctk.CTkLabel(corpo, text="Modo leve (para computadores lentos)", font=f_texto, text_color=TEXTO,
                     anchor="w").pack(fill="x", pady=(10, 4))
        opcoes = {"Automático": "auto", "Ligado": "ligado", "Desligado": "desligado"}
        leve = ctk.CTkSegmentedButton(corpo, values=list(opcoes), font=f_peq, selected_color=DESTAQUE,
                                      selected_hover_color=DESTAQUE_HOVER,
                                      command=lambda rotulo: app._aplicar_preferencia("modo_leve", opcoes[rotulo]))
        leve.set(next(r for r, valor in opcoes.items() if valor == v["modo_leve"]))
        leve.pack(anchor="w")

        _titulo_secao(corpo, "Câmera", f_secao)
        ctk.CTkLabel(corpo, text="Modo da câmera (troque se a imagem vier com listras ou não abrir)",
                     font=f_texto, text_color=TEXTO, anchor="w").pack(fill="x", pady=(0, 4))
        modos = {"Automático": "auto", "DirectShow": "dshow", "DirectShow MJPG": "dshow_mjpg",
                 "Media Foundation": "msmf", "Media Foundation (resolução da câmera)": "msmf_nativo",
                 "DirectShow (resolução da câmera)": "dshow_nativo"}
        modo = ctk.CTkOptionMenu(corpo, values=list(modos), width=320, font=f_peq, dropdown_font=f_peq,
                                 fg_color=BOTAO, button_color=BOTAO, button_hover_color=BOTAO_HOVER,
                                 text_color=TEXTO, dropdown_fg_color=SUPERFICIE,
                                 dropdown_hover_color=BOTAO_HOVER, dropdown_text_color=TEXTO,
                                 command=lambda rotulo: app._aplicar_preferencia("modo_camera", modos[rotulo]))
        modo.set(next((r for r, valor in modos.items() if valor == v["modo_camera"]), "Automático"))
        modo.pack(anchor="w")

        _titulo_secao(corpo, "Frase", f_secao)
        self._chave(corpo, "Encerrar a frase sozinho depois de uma pausa", "finalizar_por_pausa",
                    v["finalizar_por_pausa"])
        self._slider(corpo, "Pausa para encerrar a frase", "pausa_frase_s", 1.0, 6.0, 10, v["pausa_frase_s"],
                     lambda x: f"{x:.1f} s".replace(".", ","))

        _titulo_secao(corpo, "Voz", f_secao)
        self._slider(corpo, "Velocidade da voz", "taxa_fala", 100, 260, 16, v["taxa_fala"],
                     lambda x: "lenta" if x < 150 else "normal" if x <= 190 else "rápida", inteiro=True)
        self._chave(corpo, "Falar cada palavra assim que for reconhecida", "falar_cada_palavra",
                    v["falar_cada_palavra"])
        linha = ctk.CTkFrame(corpo, fg_color="transparent")
        linha.pack(fill="x", pady=(10, 0))
        app._botao_secundario(linha, "Testar voz", lambda: app._falar("Olá, eu sou o Librahin.")).pack(side="left")
        app._botao_secundario(linha, "Verificar ambiente", self._verificar).pack(side="left", padx=(8, 0))

        ctk.CTkFrame(corpo, height=1, corner_radius=0, fg_color=BORDA).pack(fill="x", pady=(18, 12))
        ctk.CTkLabel(corpo, text="As mudanças valem na hora e ficam salvas neste computador.", font=f_peq,
                     text_color=TEXTO_SECUNDARIO, anchor="w").pack(fill="x")
        rodape = ctk.CTkFrame(corpo, fg_color="transparent")
        rodape.pack(fill="x", pady=(12, 0))
        app._botao_secundario(rodape, "Restaurar padrão", self._restaurar).pack(side="left")
        app._botao_primario(rodape, "Fechar", j.destroy).pack(side="right")
        _centralizar(app, j)

    def _chave(self, master, texto, nome, valor) -> None:
        variavel = ctk.BooleanVar(value=valor)
        ctk.CTkSwitch(master, text=texto, variable=variavel, font=self.app._f_texto, text_color=TEXTO,
                      progress_color=DESTAQUE, switch_width=34, switch_height=18,
                      command=lambda: self.app._aplicar_preferencia(nome, variavel.get())).pack(anchor="w", pady=4)

    def _slider(self, master, texto, nome, minimo, maximo, passos, valor, formato, inteiro=False) -> None:
        cabecalho = ctk.CTkFrame(master, fg_color="transparent")
        cabecalho.pack(fill="x", pady=(8, 0))
        ctk.CTkLabel(cabecalho, text=texto, font=self.app._f_texto, text_color=TEXTO).pack(side="left")
        rotulo = ctk.CTkLabel(cabecalho, text=formato(valor), font=self.app._f_texto, text_color=TEXTO_SECUNDARIO)
        rotulo.pack(side="right")

        def mudou(x):
            x = int(round(x)) if inteiro else round(float(x), 2)
            rotulo.configure(text=formato(x))
            # espera a pessoa soltar o controle (a voz, por exemplo, é recarregada a cada mudança)
            if nome in self._agendados:
                self.janela.after_cancel(self._agendados[nome])
            self._agendados[nome] = self.janela.after(350, lambda: self.app._aplicar_preferencia(nome, x))

        slider = ctk.CTkSlider(master, from_=minimo, to=maximo, number_of_steps=passos, command=mudou,
                               progress_color=DESTAQUE, button_color=DESTAQUE, button_hover_color=DESTAQUE_HOVER,
                               width=400)
        slider.set(valor)
        slider.pack(anchor="w", pady=(4, 2))

    def _verificar(self) -> None:
        if self.app.estado_camera != "ligada":
            self.app._mostrar_aviso("Ligue a câmera para verificar o ambiente.")
            return
        self.janela.destroy()
        self.app._iniciar_verificacao()

    def _restaurar(self) -> None:
        preferencias.restaurar_padrao()
        for nome, valor in preferencias.valores().items():
            self.app._aplicar_preferencia(nome, valor, salvar=False)
        self.janela.destroy()
        self.app._abrir_configuracoes()


class JanelaHistorico:
    """Frases finalizadas nesta sessão, da mais recente para a mais antiga, com copiar."""

    def __init__(self, app: "AplicacaoLibras") -> None:
        self.app = app
        j = self.janela = _janela_auxiliar(app, "Histórico de frases")
        j.geometry("560x480")
        self.lista = ctk.CTkScrollableFrame(j, fg_color=SUPERFICIE)
        self.lista.pack(fill="both", expand=True, padx=16, pady=(16, 8))
        rodape = ctk.CTkFrame(j, fg_color="transparent")
        rodape.pack(fill="x", padx=16, pady=(0, 16))
        app._botao_secundario(rodape, "Copiar tudo", self._copiar_tudo).pack(side="left")
        app._botao_secundario(rodape, "Limpar histórico", self._limpar).pack(side="left", padx=(8, 0))
        app._botao_primario(rodape, "Fechar", j.destroy).pack(side="right")
        self.atualizar()
        _centralizar(app, j)

    def atualizar(self) -> None:
        for filho in self.lista.winfo_children():
            filho.destroy()
        if not self.app.historico:
            ctk.CTkLabel(self.lista, text="Nenhuma frase ainda. As frases finalizadas aparecem aqui.",
                         font=self.app._f_texto, text_color=TEXTO_APAGADO).pack(anchor="w", pady=8)
            return
        for hora, frase, glosa in reversed(self.app.historico):
            linha = ctk.CTkFrame(self.lista, fg_color="transparent")
            linha.pack(fill="x", pady=(0, 10))
            textos = ctk.CTkFrame(linha, fg_color="transparent")
            textos.pack(side="left", fill="x", expand=True)
            ctk.CTkLabel(textos, text=hora, font=self.app._f_pequeno, text_color=TEXTO_SECUNDARIO,
                         height=16, anchor="w").pack(fill="x")
            ctk.CTkLabel(textos, text=frase, font=_fonte(15, forte=True), text_color=TEXTO, wraplength=380,
                         justify="left", anchor="w").pack(fill="x")
            if glosa != frase:
                ctk.CTkLabel(textos, text=f"Sinais: {glosa}", font=self.app._f_pequeno,
                             text_color=TEXTO_SECUNDARIO, height=16, anchor="w").pack(fill="x")
            self.app._botao_secundario(linha, "Copiar", lambda t=frase: self.app._copiar(t), largura=76).pack(
                side="right", anchor="n")

    def _copiar_tudo(self) -> None:
        self.app._copiar("\n".join(f"{hora}  {frase}" for hora, frase, _ in self.app.historico))

    def _limpar(self) -> None:
        self.app.historico.clear()
        self.atualizar()


class JanelaApresentacao:
    """Tela cheia para a plateia: a câmera grande e a frase em letras grandes, como legenda.
    F11 alterna tela cheia; Esc fecha. Espaço, Backspace e C continuam funcionando."""

    def __init__(self, app: "AplicacaoLibras") -> None:
        self.app = app
        j = self.janela = ctk.CTkToplevel(app)
        j.title("Librahin - apresentação")
        j.configure(fg_color="#0d0d0c")
        app._definir_icone(j)
        largura, altura = j.winfo_screenwidth(), j.winfo_screenheight()
        escala = ctk.ScalingTracker.get_window_scaling(j) if hasattr(ctk, "ScalingTracker") else 1.0
        largura, altura = int(largura / escala), int(altura / escala)
        h_video = int(altura * 0.66)
        self.tamanho_video = (min(int(h_video * 4 / 3), largura - 80), h_video)
        self.video = ctk.CTkLabel(j, text="", fg_color="transparent")
        self.video.pack(pady=(24, 12))
        self.lbl_glosa = ctk.CTkLabel(j, text="", font=_fonte(20), text_color="#9a9993")
        self.lbl_glosa.pack()
        self.lbl_frase = ctk.CTkLabel(j, text="", font=_fonte(44, forte=True), text_color="#ffffff",
                                      wraplength=largura - 120, justify="center")
        self.lbl_frase.pack(pady=(4, 0))
        self.lbl_dica = ctk.CTkLabel(j, text="Esc sai da apresentação   F11 alterna a tela cheia",
                                     font=_fonte(12), text_color="#6f6e69")
        self.lbl_dica.place(relx=1.0, rely=0.0, x=-16, y=10, anchor="ne")
        j.after(4000, lambda: self.lbl_dica.place_forget() if j.winfo_exists() else None)
        self._imagem = None
        self._textos = None
        self.tela_cheia = True
        j.attributes("-fullscreen", True)
        j.bind("<Escape>", lambda _e: self.fechar())
        j.bind("<F11>", lambda _e: self.alternar_tela_cheia())
        j.bind("<space>", lambda _e: app._finalizar_frase())
        j.bind("<BackSpace>", lambda _e: app._remover_ultima())
        j.bind("<KeyPress-c>", lambda _e: app._limpar())
        j.protocol("WM_DELETE_WINDOW", self.fechar)
        j.after(80, lambda: (j.lift(), j.focus_force()))

    @property
    def aberta(self) -> bool:
        return self.janela.winfo_exists()

    def alternar_tela_cheia(self) -> None:
        self.tela_cheia = not self.tela_cheia
        self.janela.attributes("-fullscreen", self.tela_cheia)

    def fechar(self) -> None:
        self.janela.destroy()
        self.app.apresentacao = None

    def mostrar_quadro(self, imagem: Image.Image) -> None:
        largura, altura = self.tamanho_video
        fator = min(largura / imagem.width, altura / imagem.height)
        grande = imagem.resize((int(imagem.width * fator), int(imagem.height * fator)), Image.BILINEAR)
        self._imagem = ctk.CTkImage(light_image=grande, dark_image=grande, size=grande.size)
        self.video.configure(image=self._imagem)

    def mostrar_vazia(self, imagem: ctk.CTkImage) -> None:
        largura, altura = self.tamanho_video
        tamanho = (min(largura, int(altura * 4 / 3)), altura)
        self._imagem = ctk.CTkImage(light_image=imagem.cget("dark_image"), dark_image=imagem.cget("dark_image"),
                                    size=tamanho)
        self.video.configure(image=self._imagem)

    def atualizar(self, frase: str, glosa: str) -> None:
        if (frase, glosa) != self._textos:
            self._textos = (frase, glosa)
            self.lbl_frase.configure(text=frase or " ")
            self.lbl_glosa.configure(text=f"Sinais: {glosa}" if glosa and glosa != frase else " ")


class JanelaVerificacao:
    """Resultado da verificação do ambiente, com uma dica para cada problema."""

    def __init__(self, app: "AplicacaoLibras", verificacao: VerificacaoAmbiente) -> None:
        j = _janela_auxiliar(app, "Verificação do ambiente")
        j.resizable(False, False)
        corpo = ctk.CTkFrame(j, fg_color="transparent")
        corpo.pack(padx=26, pady=(20, 20))
        titulo = ("Tudo pronto para reconhecer os sinais" if verificacao.tudo_ok
                  else "Alguns ajustes vão melhorar o reconhecimento")
        ctk.CTkLabel(corpo, text=titulo, font=_fonte(17, forte=True), text_color=TEXTO,
                     anchor="w").pack(fill="x", pady=(0, 12))
        cores = {True: STATUS_OK, False: STATUS_ATENCAO, None: STATUS_NEUTRO}
        for item in verificacao.resultado():
            linha = ctk.CTkFrame(corpo, fg_color="transparent")
            linha.pack(fill="x", pady=4)
            ctk.CTkFrame(linha, width=9, height=9, corner_radius=5, fg_color=cores[item.ok]).pack(
                side="left", anchor="n", pady=(7, 0), padx=(0, 10))
            ctk.CTkLabel(linha, text=item.nome, font=_fonte(14, forte=True), text_color=TEXTO, width=82,
                         anchor="w").pack(side="left", anchor="n")
            ctk.CTkLabel(linha, text=item.texto, font=app._f_texto, text_color=TEXTO_SECUNDARIO, wraplength=320,
                         justify="left", anchor="w").pack(side="left", anchor="n")
        rodape = ctk.CTkFrame(corpo, fg_color="transparent")
        rodape.pack(fill="x", pady=(16, 0))
        app._botao_secundario(rodape, "Verificar de novo",
                              lambda: (j.destroy(), app._iniciar_verificacao())).pack(side="left")
        app._botao_primario(rodape, "Fechar", j.destroy).pack(side="right")
        _centralizar(app, j)


# --- janela --------------------------------------------------------------------------------

class AplicacaoLibras(ctk.CTk):
    def __init__(self, indice_camera: int | None = None) -> None:
        super().__init__()
        self.title("Librahin")
        self._definir_icone(self)
        self._ajustar_tamanho()
        self.indice_camera = config.INDICE_CAMERA if indice_camera is None else indice_camera
        self.cameras: list[int] | None = None      # índices encontrados (None = ainda procurando)
        self._fila_cameras: queue.Queue = queue.Queue()
        self._religar_camera = False               # trocou de câmera com ela ligada

        # Carregados em segundo plano (_carregar), para a janela aparecer na hora
        self.classificador = None
        self.erro_modelo: str | None = None
        self.aviso_modelo: str | None = None
        self._ProcessadorCamera = None
        self._carregando = True
        self._fila_carga: queue.Queue = queue.Queue()

        self.processador = None
        self.estado_camera = "desligada"   # desligada, iniciando, ligada, desligando
        self.erro_camera: str | None = None
        self._ultimo_resultado = None
        self._imagem_tk = None
        self._janela_sobre = None
        self._aviso_agendado = None
        self._aviso_atual = ""
        self._textos: dict = {}            # último texto/cor de cada rótulo (evita redesenhar à toa)
        self._sequencia_mostrada: tuple | None = None
        self._estabilizador: Estabilizador | None = None
        self.historico: list[tuple[str, str, str]] = []   # (hora, frase, glosa) das frases finalizadas
        self._janela_config = None
        self._janela_historico: JanelaHistorico | None = None
        self.apresentacao: JanelaApresentacao | None = None
        self._imagem_vazia: ctk.CTkImage | None = None
        self._verificacao: VerificacaoAmbiente | None = None
        self._fim_verificacao = 0.0
        self._verificar_ao_ligar = not preferencias.estado("verificacao_feita")

        self.tabela = carregar_tabela_padrao()  # frases.txt (None se desligada no config)
        self.sentenca = GerenciadorSentenca(ao_finalizar=self._ao_finalizar, tabela=self.tabela,
                                            pausa_s=config.PAUSA_FRASE_S)
        # A voz se prepara na própria thread (no Windows leva ~1 s). Sem callback: a
        # thread da voz não pode mexer no Tkinter; os erros são lidos em _ciclo.
        self.voz = Voz(timeout_inicio=0)
        self._erro_voz_mostrado = None

        self._criar_fontes()
        self._montar_tela()
        self._mostrar_imagem(_tela_vazia("Carregando", "Preparando o reconhecimento de mãos..."))
        self._atualizar_textos()
        self._atualizar_indicadores()

        self.protocol("WM_DELETE_WINDOW", self._fechar)
        self.bind("<space>", lambda _e: self._finalizar_frase())
        self.bind("<BackSpace>", lambda _e: self._remover_ultima())
        self.bind("<KeyPress-c>", lambda _e: self._limpar())
        self.bind("<F11>", lambda _e: self._abrir_apresentacao())
        if self.tabela is not None and self.tabela.avisos:
            for aviso in self.tabela.avisos:
                print(f"[AVISO] frases.txt: {aviso}")
            self.after(500, lambda: self._mostrar_aviso(
                f"frases.txt: {self.tabela.avisos[0]}" + (" (+ outros no terminal)" if len(self.tabela.avisos) > 1 else "")))
        threading.Thread(target=self._carregar, name="carregamento", daemon=True).start()
        self.after(INTERVALO_MS, self._ciclo)

    # --- inicialização ------------------------------------------------------------------

    def _definir_icone(self, janela) -> None:
        try:
            if WINDOWS and config.ARQ_ICONE_ICO.is_file():
                janela.iconbitmap(str(config.ARQ_ICONE_ICO))
            elif config.ARQ_ICONE_PNG.is_file():
                self._foto_icone = tkinter.PhotoImage(file=str(config.ARQ_ICONE_PNG))
                janela.iconphoto(False, self._foto_icone)
        except tkinter.TclError:
            pass  # sem ícone próprio: fica o padrão

    def _ajustar_tamanho(self) -> None:
        """1180x720, ou menos em telas pequenas (ex.: notebook 1366x768)."""
        try:
            escala = ctk.ScalingTracker.get_window_scaling(self)
        except Exception:
            escala = 1.0
        largura = min(1180, int(self.winfo_screenwidth() / escala) - 40)
        altura = min(720, int(self.winfo_screenheight() / escala) - 80)
        self.geometry(f"{largura}x{altura}")
        self.minsize(min(1040, largura), min(640, altura))

    def _carregar(self) -> None:
        """Thread de carregamento: só a fila, nada de widgets aqui."""
        try:
            from libras.captura import ProcessadorCamera  # importa o MediaPipe (alguns segundos)
            self._fila_carga.put(("etapa", "Carregando o modelo de sinais..."))
            classificador = erro = aviso = None
            try:
                with warnings.catch_warnings(record=True) as avisos:
                    warnings.simplefilter("always")
                    classificador = carregar_classificador()
                aviso = str(avisos[0].message) if avisos else None
            except ErroClassificador as e:
                erro = str(e)
            # antes de liberar o botão: procurar e ligar a câmera ao mesmo tempo daria conflito
            self._fila_carga.put(("etapa", "Procurando câmeras..."))
            self._procurar_cameras()
            self._fila_carga.put(("pronto", (ProcessadorCamera, classificador, erro, aviso)))
        except Exception as e:  # nunca deixar a janela presa em "Carregando"
            self._fila_carga.put(("falha", str(e)))

    def _procurar_cameras(self) -> None:
        """Procura as câmeras (em thread; a câmera deste programa precisa estar desligada)."""
        try:
            self._fila_cameras.put(listar_cameras())
        except Exception:
            self._fila_cameras.put([])

    def _verificar_carga(self) -> None:
        while True:
            try:
                tipo, dado = self._fila_carga.get_nowait()
            except queue.Empty:
                return
            if tipo == "etapa":
                self._mostrar_imagem(_tela_vazia("Carregando", dado))
            elif tipo == "pronto":
                self._ProcessadorCamera, self.classificador, self.erro_modelo, self.aviso_modelo = dado
                self._carregando = False
                self._estilo_botao_camera()
                self._mostrar_imagem(_tela_vazia(*TEXTOS_VAZIOS["desligada"]))
                if self.erro_modelo:
                    self._mostrar_aviso("Nenhum modelo treinado: a câmera mostra só os pontos das mãos. "
                                        "Treine pelo menu (opção 8).", duracao_ms=10000)
                elif self.aviso_modelo:
                    self._mostrar_aviso(self._resumo_aviso_modelo(), duracao_ms=10000)
            elif tipo == "falha":
                self._carregando = False
                self._mostrar_imagem(_tela_vazia("Não foi possível carregar o reconhecimento", dado))

    def _resumo_aviso_modelo(self) -> str:
        """O aviso do carregamento do modelo em uma frase curta para a tela."""
        treinadas = [c for c in config.CLASSES_OBRIGATORIAS if c in self.classificador.classes]
        if len(treinadas) < len(config.CLASSES_OBRIGATORIAS):
            return (f"O modelo ainda não conhece todos os sinais ({len(treinadas)} de "
                    f"{len(config.CLASSES_OBRIGATORIAS)}). "
                    "Grave os que faltam e treine de novo (menu, opções 3 e 8).")
        return f"Modelo: {self.aviso_modelo}"

    def _criar_fontes(self) -> None:
        self._f_marca = _fonte(15, forte=True)
        self._f_rotulo = _fonte(13)
        self._f_sinal = _fonte(40, forte=True)
        self._f_vazio = _fonte(20)
        self._f_percentual = _fonte(16, forte=True)
        self._f_valor = _fonte(20, forte=True)
        self._f_palavra = _fonte(15, forte=True)
        self._f_frase = _fonte(22, forte=True)
        self._f_texto = _fonte(14)
        self._f_pequeno = _fonte(12)
        self._f_botao = _fonte(13)
        self._f_botao_forte = _fonte(14, forte=True)

    # --- montagem da tela --------------------------------------------------------------

    def _montar_tela(self) -> None:
        self.configure(fg_color=FUNDO_JANELA)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._montar_topo()
        self._montar_conteudo()
        self._montar_status()

    def _montar_topo(self) -> None:
        topo = ctk.CTkFrame(self, fg_color=SUPERFICIE, corner_radius=0, height=52)
        topo.grid(row=0, column=0, sticky="ew")
        topo.pack_propagate(False)
        ctk.CTkFrame(topo, height=1, corner_radius=0, fg_color=BORDA).pack(side="bottom", fill="x")
        if config.ARQ_ICONE_PNG.is_file():
            self._pil_icone = Image.open(config.ARQ_ICONE_PNG)
        else:
            self._pil_icone = icone_mao(64, "#ffffff", DESTAQUE)
        self._img_icone = ctk.CTkImage(light_image=self._pil_icone, dark_image=self._pil_icone, size=(24, 24))
        ctk.CTkLabel(topo, image=self._img_icone, text="").pack(side="left", padx=(20, 10))
        ctk.CTkLabel(topo, text="Librahin", font=self._f_marca, text_color=TEXTO).pack(side="left")
        ctk.CTkLabel(topo, text="Libras para texto e voz", font=self._f_rotulo,
                     text_color=TEXTO_SECUNDARIO).pack(side="left", padx=(12, 0), pady=(2, 0))
        for texto, comando in (("Sobre", self._abrir_sobre), ("Configurações", self._abrir_configuracoes),
                               ("Histórico", self._abrir_historico), ("Apresentação", self._abrir_apresentacao)):
            ctk.CTkButton(topo, text=texto, width=0, height=30, corner_radius=6, font=self._f_botao,
                          fg_color="transparent", hover_color=BOTAO_HOVER, text_color=TEXTO_SECUNDARIO,
                          command=comando).pack(side="right", padx=(0, 14 if texto == "Sobre" else 2))

    def _botao_secundario(self, master, texto: str, comando, largura: int = 0) -> ctk.CTkButton:
        return ctk.CTkButton(master, text=texto, command=comando, width=largura, height=34, corner_radius=8,
                             font=self._f_botao, fg_color=BOTAO, hover_color=BOTAO_HOVER, text_color=TEXTO,
                             border_width=1, border_color=BORDA_BOTAO)

    def _botao_primario(self, master, texto: str, comando) -> ctk.CTkButton:
        return ctk.CTkButton(master, text=texto, command=comando, width=96, height=34, corner_radius=8,
                             font=self._f_botao_forte, fg_color=DESTAQUE, hover_color=DESTAQUE_HOVER,
                             text_color="#ffffff")

    def _montar_conteudo(self) -> None:
        conteudo = ctk.CTkFrame(self, fg_color="transparent")
        conteudo.grid(row=1, column=0, sticky="nsew", padx=20, pady=16)
        conteudo.grid_columnconfigure(1, weight=1)
        conteudo.grid_rowconfigure(0, weight=1)

        # Coluna da câmera: vídeo, botão da câmera e avisos
        esquerda = ctk.CTkFrame(conteudo, fg_color="transparent")
        esquerda.grid(row=0, column=0, sticky="n")
        area_video = ctk.CTkFrame(esquerda, width=TAMANHO_VIDEO[0], height=TAMANHO_VIDEO[1],
                                  fg_color="transparent")
        area_video.pack()
        area_video.pack_propagate(False)  # tamanho fixo: a janela não "pula" com outra proporção de câmera
        self.video = ctk.CTkLabel(area_video, text="")
        self.video.pack(expand=True)

        controles = ctk.CTkFrame(esquerda, fg_color="transparent")
        controles.pack(fill="x", pady=(12, 0))
        self.btn_camera = ctk.CTkButton(controles, text="", width=172, height=38, corner_radius=8,
                                        command=self._alternar_camera)
        self.btn_camera.pack(side="left", anchor="n")
        self._estilo_botao_camera()
        self.menu_camera = ctk.CTkOptionMenu(
            controles, values=[self._nome_camera(self.indice_camera)], command=self._escolher_camera,
            width=128, height=38, corner_radius=8, font=self._f_botao, dropdown_font=self._f_botao,
            fg_color=BOTAO, button_color=BOTAO, button_hover_color=BOTAO_HOVER, text_color=TEXTO,
            dropdown_fg_color=SUPERFICIE, dropdown_hover_color=BOTAO_HOVER, dropdown_text_color=TEXTO)
        self.menu_camera.set(self._nome_camera(self.indice_camera))
        self.menu_camera.pack(side="left", anchor="n", padx=(8, 0))
        # aviso ao lado do botão, alinhado pela primeira linha (textos longos quebram para baixo)
        self._aviso_ponto = ctk.CTkFrame(controles, width=8, height=8, corner_radius=4, fg_color=STATUS_ATENCAO)
        self.lbl_aviso = ctk.CTkLabel(controles, text="", font=self._f_texto, text_color=TEXTO, height=20,
                                      anchor="nw", justify="left", wraplength=420)
        self.lbl_aviso.pack(side="right", fill="x", expand=True, anchor="n", pady=(9, 0))

        # Coluna dos resultados
        direita = ctk.CTkFrame(conteudo, fg_color="transparent")
        direita.grid(row=0, column=1, sticky="nsew", padx=(20, 0))
        painel = ctk.CTkFrame(direita, fg_color=SUPERFICIE, corner_radius=RAIO, border_width=1,
                              border_color=BORDA)
        painel.pack(fill="x")

        # Sinal detectado agora + confiança
        secao = self._secao(painel, primeira=True)
        cabecalho = ctk.CTkFrame(secao, fg_color="transparent")
        cabecalho.pack(fill="x")
        ctk.CTkLabel(cabecalho, text="Sinal detectado", font=self._f_rotulo, text_color=TEXTO_SECUNDARIO,
                     height=18).pack(side="left")
        self.lbl_conf = ctk.CTkLabel(cabecalho, text="", font=self._f_percentual, text_color=TEXTO, height=18)
        self.lbl_conf.pack(side="right")
        self.lbl_sinal = ctk.CTkLabel(secao, text="", height=54, anchor="w")
        self.lbl_sinal.pack(fill="x")
        self.medidor = Medidor(secao, config.LIMIAR_CONFIANCA)
        self.medidor.pack(fill="x", pady=(2, 4))
        self.lbl_limite = ctk.CTkLabel(secao, text="", font=self._f_pequeno, text_color=TEXTO_SECUNDARIO,
                                       height=16, anchor="w")
        self.lbl_limite.pack(fill="x")

        secao = self._secao(painel, "Último sinal confirmado")
        self.lbl_confirmado = ctk.CTkLabel(secao, text="", height=30, anchor="w")
        self.lbl_confirmado.pack(fill="x")

        secao = self._secao(painel, "Frase em construção")
        self.frm_sequencia = ctk.CTkFrame(secao, fg_color="transparent")
        self.frm_sequencia.pack(fill="x", pady=(4, 0))
        # prévia em português (tabela de frases); só aparece quando algum trecho foi convertido
        self.lbl_previa = ctk.CTkLabel(secao, text="", font=self._f_texto, text_color=TEXTO_SECUNDARIO,
                                       wraplength=430, justify="left", anchor="w")

        secao = self._secao(painel, "Frase final")
        self.lbl_final = ctk.CTkLabel(secao, text="", wraplength=430, justify="left", anchor="w")
        self.lbl_final.pack(fill="x")
        # glosa (sinais feitos) embaixo do português, quando forem diferentes
        self.lbl_glosa_final = ctk.CTkLabel(secao, text="", font=self._f_pequeno, text_color=TEXTO_SECUNDARIO,
                                            wraplength=430, justify="left", anchor="w")

        botoes = ctk.CTkFrame(direita, fg_color="transparent")
        botoes.pack(fill="x", pady=(12, 0))
        botoes.grid_columnconfigure((0, 1), weight=1, uniform="botoes")
        acoes = [("Finalizar frase", self._finalizar_frase), ("Reproduzir voz", self._reproduzir_voz),
                 ("Remover última palavra", self._remover_ultima), ("Limpar frase", self._limpar)]
        for i, (texto, comando) in enumerate(acoes):
            ctk.CTkButton(botoes, text=texto, command=comando, height=38, corner_radius=8, font=self._f_botao,
                          fg_color=BOTAO, hover_color=BOTAO_HOVER, text_color=TEXTO, border_width=1,
                          border_color=BORDA_BOTAO).grid(row=i // 2, column=i % 2, sticky="ew",
                                                         padx=(0, 5) if i % 2 == 0 else (5, 0), pady=4)

        teclas = ctk.CTkFrame(direita, fg_color="transparent")
        teclas.pack(fill="x", pady=(8, 0))
        for tecla, acao in (("Espaço", "finaliza"), ("Backspace", "remove a última"), ("C", "limpa")):
            ctk.CTkLabel(teclas, text=tecla, font=self._f_pequeno, fg_color=FUNDO_ETIQUETA, corner_radius=4,
                         text_color=TEXTO, height=22, padx=7).pack(side="left")
            ctk.CTkLabel(teclas, text=acao, font=self._f_pequeno, text_color=TEXTO_SECUNDARIO,
                         height=22).pack(side="left", padx=(6, 16))

        # Resposta mais rápida: fala cada palavra assim que ela é confirmada, sem
        # esperar a frase terminar (a frase inteira continua em "Reproduzir voz").
        self.var_cada_palavra = ctk.BooleanVar(value=config.FALAR_CADA_PALAVRA)
        ctk.CTkSwitch(direita, text="Falar cada palavra assim que for reconhecida", variable=self.var_cada_palavra,
                      command=self._mudou_cada_palavra, font=self._f_pequeno, text_color=TEXTO_SECUNDARIO,
                      progress_color=DESTAQUE, switch_width=34, switch_height=18).pack(anchor="w", pady=(12, 0))
        self._alternar_cada_palavra()

    def _secao(self, painel, titulo: str | None = None, primeira: bool = False) -> ctk.CTkFrame:
        if not primeira:
            ctk.CTkFrame(painel, height=1, corner_radius=0, fg_color=BORDA).pack(fill="x", padx=16)
        corpo = ctk.CTkFrame(painel, fg_color="transparent")
        corpo.pack(fill="x", padx=18, pady=(14 if primeira else 12, 12))
        if titulo:
            ctk.CTkLabel(corpo, text=titulo, font=self._f_rotulo, text_color=TEXTO_SECUNDARIO,
                         height=18, anchor="w").pack(fill="x")
        return corpo

    def _montar_status(self) -> None:
        barra = ctk.CTkFrame(self, fg_color=SUPERFICIE, corner_radius=0, height=32)
        barra.grid(row=2, column=0, sticky="ew")
        barra.pack_propagate(False)
        ctk.CTkFrame(barra, height=1, corner_radius=0, fg_color=BORDA).pack(side="top", fill="x")
        self.ind_camera, self.ind_modelo, self.ind_maos, self.ind_voz = (
            Indicador(barra, self._f_pequeno) for _ in range(4))
        for i, indicador in enumerate((self.ind_camera, self.ind_modelo, self.ind_maos, self.ind_voz)):
            indicador.pack(side="left", padx=(20 if i == 0 else 0, 22))
        self.lbl_desempenho = ctk.CTkLabel(barra, text="", font=self._f_pequeno, text_color=TEXTO_APAGADO)
        self.lbl_desempenho.pack(side="right", padx=20)

    # --- câmera -----------------------------------------------------------------------

    def _estilo_botao_camera(self) -> None:
        if self._carregando or self.estado_camera == "desligada":
            self.btn_camera.configure(
                text="Carregando..." if self._carregando else "Iniciar câmera",
                state="disabled" if self._carregando else "normal",
                font=self._f_botao_forte, fg_color=DESTAQUE, hover_color=DESTAQUE_HOVER, border_width=0,
                text_color="#ffffff", text_color_disabled="#c8d8ee")
        else:
            self.btn_camera.configure(
                text="Parar câmera" if self.estado_camera != "desligando" else "Desligando...",
                state="normal" if self.estado_camera != "desligando" else "disabled",
                font=self._f_botao, fg_color=BOTAO, hover_color=BOTAO_HOVER, border_width=1,
                border_color=BORDA_BOTAO, text_color=TEXTO, text_color_disabled=TEXTO_APAGADO)

    def _alternar_camera(self) -> None:
        if self.processador is None:
            self._iniciar_camera()
        else:
            self._parar_camera()

    def _iniciar_camera(self) -> None:
        if self.processador is not None or self._ProcessadorCamera is None:
            return
        self.erro_camera = None
        self._estabilizador = estabilizador = (
            Estabilizador(limiar=config.LIMIAR_CONFIANCA, confirmacao_adaptativa=config.CONFIRMACAO_ADAPTATIVA)
            if self.classificador else None)
        self.processador = self._ProcessadorCamera(self.classificador, self.indice_camera, estabilizador)
        self.processador.start()
        self.estado_camera = "iniciando"
        self._estilo_botao_camera()
        self._mostrar_imagem(_tela_vazia(*TEXTOS_VAZIOS["iniciando"]))

    def _parar_camera(self) -> None:
        if self.processador is not None:
            self.processador.parar()  # não bloqueia: o evento "parado" chega no ciclo
            self.estado_camera = "desligando"
            self._estilo_botao_camera()

    def _ciclo(self) -> None:
        """Roda na thread da interface a cada INTERVALO_MS. Um erro inesperado aparece
        no terminal, mas nunca congela a janela: o próximo ciclo é sempre agendado."""
        try:
            self._passo_do_ciclo()
        except Exception:
            import traceback
            traceback.print_exc()
        finally:
            self.after(INTERVALO_MS, self._ciclo)

    def _passo_do_ciclo(self) -> None:
        if self._carregando:
            self._verificar_carga()
        if not self._fila_cameras.empty():
            self._receber_cameras(self._fila_cameras.get())
        if self.processador is not None:
            for tipo, dado in self.processador.eventos():
                self._tratar_evento(tipo, dado)
        if self.processador is not None:
            quadro = self.processador.ultimo_quadro()
            if quadro is not None:
                self._mostrar_quadro(quadro)
        if config.FINALIZAR_POR_PAUSA:
            self.sentenca.verificar_pausa(time.perf_counter())
        if self.voz.erro and self.voz.erro != self._erro_voz_mostrado:
            self._erro_voz_mostrado = self.voz.erro
            self._mostrar_aviso(f"Voz: {self.voz.erro}")
        self._atualizar_textos()
        self._atualizar_indicadores()

    def _tratar_evento(self, tipo: str, dado) -> None:
        if tipo == "status":
            if dado == "ok":
                self.estado_camera = "ligada"
                if self._verificar_ao_ligar:  # primeira vez neste computador
                    self._verificar_ao_ligar = False
                    self._iniciar_verificacao()
            elif self.estado_camera == "iniciando":
                self._mostrar_imagem(_tela_vazia("Iniciando a câmera", dado))
        elif tipo == "palavra":
            palavra, _confianca, momento = dado
            if self.sentenca.adicionar(palavra, momento) and self.var_cada_palavra.get():
                self.voz.falar(self.sentenca.texto_para_fala(config.rotulo_exibicao(palavra)))
        elif tipo == "erro":
            self.erro_camera = dado
        elif tipo == "aviso":
            self._mostrar_aviso(dado, duracao_ms=12000)
        elif tipo == "parado":
            self.processador = None
            self.estado_camera = "desligada"
            self._ultimo_resultado = None
            self._estilo_botao_camera()
            self.sentenca.atualizar_deteccao(None)
            if self.erro_camera:
                self._mostrar_imagem(_tela_vazia("Não foi possível usar a câmera", self.erro_camera))
            else:
                self._mostrar_imagem(_tela_vazia(*TEXTOS_VAZIOS["desligada"]))
            self.lbl_desempenho.configure(text="")
            self._verificacao = None
            if self._religar_camera:   # trocou de câmera com ela ligada: liga a nova
                self._religar_camera = False
                self._iniciar_camera()

    def _mostrar_quadro(self, quadro) -> None:
        rgb = cv2.cvtColor(quadro.imagem, cv2.COLOR_BGR2RGB)
        imagem = Image.fromarray(rgb)
        if self.apresentacao is not None and self.apresentacao.aberta:
            self.apresentacao.mostrar_quadro(imagem)
        if self._verificacao is not None:
            self._amostrar_verificacao(quadro)
        imagem.thumbnail(TAMANHO_VIDEO)
        imagem = _arredondar(imagem, RAIO)
        self._imagem_tk = ctk.CTkImage(light_image=imagem, dark_image=imagem, size=imagem.size)
        self.video.configure(image=self._imagem_tk)
        self.sentenca.atualizar_deteccao(quadro.estado.sinal, quadro.estado.confianca)
        self._ultimo_resultado = quadro.resultado
        extra = f"   modelo {quadro.estado.tempo_inferencia_ms:.0f} ms" if self.classificador else ""
        leve = "   modo leve" if getattr(quadro, "leve", False) else ""
        self.lbl_desempenho.configure(text=f"{quadro.fps:.0f} fps{extra}{leve}")
        if quadro.estado.aviso:
            self._mostrar_aviso(quadro.estado.aviso)

    def _mostrar_imagem(self, imagem: ctk.CTkImage) -> None:
        self._imagem_tk = self._imagem_vazia = imagem
        self.video.configure(image=imagem)
        if self.apresentacao is not None and self.apresentacao.aberta:
            self.apresentacao.mostrar_vazia(imagem)

    # --- escolha da câmera ----------------------------------------------------------------

    PROCURAR = "Procurar câmeras"

    @staticmethod
    def _nome_camera(indice: int) -> str:
        return f"Câmera {indice + 1}"   # para as pessoas, a primeira é a "Câmera 1" (índice 0)

    def _receber_cameras(self, cameras: list[int]) -> None:
        self.cameras = cameras
        if cameras and self.indice_camera not in cameras and self.processador is None:
            self.indice_camera = cameras[0]   # a escolhida antes não está conectada agora
        if cameras:
            nomes = [self._nome_camera(i) for i in cameras]
        else:   # nenhuma respondeu na procura: deixa escolher na mão (às vezes ela funciona ao ligar)
            nomes = [self._nome_camera(i) for i in range(config.MAX_CAMERAS_PROCURAR)]
            self._mostrar_aviso("Nenhuma câmera respondeu na procura. Tente Iniciar câmera ou escolha "
                                "outra na lista.", duracao_ms=10000)
        self.menu_camera.configure(values=nomes + [self.PROCURAR])
        self.menu_camera.set(self._nome_camera(self.indice_camera))

    def _escolher_camera(self, escolha: str) -> None:
        if escolha == self.PROCURAR:
            self.menu_camera.set(self._nome_camera(self.indice_camera))
            if self.processador is not None:
                self._mostrar_aviso("Pare a câmera para procurar outras câmeras.")
                return
            self._mostrar_aviso("Procurando câmeras...")
            threading.Thread(target=self._procurar_cameras, name="cameras", daemon=True).start()
            return
        if not escolha.startswith("Câmera "):
            return
        indice = int(escolha.split()[-1]) - 1
        if indice == self.indice_camera:
            return
        self.indice_camera = indice
        self._aplicar_preferencia("indice_camera", indice)   # lembra da escolha neste computador
        if self.processador is not None:   # ligada: desliga e religa na nova
            self._religar_camera = True
            self._parar_camera()
            self._mostrar_aviso(f"Trocando para a {escolha}...")

    # --- verificação do ambiente ---------------------------------------------------------

    def _iniciar_verificacao(self) -> None:
        if self.estado_camera != "ligada":
            self._mostrar_aviso("Ligue a câmera para verificar o ambiente.")
            return
        self._verificacao = VerificacaoAmbiente()
        self._fim_verificacao = time.perf_counter() + DURACAO_VERIFICACAO_S
        self._mostrar_aviso("Verificando o ambiente: fique na posição de fazer os sinais, com as mãos "
                            "na frente do peito.", duracao_ms=int(DURACAO_VERIFICACAO_S * 1000) + 500)

    def _amostrar_verificacao(self, quadro) -> None:
        altura, largura = quadro.imagem.shape[:2]
        self._verificacao.adicionar(brilho_medio(quadro.imagem), quadro.fps,
                                    largura_ombros(quadro.resultado.pose, largura, altura),
                                    quadro.resultado.tem_maos)
        if time.perf_counter() >= self._fim_verificacao:
            verificacao, self._verificacao = self._verificacao, None
            preferencias.definir("verificacao_feita", True)
            self._limpar_aviso()
            JanelaVerificacao(self, verificacao)

    # --- janelas: configurações, histórico, apresentação ----------------------------------

    def _abrir_configuracoes(self) -> None:
        if self._janela_config is not None and self._janela_config.janela.winfo_exists():
            self._janela_config.janela.focus()
            return
        self._janela_config = JanelaConfiguracoes(self)

    def _aplicar_preferencia(self, nome: str, valor, salvar: bool = True) -> None:
        """Muda uma configuração, salva e aplica na hora no que já está rodando."""
        if salvar:
            try:
                preferencias.definir(nome, valor)
            except (ValueError, OSError) as erro:
                self._mostrar_aviso(f"Não foi possível salvar a configuração: {erro}")
                return
        if nome == "limiar_confianca":
            self.medidor.definir_limite(valor)
            if self._estabilizador is not None:
                self._estabilizador.limiar = valor
        elif nome == "confirmacao_adaptativa" and self._estabilizador is not None:
            self._estabilizador.confirmacao_adaptativa = valor
        elif nome == "modo_leve":
            pipeline = getattr(self.processador, "pipeline", None)
            if pipeline is not None:
                pipeline.modo_leve = valor
                if valor != "auto":
                    pipeline.extrator.leve = valor == "ligado"
        elif nome == "pausa_frase_s":
            self.sentenca.pausa_s = valor
        elif nome == "taxa_fala":
            self.voz.reiniciar_motor()
        elif nome == "falar_cada_palavra":
            self.var_cada_palavra.set(valor)
            self._alternar_cada_palavra()
        elif nome == "modo_camera" and self.processador is not None:
            self._religar_camera = True   # religa a câmera no modo novo
            self._parar_camera()

    def _abrir_historico(self) -> None:
        if self._janela_historico is not None and self._janela_historico.janela.winfo_exists():
            self._janela_historico.janela.focus()
            return
        self._janela_historico = JanelaHistorico(self)

    def _copiar(self, texto: str) -> None:
        self.clipboard_clear()
        self.clipboard_append(texto)
        self._mostrar_aviso("Copiado. Cole com Ctrl+V onde quiser.")

    def _abrir_apresentacao(self) -> None:
        if self.apresentacao is not None and self.apresentacao.aberta:
            self.apresentacao.janela.focus_force()
            return
        self.apresentacao = JanelaApresentacao(self)
        if self.processador is None and self._imagem_vazia is not None:
            self.apresentacao.mostrar_vazia(self._imagem_vazia)

    # --- textos e indicadores ----------------------------------------------------------

    def _definir(self, rotulo: ctk.CTkLabel, texto: str, cor=TEXTO, fonte=None) -> None:
        """Muda o rótulo só quando algo mudou (roda a cada ciclo)."""
        estado = (texto, cor, id(fonte))
        if self._textos.get(id(rotulo)) != estado:
            self._textos[id(rotulo)] = estado
            rotulo.configure(text=texto, text_color=cor, **({"font": fonte} if fonte else {}))

    def _atualizar_indicadores(self) -> None:
        if self.estado_camera == "ligada":
            camera = ("Câmera ligada", STATUS_OK)
        elif self.estado_camera in ("iniciando", "desligando"):
            camera = ("Câmera iniciando" if self.estado_camera == "iniciando" else "Câmera desligando",
                      STATUS_ATENCAO)
        elif self.erro_camera:
            camera = ("Câmera com erro", STATUS_ERRO)
        else:
            camera = ("Câmera desligada", STATUS_NEUTRO)
        self.ind_camera.definir(*camera)

        if self._carregando:
            self.ind_modelo.definir("Modelo carregando", STATUS_NEUTRO)
        elif self.classificador is not None:
            classes = [c for c in self.classificador.classes if c != config.CLASSE_NADA]
            letras = sum(config.eh_letra(c) for c in classes)
            texto = f"Modelo com {len(classes) - letras} sinais" + (f" e {letras} letras" if letras else "")
            self.ind_modelo.definir(texto + (", com avisos" if self.aviso_modelo else ""),
                                    STATUS_ATENCAO if self.aviso_modelo else STATUS_OK)
        else:
            self.ind_modelo.definir("Sem modelo treinado", STATUS_ERRO)

        if self.estado_camera != "ligada" or self._ultimo_resultado is None:
            self.ind_maos.definir("Mãos: sem imagem", STATUS_NEUTRO)
        elif self._ultimo_resultado.tem_maos:
            self.ind_maos.definir(descrever_maos(self._ultimo_resultado), STATUS_OK)
        else:
            self.ind_maos.definir("Nenhuma mão", STATUS_ATENCAO)

        if self.voz.disponivel:
            self.ind_voz.definir("Voz falando" if self.voz.falando else f"Voz: {self.voz.nome_voz}", STATUS_OK)
        elif self.voz.erro:
            self.ind_voz.definir("Voz indisponível", STATUS_ERRO)
        else:
            self.ind_voz.definir("Voz preparando", STATUS_NEUTRO)

    def _atualizar_textos(self) -> None:
        s = self.sentenca
        limite = config.LIMIAR_CONFIANCA
        if s.sinal_atual:
            aceito = s.confianca_atual >= limite
            self._definir(self.lbl_sinal, config.rotulo_exibicao(s.sinal_atual), TEXTO, self._f_sinal)
            self._definir(self.lbl_conf, f"{s.confianca_atual:.0%}")
            self._definir(self.lbl_limite, f"Acima do limite de {limite:.0%}: pode ser confirmado" if aceito
                          else f"Abaixo do limite de {limite:.0%}: não será confirmado", TEXTO_SECUNDARIO)
            self.medidor.definir(s.confianca_atual, aceito)
        else:
            self._definir(self.lbl_sinal, "Nenhum sinal", TEXTO_APAGADO, self._f_vazio)
            self._definir(self.lbl_conf, "")
            self._definir(self.lbl_limite, f"Um sinal é confirmado com {limite:.0%} de confiança ou mais",
                          TEXTO_SECUNDARIO)
            self.medidor.definir(0.0, True)

        if s.ultimo_confirmado:
            self._definir(self.lbl_confirmado, config.rotulo_exibicao(s.ultimo_confirmado), TEXTO, self._f_valor)
        else:
            self._definir(self.lbl_confirmado, "Nenhum ainda", TEXTO_APAGADO, self._f_texto)

        self._mostrar_sequencia(tuple(s.sequencia))
        traducao = s.traducao_atual
        self._mostrar_opcional(self.lbl_previa, f"Em português: {traducao.texto}" if traducao.convertida else "",
                               depois_de=self.frm_sequencia)

        if s.frase_final:
            self._definir(self.lbl_final, s.frase_final, TEXTO, self._f_frase)
        else:
            self._definir(self.lbl_final, "A frase aparece aqui ao finalizar (Espaço ou pausa).",
                          TEXTO_APAGADO, self._f_texto)
        glosa = s.glosa_final if config.MOSTRAR_GLOSA and s.glosa_final != s.frase_final else ""
        self._mostrar_opcional(self.lbl_glosa_final, f"Sinais: {glosa}" if glosa else "", depois_de=self.lbl_final)
        if self.apresentacao is not None and self.apresentacao.aberta:
            if s.palavras:   # frase em construção ao vivo; senão, a última frase finalizada
                self.apresentacao.atualizar(traducao.texto, traducao.glosa if config.MOSTRAR_GLOSA else "")
            else:
                self.apresentacao.atualizar(s.frase_final, s.glosa_final if config.MOSTRAR_GLOSA else "")

    def _mostrar_sequencia(self, palavras: tuple[str, ...]) -> None:
        """Cada palavra confirmada vira uma etiqueta; a mais recente fica destacada."""
        if palavras == self._sequencia_mostrada:
            return
        self._sequencia_mostrada = palavras
        for filho in self.frm_sequencia.winfo_children():
            filho.destroy()
        if not palavras:
            ctk.CTkLabel(self.frm_sequencia, text="Os sinais confirmados aparecem aqui.", font=self._f_texto,
                         text_color=TEXTO_APAGADO, height=28, anchor="w").pack(anchor="w")
            return
        largura_max = 430
        linha, usado = None, 0
        for i, palavra in enumerate(palavras):
            largura = self._f_palavra.measure(palavra) + 20 + 6
            if linha is None or usado + largura > largura_max:
                linha = ctk.CTkFrame(self.frm_sequencia, fg_color="transparent")
                linha.pack(anchor="w", pady=(0, 6))
                usado = 0
            nova = i == len(palavras) - 1
            ctk.CTkLabel(linha, text=palavra, font=self._f_palavra, text_color=TEXTO, height=28, corner_radius=6,
                         fg_color=FUNDO_ETIQUETA_NOVA if nova else FUNDO_ETIQUETA, padx=10).pack(
                side="left", padx=(0, 6))
            usado += largura

    @staticmethod
    def _mostrar_opcional(rotulo: ctk.CTkLabel, texto: str, depois_de) -> None:
        """Mostra o rótulo com `texto` logo abaixo de `depois_de`, ou o esconde se vazio."""
        if texto:
            if rotulo.cget("text") != texto:
                rotulo.configure(text=texto)
            if not rotulo.winfo_manager():
                rotulo.pack(fill="x", pady=(2, 0), after=depois_de)
        elif rotulo.winfo_manager():
            rotulo.pack_forget()

    def _mostrar_aviso(self, texto: str, duracao_ms: int = 4000) -> None:
        """Mostra um aviso ao lado do botão da câmera. Chamado a cada frame pelo mesmo
        aviso (ex.: ombros fora da imagem), só renova o prazo: nunca acumula temporizadores."""
        if self._aviso_agendado is not None:
            self.after_cancel(self._aviso_agendado)
        if texto != self._aviso_atual:
            self.lbl_aviso.configure(text=texto)
            self._aviso_atual = texto
            if not self._aviso_ponto.winfo_manager():
                self._aviso_ponto.pack(side="left", anchor="n", padx=(16, 0), pady=(15, 0), before=self.lbl_aviso)
            self.lbl_aviso.pack_configure(padx=(8, 0))
        self._aviso_agendado = self.after(duracao_ms, self._limpar_aviso)

    def _limpar_aviso(self) -> None:
        self._aviso_agendado = None
        self._aviso_atual = ""
        self.lbl_aviso.configure(text="")
        if self._aviso_ponto.winfo_manager():
            self._aviso_ponto.pack_forget()

    # --- janela Sobre ---------------------------------------------------------------------

    def _abrir_sobre(self) -> None:
        if self._janela_sobre is not None and self._janela_sobre.winfo_exists():
            self._janela_sobre.focus()
            return
        janela = ctk.CTkToplevel(self)
        self._janela_sobre = janela
        janela.title("Sobre o Librahin")
        janela.configure(fg_color=SUPERFICIE)
        janela.resizable(False, False)
        janela.transient(self)
        self._definir_icone(janela)

        corpo = ctk.CTkFrame(janela, fg_color="transparent")
        corpo.pack(padx=28, pady=(24, 20), fill="both")
        cabecalho = ctk.CTkFrame(corpo, fg_color="transparent")
        cabecalho.pack(fill="x")
        self._img_icone_sobre = ctk.CTkImage(light_image=self._pil_icone, dark_image=self._pil_icone,
                                             size=(48, 48))
        ctk.CTkLabel(cabecalho, image=self._img_icone_sobre, text="").pack(side="left", padx=(0, 14))
        nome = ctk.CTkFrame(cabecalho, fg_color="transparent")
        nome.pack(side="left")
        ctk.CTkLabel(nome, text="Librahin", font=_fonte(20, forte=True), text_color=TEXTO,
                     height=26, anchor="w").pack(anchor="w")
        ctk.CTkLabel(nome, text=f"Versão {libras.__version__}", font=self._f_pequeno,
                     text_color=TEXTO_SECUNDARIO, height=16, anchor="w").pack(anchor="w")
        ctk.CTkLabel(corpo, text=config.TITULO_TRABALHO, font=self._f_texto, text_color=TEXTO,
                     wraplength=380, justify="left", anchor="w").pack(fill="x", pady=(18, 14))
        ctk.CTkFrame(corpo, height=1, corner_radius=0, fg_color=BORDA).pack(fill="x", pady=(0, 14))
        for titulo, linhas in (("Equipe", config.EQUIPE), ("Professor orientador", (config.ORIENTADOR,)),
                               ("Curso", (config.CURSO,))):
            ctk.CTkLabel(corpo, text=titulo, font=self._f_pequeno, text_color=TEXTO_SECUNDARIO,
                         height=16, anchor="w").pack(fill="x")
            for linha in linhas:
                ctk.CTkLabel(corpo, text=linha, font=self._f_texto, text_color=TEXTO, height=22,
                             wraplength=380, justify="left", anchor="w").pack(fill="x")
            ctk.CTkFrame(corpo, height=12, fg_color="transparent").pack()
        ctk.CTkButton(corpo, text="Fechar", width=96, height=34, corner_radius=8, font=self._f_botao_forte,
                      fg_color=DESTAQUE, hover_color=DESTAQUE_HOVER, text_color="#ffffff",
                      command=janela.destroy).pack(anchor="e", pady=(6, 0))
        janela.bind("<Escape>", lambda _e: janela.destroy())
        janela.bind("<Return>", lambda _e: janela.destroy())

        # Centraliza sobre a janela principal (coordenadas reais da tela)
        janela.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() - janela.winfo_reqwidth()) // 2
        y = self.winfo_rooty() + (self.winfo_height() - janela.winfo_reqheight()) // 3
        janela.wm_geometry(f"+{max(0, x)}+{max(0, y)}")
        janela.after(60, lambda: self._focar_janela(janela))

    @staticmethod
    def _focar_janela(janela) -> None:
        try:
            janela.lift()
            janela.focus_force()
            janela.grab_set()  # modal: só depois de visível
        except tkinter.TclError:
            pass

    # --- frase e voz -----------------------------------------------------------------------

    def _ao_finalizar(self, frase: str) -> None:
        """Chamado pelo GerenciadorSentenca quando uma frase é encerrada. Se cada palavra
        já foi falada na hora, a frase só é falada de novo quando ficou diferente da
        sequência de sinais (a tabela de frases ou a soletração mudaram o texto)."""
        glosa = self.sentenca.glosa_final
        self.historico.append((time.strftime("%H:%M:%S"), frase, glosa))
        del self.historico[:-50]
        if self._janela_historico is not None and self._janela_historico.janela.winfo_exists():
            self._janela_historico.atualizar()
        if not config.FALAR_AO_FINALIZAR:
            return
        if not self.var_cada_palavra.get() or _som(frase) != _som(glosa):
            self._falar(frase)

    def _alternar_cada_palavra(self) -> None:
        # Falando palavra por palavra, uma nova palavra espera a anterior terminar (em vez de ser ignorada)
        self.voz.politica = "enfileirar" if self.var_cada_palavra.get() else config.POLITICA_VOZ

    def _mudou_cada_palavra(self) -> None:
        self._aplicar_preferencia("falar_cada_palavra", self.var_cada_palavra.get())

    def _falar(self, texto: str) -> None:
        if not self.voz.disponivel:
            self._mostrar_aviso(f"Voz indisponível: {self.voz.erro or 'ainda preparando, tente de novo'}")
        elif not self.voz.falar(self.sentenca.texto_para_fala(texto)):
            self._mostrar_aviso("Aguarde: a voz ainda está falando a frase anterior.")

    def _finalizar_frase(self) -> None:
        if self.sentenca.finalizar() is None:
            self._mostrar_aviso("Nenhuma palavra na sequência para finalizar.")

    def _reproduzir_voz(self) -> None:
        texto = self.sentenca.frase_atual or self.sentenca.frase_final
        if texto:
            self._falar(texto)
        else:
            self._mostrar_aviso("Nada para falar: faça alguns sinais primeiro.")

    def _remover_ultima(self) -> None:
        if self.sentenca.remover_ultima() is None:
            self._mostrar_aviso("A sequência já está vazia.")

    def _limpar(self) -> None:
        self.sentenca.limpar()
        if self.processador is not None:
            self.processador.pedir_limpeza()

    def _fechar(self) -> None:
        if self.processador is not None:
            self.processador.parar()
            self.processador.join(timeout=2.0)
        self.voz.encerrar()
        self.destroy()


def iniciar(indice_camera: int | None = None, tema: str = "dark") -> None:
    """`indice_camera` None = a câmera escolhida na janela (preferências) ou a do config."""
    if WINDOWS:
        try:  # agrupa a janela com o ícone do Librahin na barra de tarefas (e não com o do Python)
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Librahin.Aplicacao")
        except Exception:
            pass
    for aviso in preferencias.carregar():   # configurações salvas neste computador
        print(f"[AVISO] preferências: {aviso}")
    ctk.set_appearance_mode(tema)
    ctk.set_default_color_theme("blue")
    AplicacaoLibras(indice_camera).mainloop()
