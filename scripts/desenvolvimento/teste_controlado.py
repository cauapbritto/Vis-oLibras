"""Teste controlado do protótipo com participantes (modo desenvolvimento).

Cada participante faz cada sinal N vezes, em ordem aleatória (semente
registrada). O programa mostra "Faça: SINAL", conta até o "JÁ!" e registra o
que o sistema reconheceu, a confiança e o tempo de resposta. Os resultados vão
para reports/testes/<sessao>.csv, uma linha por tentativa, gravada na hora.

Uso:
    python scripts/desenvolvimento/teste_controlado.py --participante ana
    python scripts/desenvolvimento/teste_controlado.py --participante ana --repeticoes 5 --sinais OI SIM NAO
    python scripts/desenvolvimento/teste_controlado.py --participante ana --incluir-nada

Teclas:
    ESPAÇO   começa / pausa
    D        (durante o resultado) descarta a tentativa - ex.: o participante
             fez o sinal errado ou se distraiu; o mesmo sinal é refeito
    Q/ESC    encerra (o que já foi medido fica salvo)

Depois: python scripts/desenvolvimento/resumir_testes.py
"""

import argparse
import json
import random
import sys
import time
import warnings
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))  # funciona sem "pip install -e ."

import cv2  # noqa: E402

from libras import config, dataset, preferencias  # noqa: E402
from libras.camera import Camera, ErroCamera  # noqa: E402
from libras.classificador import ErroClassificador, carregar_classificador  # noqa: E402
from libras.desenho import (COR_AVISO, COR_OK, COR_TEXTO, descrever_maos, desenhar_legenda,  # noqa: E402
                            desenhar_painel, eh_tecla_sair, janela_fechada, ler_tecla)
from libras.estabilizador import Estabilizador  # noqa: E402
from libras.experimento import (AGUARDANDO, CONTAGEM, EXECUCAO, FIM, NENHUM, RESULTADO,  # noqa: E402
                                RegistroCSV, SessaoTeste, plano_de_tentativas)
from libras.extrator import ErroModelo  # noqa: E402
from libras.pipeline import PipelineVisao  # noqa: E402

COR_ERRO = (60, 60, 230)


def texto_legenda(sessao: SessaoTeste, agora: float) -> list[tuple[str, tuple, int]]:
    rotulo = config.rotulo_exibicao(sessao.atual) if sessao.atual else ""
    if sessao.atual == config.CLASSE_NADA:
        rotulo = "NÃO SINALIZE (fique natural)"
    if sessao.estado == AGUARDANDO:
        return [("ESPAÇO para começar", COR_TEXTO, 28)]
    if sessao.estado == CONTAGEM:
        return [(f"Faça: {rotulo}", COR_TEXTO, 34),
                (f"abaixe as mãos... {max(sessao.fim_fase - agora, 0):.0f}", COR_AVISO, 22)]
    if sessao.estado == EXECUCAO:
        return [(f"JÁ!  {rotulo}", COR_OK, 34)]
    if sessao.estado == RESULTADO and sessao.resultado:
        r = sessao.resultado
        reconhecido = config.rotulo_exibicao(r.sinal_reconhecido) if r.sinal_reconhecido != NENHUM else "nada"
        detalhe = f"{r.confianca:.0%}, {r.tempo_resposta_s:.2f} s" if r.tempo_resposta_s else "tempo esgotado"
        return [(("✓ " if r.acerto else "✗ ") + f"reconhecido: {reconhecido} ({detalhe})",
                 COR_OK if r.acerto else COR_ERRO, 28),
                ("D descarta esta tentativa", COR_TEXTO, 18)]
    if sessao.estado == FIM:
        return [("Teste concluído! Q para sair", COR_OK, 30)]
    return []


def main() -> int:
    preferencias.carregar()  # ex.: a câmera escolhida na janela da aplicação
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--participante", required=True, help="identificação (ex.: ana, p01)")
    parser.add_argument("--sinais", nargs="+", help="sinais a testar (padrão: todos os do modelo)")
    parser.add_argument("--repeticoes", type=int, default=config.TESTE_REPETICOES)
    parser.add_argument("--incluir-nada", action="store_true",
                        help="inclui tentativas de NÃO sinalizar (mede falsos positivos)")
    parser.add_argument("--ordem", choices=["aleatoria", "sequencial"], default="aleatoria")
    parser.add_argument("--semente", type=int, help="semente da ordem aleatória (padrão: sorteada e registrada)")
    parser.add_argument("--camera", type=int, default=config.INDICE_CAMERA)
    args = parser.parse_args()

    try:
        participante = dataset.validar_pessoa(args.participante)
    except ValueError as erro:
        parser.error(str(erro))
    if args.repeticoes < 1:
        parser.error("--repeticoes deve ser pelo menos 1")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            classificador = carregar_classificador()
    except ErroClassificador as erro:
        print(f"[ERRO] {erro}", file=sys.stderr)
        return 1

    conhecidos = [c for c in classificador.classes if c != config.CLASSE_NADA]
    sinais = [config.identificador_sinal(s) for s in args.sinais] if args.sinais else conhecidos
    desconhecidos = [s for s in sinais if s not in classificador.classes]
    if desconhecidos:
        parser.error(f"o modelo não reconhece {desconhecidos}; sinais do modelo: {conhecidos}")
    if args.incluir_nada:
        sinais = sinais + [config.CLASSE_NADA]
    semente = args.semente if args.semente is not None else random.randrange(1_000_000)
    plano = plano_de_tentativas(sinais, args.repeticoes, semente, args.ordem == "aleatoria")

    sessao_id = f"{participante}_{datetime.now():%Y%m%d_%H%M%S}"
    caminho_csv = config.DIR_TESTES / f"{sessao_id}.csv"
    registro = RegistroCSV(caminho_csv)
    modelo = f"{classificador.info.get('descricao')} {classificador.info.get('criado_em')}"
    estabilizador = Estabilizador()
    metadados = {
        "sessao": sessao_id, "participante": participante, "sinais": sinais,
        "repeticoes": args.repeticoes, "ordem": args.ordem, "semente": semente,
        "modelo": classificador.info.get("descricao"), "modelo_criado_em": classificador.info.get("criado_em"),
        "features_versao": classificador.versao_features,
        "estabilizador": {"limiar": estabilizador.limiar, "consecutivas": estabilizador.n_consecutivas,
                          "cooldown_s": estabilizador.cooldown_s},
        "contagem_s": config.TESTE_CONTAGEM_S, "janela_s": config.TESTE_JANELA_S,
        "inicio": datetime.now().isoformat(timespec="seconds"),
    }
    arquivo_meta = caminho_csv.with_name(f"{sessao_id}_sessao.json")

    pipeline = PipelineVisao(classificador, estabilizador)
    sessao = SessaoTeste(plano, participante, sessao_id, modelo, registro.adicionar,
                         ao_iniciar_tentativa=pipeline.reiniciar_estabilizador)
    print(f"Sessão {sessao_id}: {len(plano)} tentativas ({len(sinais)} sinais x {args.repeticoes}), "
          f"semente {semente}.\nResultados em {caminho_csv}")
    try:
        with Camera(indice=args.camera) as camera:
            cv2.namedWindow(config.NOME_JANELA)
            while True:
                frame = camera.ler()
                if frame is None:
                    if eh_tecla_sair(ler_tecla(10)) or janela_fechada():
                        break
                    continue
                quadro = pipeline.processar(frame)
                estado = quadro.estado
                sessao.atualizar(quadro.momento, estado.palavra, estado.confianca, quadro.resultado.tem_maos,
                                 quadro.fps, estado.tempo_inferencia_ms if estado.inferiu else 0.0)

                imagem = quadro.imagem
                desenhar_painel(imagem, [
                    (f"Participante: {participante}   Tentativa {min(sessao.numero_atual, sessao.total)}"
                     f"/{sessao.total}", COR_TEXTO),
                    (descrever_maos(quadro.resultado), COR_TEXTO),
                    (f"FPS: {quadro.fps:.1f}", COR_TEXTO),
                    ("ESPAÇO começar/pausar | D descartar | Q sair", COR_TEXTO),
                ])
                desenhar_legenda(imagem, texto_legenda(sessao, quadro.momento))
                cv2.imshow(config.NOME_JANELA, imagem)

                tecla = ler_tecla()
                if eh_tecla_sair(tecla) or janela_fechada():
                    break
                if tecla == ord(" "):
                    if sessao.estado == AGUARDANDO:
                        sessao.iniciar(time.perf_counter())
                    else:
                        sessao.pausar()
                elif tecla in (ord("d"), ord("D")) and sessao.descartar():
                    print("  tentativa descartada; será refeita")
    except (ErroCamera, ErroModelo) as erro:
        print(f"[ERRO] {erro}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrompido pelo usuário.")
    finally:
        sessao.pausar()  # confirma um resultado que estava na tela
        pipeline.fechar()
        cv2.destroyAllWindows()
        metadados.update(fim=datetime.now().isoformat(timespec="seconds"),
                         tentativas_registradas=len(sessao.registradas), tentativas_planejadas=len(plano))
        arquivo_meta.write_text(json.dumps(metadados, ensure_ascii=False, indent=2), encoding="utf-8")

    acertos = sum(t.acerto for t in sessao.registradas)
    print(f"{len(sessao.registradas)} de {len(plano)} tentativas registradas"
          + (f", {acertos} acertos ({acertos / len(sessao.registradas):.0%})" if sessao.registradas else ""))
    print(f"CSV: {caminho_csv}\nResumo: python scripts/desenvolvimento/resumir_testes.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
