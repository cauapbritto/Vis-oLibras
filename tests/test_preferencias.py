"""Preferências da janela Configurações (preferencias.json)."""

import json

import pytest

from libras import config, preferencias


@pytest.fixture
def arquivo(tmp_path, monkeypatch):
    caminho = tmp_path / "preferencias.json"
    monkeypatch.setattr(config, "ARQ_PREFERENCIAS", caminho)
    for nome, campo in preferencias.CAMPOS.items():   # cada teste começa no padrão
        monkeypatch.setattr(config, campo.atributo, preferencias.PADROES[nome])
    monkeypatch.setattr(preferencias, "_estado", dict(preferencias.ESTADOS))
    return caminho


def test_definir_aplica_e_salva_so_o_que_mudou(arquivo):
    preferencias.definir("taxa_fala", 210)
    preferencias.definir("limiar_confianca", 0.8)
    assert config.TAXA_FALA == 210 and config.LIMIAR_CONFIANCA == 0.8
    assert json.loads(arquivo.read_text(encoding="utf-8")) == {"taxa_fala": 210, "limiar_confianca": 0.8}


def test_valores_invalidos_sao_recusados(arquivo):
    with pytest.raises(ValueError):
        preferencias.definir("taxa_fala", 999)
    with pytest.raises(ValueError):
        preferencias.definir("modo_leve", "turbo")
    with pytest.raises(ValueError):
        preferencias.definir("falar_cada_palavra", "sim")


def test_carregar_aplica_e_avisa_o_que_esta_errado(arquivo):
    arquivo.write_text(json.dumps({"pausa_frase_s": 1.5, "taxa_fala": 5, "cor": "azul",
                                   "verificacao_feita": True}), encoding="utf-8")
    avisos = preferencias.carregar()
    assert config.PAUSA_FRASE_S == 1.5 and config.TAXA_FALA == preferencias.PADROES["taxa_fala"]
    assert preferencias.estado("verificacao_feita") is True
    assert len(avisos) == 2 and any("cor" in a for a in avisos)


def test_arquivo_ilegivel_nao_quebra(arquivo):
    arquivo.write_text("{isso não é json", encoding="utf-8")
    assert "ilegível" in preferencias.carregar()[0]


def test_restaurar_padrao_apaga_o_arquivo(arquivo):
    preferencias.definir("modo_leve", "ligado")
    preferencias.restaurar_padrao()
    assert config.MODO_LEVE == preferencias.PADROES["modo_leve"] and not arquivo.exists()
