"""Interface gráfica para demonstração (CustomTkinter).

Organização das threads:
- thread da interface (Tk): desenha a janela e, a cada ~30 ms (`after`), lê o
  último quadro e os eventos da câmera. Nunca espera pela câmera.
- thread da câmera (captura.ProcessadorCamera): câmera -> MediaPipe ->
  reconhecimento. Nunca mexe em widgets.
- thread da voz (voz.Voz): fala sem bloquear nenhuma das outras.

A frase (frase.GerenciadorSentenca) vive na thread da interface: as palavras
chegam como eventos e os botões mexem nela diretamente, sem disputa entre threads.
"""

from __future__ import annotations

import time
import warnings
from tkinter import messagebox

import customtkinter as ctk
import cv2
from PIL import Image, ImageDraw

from libras import config
from libras.captura import ProcessadorCamera
from libras.classificador import Classificador, ErroClassificador, carregar_classificador
from libras.desenho import descrever_maos, fonte_com_acentos
from libras.estabilizador import Estabilizador
from libras.frase import GerenciadorSentenca
from libras.voz import Voz

INTERVALO_MS = 30
ATALHOS = "Atalhos: Espaço finaliza · Backspace remove · C limpa"
MAOS_CURTO = {"Ambas as mãos": "ambas", "Mão direita": "direita", "Mão esquerda": "esquerda"}
TAMANHO_VIDEO = (640, 480)

# Cores (paleta de status validada: ok / atenção / erro, sempre com texto junto)
COR_OK = "#0ca30c"
COR_ATENCAO = "#fab219"
COR_ERRO = "#d03b3b"
COR_NEUTRA = "#8a8a85"
COR_DESTAQUE = "#3987e5"
COR_FRASE = "#f0c75e"
COR_CARTAO = ("#ececea", "#242423")
COR_TEXTO_SECUNDARIO = ("#52514e", "#c3c2b7")


def _imagem_parada(texto: str) -> Image.Image:
    imagem = Image.new("RGB", TAMANHO_VIDEO, (26, 26, 25))
    desenho = ImageDraw.Draw(imagem)
    fonte = fonte_com_acentos(24)
    largura = desenho.textlength(texto, font=fonte) if fonte else len(texto) * 10
    desenho.text(((TAMANHO_VIDEO[0] - largura) / 2, TAMANHO_VIDEO[1] / 2 - 14), texto,
                 fill=(195, 194, 183), font=fonte)
    return imagem


class Indicador(ctk.CTkFrame):
    """"● Câmera: OK" - a cor nunca aparece sozinha, sempre com o texto."""

    def __init__(self, master, rotulo: str) -> None:
        super().__init__(master, fg_color=COR_CARTAO, corner_radius=8)
        self.rotulo = rotulo
        self._ponto = ctk.CTkLabel(self, text="●", font=ctk.CTkFont(size=16), width=16)
        self._ponto.pack(side="left", padx=(10, 4), pady=6)
        self._texto = ctk.CTkLabel(self, text=f"{rotulo}: —", font=ctk.CTkFont(size=13))
        self._texto.pack(side="left", padx=(0, 12), pady=6)
        self.definir("—", COR_NEUTRA)

    def definir(self, valor: str, cor: str) -> None:
        self._ponto.configure(text_color=cor)
        self._texto.configure(text=f"{self.rotulo}: {valor}")


class Cartao(ctk.CTkFrame):
    """Bloco com título pequeno e conteúdo."""

    def __init__(self, master, titulo: str) -> None:
        super().__init__(master, fg_color=COR_CARTAO, corner_radius=12)
        ctk.CTkLabel(self, text=titulo.upper(), font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=COR_TEXTO_SECUNDARIO).pack(anchor="w", padx=16, pady=(12, 0))


class AplicacaoLibras(ctk.CTk):
    def __init__(self, indice_camera: int = config.INDICE_CAMERA) -> None:
        super().__init__()
        self.title("Vis-oLibras — Libras para texto e voz")
        self.geometry("1220x760")
        self.minsize(1100, 700)
        self.indice_camera = indice_camera
        self.processador: ProcessadorCamera | None = None
        self.erro_camera: str | None = None
        self._imagem_tk = None

        self.classificador = self._carregar_modelo()
        self.sentenca = GerenciadorSentenca(ao_finalizar=self._ao_finalizar)
        # Sem callback: a thread da voz não pode mexer no Tkinter. Os erros dela
        # são lidos em self.voz.erro, na thread da interface (_ciclo).
        self.voz = Voz()
        self._erro_voz_mostrado = self.voz.erro
        self._aviso_agendado = None
        self._aviso_atual = ""

        self._montar_tela()
        self._mostrar_imagem(_imagem_parada("Câmera parada — clique em Iniciar câmera"))
        self._atualizar_indicadores(None)
        self.protocol("WM_DELETE_WINDOW", self._fechar)
        self.bind("<space>", lambda _e: self._finalizar_frase())
        self.bind("<BackSpace>", lambda _e: self._remover_ultima())
        self.bind("<KeyPress-c>", lambda _e: self._limpar())
        self.after(INTERVALO_MS, self._ciclo)

    # --- inicialização ------------------------------------------------------------

    def _carregar_modelo(self) -> Classificador | None:
        self.erro_modelo = None
        try:
            with warnings.catch_warnings(record=True) as avisos:
                warnings.simplefilter("always")
                classificador = carregar_classificador()
            self.aviso_modelo = str(avisos[0].message) if avisos else None
            return classificador
        except ErroClassificador as erro:
            self.erro_modelo = str(erro)
            return None

    def _montar_tela(self) -> None:
        self.grid_columnconfigure(0, weight=3)
        self.grid_columnconfigure(1, weight=2)
        self.grid_rowconfigure(1, weight=1)

        cabecalho = ctk.CTkFrame(self, fg_color="transparent")
        cabecalho.grid(row=0, column=0, columnspan=2, sticky="ew", padx=20, pady=(16, 4))
        ctk.CTkLabel(cabecalho, text="Vis-oLibras", font=ctk.CTkFont(size=26, weight="bold")).pack(side="left")
        ctk.CTkLabel(cabecalho, text="  Tradução de Libras para texto e voz com visão computacional",
                     font=ctk.CTkFont(size=14), text_color=COR_TEXTO_SECUNDARIO).pack(side="left", pady=(6, 0))

        # Coluna da câmera
        esquerda = ctk.CTkFrame(self, fg_color="transparent")
        esquerda.grid(row=1, column=0, sticky="nsew", padx=(20, 10), pady=10)
        # Área de tamanho fixo: a janela não "pula" se a câmera tiver outra proporção
        area_video = ctk.CTkFrame(esquerda, width=TAMANHO_VIDEO[0], height=TAMANHO_VIDEO[1],
                                  fg_color=COR_CARTAO, corner_radius=12)
        area_video.pack(anchor="n")
        area_video.pack_propagate(False)
        self.video = ctk.CTkLabel(area_video, text="")
        self.video.pack(expand=True)
        indicadores = ctk.CTkFrame(esquerda, fg_color="transparent")
        indicadores.pack(anchor="w", pady=(12, 0))
        self.ind_camera = Indicador(indicadores, "Câmera")
        self.ind_modelo = Indicador(indicadores, "Modelo")
        self.ind_maos = Indicador(indicadores, "Mãos")
        self.ind_voz = Indicador(indicadores, "Voz")
        for indicador in (self.ind_camera, self.ind_modelo, self.ind_maos, self.ind_voz):
            indicador.pack(side="left", padx=(0, 8))
        self.fps = ctk.CTkLabel(esquerda, text="", font=ctk.CTkFont(size=12), text_color=COR_TEXTO_SECUNDARIO)
        self.fps.pack(anchor="w", pady=(6, 0))

        # Coluna de resultados
        direita = ctk.CTkFrame(self, fg_color="transparent")
        direita.grid(row=1, column=1, sticky="nsew", padx=(10, 20), pady=10)

        atual = Cartao(direita, "Sinal detectado agora")
        atual.pack(fill="x", pady=(0, 10))
        self.lbl_sinal = ctk.CTkLabel(atual, text="—", font=ctk.CTkFont(size=40, weight="bold"))
        self.lbl_sinal.pack(anchor="w", padx=16)
        linha_conf = ctk.CTkFrame(atual, fg_color="transparent")
        linha_conf.pack(fill="x", padx=16, pady=(0, 14))
        self.barra_conf = ctk.CTkProgressBar(linha_conf, height=12, progress_color=COR_DESTAQUE)
        self.barra_conf.set(0)
        self.barra_conf.pack(side="left", fill="x", expand=True)
        self.lbl_conf = ctk.CTkLabel(linha_conf, text="0%", width=110, anchor="e", font=ctk.CTkFont(size=14))
        self.lbl_conf.pack(side="left")

        confirmado = Cartao(direita, "Último sinal confirmado")
        confirmado.pack(fill="x", pady=(0, 10))
        self.lbl_confirmado = ctk.CTkLabel(confirmado, text="—", font=ctk.CTkFont(size=24, weight="bold"),
                                           text_color=COR_OK)
        self.lbl_confirmado.pack(anchor="w", padx=16, pady=(0, 12))

        sequencia = Cartao(direita, "Sequência (frase em construção)")
        sequencia.pack(fill="x", pady=(0, 10))
        self.lbl_sequencia = ctk.CTkLabel(sequencia, text="—", font=ctk.CTkFont(size=22),
                                          wraplength=420, justify="left", anchor="w")
        self.lbl_sequencia.pack(fill="x", padx=16, pady=(0, 12))

        final = Cartao(direita, "Frase final")
        final.pack(fill="x", pady=(0, 12))
        self.lbl_final = ctk.CTkLabel(final, text="—", font=ctk.CTkFont(size=24, weight="bold"),
                                      text_color=COR_FRASE, wraplength=420, justify="left", anchor="w")
        self.lbl_final.pack(fill="x", padx=16, pady=(0, 12))

        botoes = ctk.CTkFrame(direita, fg_color="transparent")
        botoes.pack(fill="x")
        botoes.grid_columnconfigure((0, 1), weight=1)
        fonte = ctk.CTkFont(size=14, weight="bold")
        self.btn_iniciar = ctk.CTkButton(botoes, text="▶  Iniciar câmera", height=40, font=fonte,
                                         fg_color="#1f7a1f", hover_color="#176117", command=self._iniciar_camera)
        self.btn_parar = ctk.CTkButton(botoes, text="■  Parar câmera", height=40, font=fonte,
                                       fg_color="#9e2b2b", hover_color="#7f2222", command=self._parar_camera,
                                       state="disabled")
        acoes = [
            ("✓  Finalizar frase", self._finalizar_frase),
            ("♪  Reproduzir voz", self._reproduzir_voz),
            ("⌫  Remover última palavra", self._remover_ultima),
            ("✕  Limpar frase", self._limpar),
        ]
        self.btn_iniciar.grid(row=0, column=0, sticky="ew", padx=(0, 5), pady=4)
        self.btn_parar.grid(row=0, column=1, sticky="ew", padx=(5, 0), pady=4)
        for i, (texto, comando) in enumerate(acoes):
            ctk.CTkButton(botoes, text=texto, height=40, font=fonte, command=comando).grid(
                row=1 + i // 2, column=i % 2, sticky="ew", padx=(0, 5) if i % 2 == 0 else (5, 0), pady=4)

        self.lbl_aviso = ctk.CTkLabel(direita, text=ATALHOS,
                                      font=ctk.CTkFont(size=12), text_color=COR_TEXTO_SECUNDARIO,
                                      wraplength=440, justify="left")
        self.lbl_aviso.pack(anchor="w", pady=(10, 0))

    # --- câmera -------------------------------------------------------------------

    def _iniciar_camera(self) -> None:
        if self.processador is not None:
            return
        self.erro_camera = None
        estabilizador = Estabilizador() if self.classificador else None
        self.processador = ProcessadorCamera(self.classificador, self.indice_camera, estabilizador)
        self.processador.start()
        self.btn_iniciar.configure(state="disabled")
        self.btn_parar.configure(state="normal")
        self.ind_camera.definir("iniciando...", COR_ATENCAO)
        self._mostrar_imagem(_imagem_parada("Iniciando a câmera..."))

    def _parar_camera(self) -> None:
        if self.processador is not None:
            self.processador.parar()  # não bloqueia: o evento "parado" chega no ciclo
            self.btn_parar.configure(state="disabled")
            self.ind_camera.definir("parando...", COR_ATENCAO)

    def _ciclo(self) -> None:
        """Roda na thread da interface a cada INTERVALO_MS."""
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
        self.after(INTERVALO_MS, self._ciclo)

    def _tratar_evento(self, tipo: str, dado) -> None:
        if tipo == "status":
            self.ind_camera.definir("OK" if dado == "ok" else "iniciando...",
                                    COR_OK if dado == "ok" else COR_ATENCAO)
        elif tipo == "palavra":
            palavra, _confianca, momento = dado
            if self.sentenca.adicionar(palavra, momento) and config.FALAR_CADA_PALAVRA:
                self.voz.falar(self.sentenca.texto_para_fala(config.rotulo_exibicao(palavra)))
        elif tipo == "erro":
            self.erro_camera = dado
            messagebox.showerror("Câmera", dado)
        elif tipo == "parado":
            self.processador = None
            self.btn_iniciar.configure(state="normal")
            self.btn_parar.configure(state="disabled")
            self.sentenca.atualizar_deteccao(None)
            self._mostrar_imagem(_imagem_parada("Câmera parada — clique em Iniciar câmera"))
            self._atualizar_indicadores(None)
            self.fps.configure(text="")

    def _mostrar_quadro(self, quadro) -> None:
        rgb = cv2.cvtColor(quadro.imagem, cv2.COLOR_BGR2RGB)
        self._mostrar_imagem(Image.fromarray(rgb))
        self.sentenca.atualizar_deteccao(quadro.estado.sinal, quadro.estado.confianca)
        self._atualizar_indicadores(quadro)
        extra = f"   ·   modelo: {quadro.estado.tempo_inferencia_ms:.0f} ms" if self.classificador else ""
        self.fps.configure(text=f"FPS: {quadro.fps:.1f}{extra}")
        if quadro.estado.aviso:
            self._mostrar_aviso(quadro.estado.aviso)

    def _mostrar_imagem(self, imagem: Image.Image) -> None:
        imagem.thumbnail(TAMANHO_VIDEO)
        self._imagem_tk = ctk.CTkImage(light_image=imagem, dark_image=imagem, size=imagem.size)
        self.video.configure(image=self._imagem_tk)

    # --- textos e indicadores ------------------------------------------------------

    def _atualizar_indicadores(self, quadro) -> None:
        if self.erro_camera:
            self.ind_camera.definir("erro", COR_ERRO)
        elif self.processador is None:
            self.ind_camera.definir("parada", COR_NEUTRA)
        if self.classificador:
            self.ind_modelo.definir("carregado", COR_ATENCAO if self.aviso_modelo else COR_OK)
        else:
            self.ind_modelo.definir("não encontrado", COR_ERRO)
        if quadro is None:
            self.ind_maos.definir("—", COR_NEUTRA)
        elif quadro.resultado.tem_maos:
            self.ind_maos.definir(MAOS_CURTO.get(descrever_maos(quadro.resultado), "detectadas"), COR_OK)
        else:
            self.ind_maos.definir("nenhuma", COR_ATENCAO)
        if not self.voz.disponivel:
            self.ind_voz.definir("indisponível", COR_ERRO)

    def _atualizar_textos(self) -> None:
        s = self.sentenca
        if s.sinal_atual:
            self.lbl_sinal.configure(text=config.rotulo_exibicao(s.sinal_atual))
            self.barra_conf.set(s.confianca_atual)
            aceita = s.confianca_atual >= config.LIMIAR_CONFIANCA
            self.barra_conf.configure(progress_color=COR_OK if aceita else COR_ATENCAO)
            self.lbl_conf.configure(text=f"{s.confianca_atual:.0%}" + ("" if aceita else " (baixa)"))
        else:
            self.lbl_sinal.configure(text="—")
            self.barra_conf.set(0)
            self.lbl_conf.configure(text="nenhum sinal" if self.processador else "0%")
        self.lbl_confirmado.configure(text=config.rotulo_exibicao(s.ultimo_confirmado) if s.ultimo_confirmado else "—")
        self.lbl_sequencia.configure(text="  ·  ".join(s.sequencia) or "—")
        self.lbl_final.configure(text=s.frase_final or "—")
        if self.voz.disponivel:
            self.ind_voz.definir("falando..." if self.voz.falando else "pronta", COR_OK)

    def _mostrar_aviso(self, texto: str) -> None:
        """Mostra um aviso por 4 s. Chamado a cada frame pelo mesmo aviso (ex.: ombros
        fora da imagem), só renova o prazo: nunca acumula temporizadores."""
        if self._aviso_agendado is not None:
            self.after_cancel(self._aviso_agendado)
        if texto != self._aviso_atual:
            self.lbl_aviso.configure(text=texto, text_color=COR_ATENCAO)
            self._aviso_atual = texto
        self._aviso_agendado = self.after(4000, self._limpar_aviso)

    def _limpar_aviso(self) -> None:
        self._aviso_agendado = None
        self._aviso_atual = ""
        self.lbl_aviso.configure(text=ATALHOS, text_color=COR_TEXTO_SECUNDARIO)

    # --- frase e voz ---------------------------------------------------------------

    def _ao_finalizar(self, frase: str) -> None:
        """Chamado pelo GerenciadorSentenca quando uma frase é encerrada."""
        self.lbl_final.configure(text=frase)
        if config.FALAR_AO_FINALIZAR:
            self._falar(frase)

    def _falar(self, texto: str) -> None:
        if not self.voz.disponivel:
            self._mostrar_aviso(f"Voz indisponível: {self.voz.erro or 'sem motor de voz'}")
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
    ctk.set_appearance_mode(tema)
    ctk.set_default_color_theme("blue")
    aplicacao = AplicacaoLibras(indice_camera)
    if aplicacao.erro_modelo:
        aplicacao._mostrar_aviso("Modelo não encontrado: a câmera mostra só os landmarks. "
                                 "Treine com scripts/desenvolvimento/treinar_modelo.py")
    aplicacao.mainloop()
