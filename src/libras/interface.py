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
from libras import config
from libras.classificador import ErroClassificador, carregar_classificador
from libras.desenho import descrever_maos, fonte_com_acentos, icone_mao
from libras.estabilizador import Estabilizador
from libras.frase import GerenciadorSentenca
from libras.traducao import carregar_tabela_padrao
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


# --- janela --------------------------------------------------------------------------------

class AplicacaoLibras(ctk.CTk):
    def __init__(self, indice_camera: int = config.INDICE_CAMERA) -> None:
        super().__init__()
        self.title("Vis-oLibras")
        self._definir_icone(self)
        self._ajustar_tamanho()
        self.indice_camera = indice_camera

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

        self.tabela = carregar_tabela_padrao()  # frases.txt (None se desligada no config)
        self.sentenca = GerenciadorSentenca(ao_finalizar=self._ao_finalizar, tabela=self.tabela)
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
            self._fila_carga.put(("pronto", (ProcessadorCamera, classificador, erro, aviso)))
        except Exception as e:  # nunca deixar a janela presa em "Carregando"
            self._fila_carga.put(("falha", str(e)))

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
        treinadas = [c for c in config.CLASSES if c in self.classificador.classes]
        if len(treinadas) < len(config.CLASSES):
            return (f"O modelo ainda não conhece todos os sinais ({len(treinadas)} de {len(config.CLASSES)}). "
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
        ctk.CTkLabel(topo, text="Vis-oLibras", font=self._f_marca, text_color=TEXTO).pack(side="left")
        ctk.CTkLabel(topo, text="Libras para texto e voz", font=self._f_rotulo,
                     text_color=TEXTO_SECUNDARIO).pack(side="left", padx=(12, 0), pady=(2, 0))
        ctk.CTkButton(topo, text="Sobre", width=72, height=30, corner_radius=6, font=self._f_botao,
                      fg_color="transparent", hover_color=BOTAO_HOVER, text_color=TEXTO_SECUNDARIO,
                      command=self._abrir_sobre).pack(side="right", padx=14)

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
        estabilizador = Estabilizador() if self.classificador else None
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
        """Roda na thread da interface a cada INTERVALO_MS."""
        if self._carregando:
            self._verificar_carga()
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
        self.after(INTERVALO_MS, self._ciclo)

    def _tratar_evento(self, tipo: str, dado) -> None:
        if tipo == "status":
            if dado == "ok":
                self.estado_camera = "ligada"
            elif self.estado_camera == "iniciando":
                self._mostrar_imagem(_tela_vazia("Iniciando a câmera", dado))
        elif tipo == "palavra":
            palavra, _confianca, momento = dado
            if self.sentenca.adicionar(palavra, momento) and config.FALAR_CADA_PALAVRA:
                self.voz.falar(self.sentenca.texto_para_fala(config.rotulo_exibicao(palavra)))
        elif tipo == "erro":
            self.erro_camera = dado
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

    def _mostrar_quadro(self, quadro) -> None:
        rgb = cv2.cvtColor(quadro.imagem, cv2.COLOR_BGR2RGB)
        imagem = Image.fromarray(rgb)
        imagem.thumbnail(TAMANHO_VIDEO)
        imagem = _arredondar(imagem, RAIO)
        self._imagem_tk = ctk.CTkImage(light_image=imagem, dark_image=imagem, size=imagem.size)
        self.video.configure(image=self._imagem_tk)
        self.sentenca.atualizar_deteccao(quadro.estado.sinal, quadro.estado.confianca)
        self._ultimo_resultado = quadro.resultado
        extra = f"   modelo {quadro.estado.tempo_inferencia_ms:.0f} ms" if self.classificador else ""
        self.lbl_desempenho.configure(text=f"{quadro.fps:.0f} fps{extra}")
        if quadro.estado.aviso:
            self._mostrar_aviso(quadro.estado.aviso)

    def _mostrar_imagem(self, imagem: ctk.CTkImage) -> None:
        self._imagem_tk = imagem
        self.video.configure(image=imagem)

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
            sinais = len([c for c in self.classificador.classes if c != config.CLASSE_NADA])
            self.ind_modelo.definir(f"Modelo com {sinais} sinais" + (", com avisos" if self.aviso_modelo else ""),
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
        janela.title("Sobre o Vis-oLibras")
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
        ctk.CTkLabel(nome, text="Vis-oLibras", font=_fonte(20, forte=True), text_color=TEXTO,
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
        """Chamado pelo GerenciadorSentenca quando uma frase é encerrada."""
        if config.FALAR_AO_FINALIZAR:
            self._falar(frase)

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


def iniciar(indice_camera: int = config.INDICE_CAMERA, tema: str = "dark") -> None:
    if WINDOWS:
        try:  # agrupa a janela com o ícone do Vis-oLibras na barra de tarefas (e não com o do Python)
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("VisoLibras.Aplicacao")
        except Exception:
            pass
    ctk.set_appearance_mode(tema)
    ctk.set_default_color_theme("blue")
    AplicacaoLibras(indice_camera).mainloop()
