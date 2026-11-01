import json

import pytest

from esteira.cortar import cortar_episodio, ler_aprovados
from esteira.modelos import Corte, Palavra
from tests.auxiliares import gerar_video_teste


def preparar(tmp_path, cortes):
    pasta = tmp_path / "ep"
    (pasta / "transcricao").mkdir(parents=True)
    video = gerar_video_teste(tmp_path / "v.mp4", 80)
    cartao = gerar_video_teste(tmp_path / "fim.mp4", 1, 1080, 1920)
    (pasta / "episodio.json").write_text(json.dumps({"video": str(video), "duracao": 80}), "utf-8")
    palavras = [{"texto": "fala.", "inicio": t + 0.0, "fim": t + 0.9} for t in range(1, 70)]
    (pasta / "transcricao" / "palavras.json").write_text(json.dumps(palavras), "utf-8")
    (pasta / "aprovados.json").write_text(json.dumps({"cortes": cortes}), "utf-8")
    return pasta, cartao


BOM = {"numero": 1, "titulo": "Bom corte", "inicio": 1.0, "fim": 62.9, "clima": "leve"}
RUIM = {"numero": 2, "titulo": "Ruim", "inicio": 1.0, "fim": 10.9, "clima": "tenso"}


def test_le_aprovados(tmp_path):
    pasta, _ = preparar(tmp_path, [BOM])
    assert ler_aprovados(pasta) == [Corte(1, "Bom corte", 1.0, 62.9, "leve")]


def test_gera_todos_os_arquivos(tmp_path):
    pasta, cartao = preparar(tmp_path, [BOM])
    assert cortar_episodio(pasta, cartao=cartao, nomes=[]) == {1: "ok"}
    corte = pasta / "01-bom-corte"
    for nome in ("corte.mp4", "corte-sem-legenda.mp4", "legenda.srt", "edicoes.md", "registro.json"):
        assert (corte / nome).exists(), nome
    assert (corte / "imagens").is_dir()


def test_um_corte_invalido_nao_para_os_outros(tmp_path):
    pasta, cartao = preparar(tmp_path, [RUIM, BOM])
    r = cortar_episodio(pasta, cartao=cartao, nomes=[])
    assert r[1] == "ok" and r[2].startswith("erro")
    assert (pasta / "02-ruim" / "registro.json").exists()


def test_nao_sobrescreve_sem_forcar(tmp_path):
    pasta, cartao = preparar(tmp_path, [BOM])
    cortar_episodio(pasta, cartao=cartao, nomes=[])
    assert cortar_episodio(pasta, cartao=cartao, nomes=[])[1].startswith("erro")
    assert cortar_episodio(pasta, cartao=cartao, nomes=[], forcar=True)[1] == "ok"


def test_filtra_por_numero(tmp_path):
    pasta, cartao = preparar(tmp_path, [RUIM, BOM])
    assert list(cortar_episodio(pasta, {1}, cartao=cartao, nomes=[])) == [1]
