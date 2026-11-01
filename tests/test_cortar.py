import json

import pytest

from esteira import cortar
from esteira.cortar import cortar_episodio, ler_aprovados
from esteira.midia import ErroMidia
from esteira.modelos import Corte, Palavra
from esteira.planos import Plano, gravar_planos
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


def test_erro_de_sistema_nao_para_os_outros(tmp_path, monkeypatch):
    pasta, cartao = preparar(tmp_path, [BOM, {**BOM, "numero": 2, "titulo": "Outro"}])
    original = cortar.queimar_legenda

    def falhar_no_primeiro(base, ass, saida):
        if "01-" in str(saida):
            raise PermissionError("arquivo aberto")
        original(base, ass, saida)

    monkeypatch.setattr(cortar, "queimar_legenda", falhar_no_primeiro)
    r = cortar_episodio(pasta, cartao=cartao, nomes=[])
    assert r[1].startswith("erro") and r[2] == "ok"
    assert (pasta / "01-bom-corte" / "registro.json").exists()


def test_forcar_com_falha_nao_deixa_corte_antigo(tmp_path, monkeypatch):
    pasta, cartao = preparar(tmp_path, [BOM])
    cortar_episodio(pasta, cartao=cartao, nomes=[])

    def falhar(base, ass, saida):
        raise ErroMidia("falhou")

    monkeypatch.setattr(cortar, "queimar_legenda", falhar)
    assert cortar_episodio(pasta, cartao=cartao, nomes=[], forcar=True)[1].startswith("erro")
    assert not (pasta / "01-bom-corte" / "corte.mp4").exists()


def test_usa_enquadramento_gravado(tmp_path, monkeypatch):
    pasta, cartao = preparar(tmp_path, [BOM])
    corte = pasta / "01-bom-corte"
    corte.mkdir()
    gravar_planos(corte, [Plano(1.0, 62.9, x=0.3, zoom=2)])
    usados = []
    original = cortar.renderizar_sem_legenda

    def espiar(video, faixas, fim, saida, planos=None, sobreposicao=None):
        usados.append(planos)
        original(video, faixas, fim, saida, planos, sobreposicao)

    monkeypatch.setattr(cortar, "renderizar_sem_legenda", espiar)
    cortar_episodio(pasta, cartao=cartao, nomes=[])
    assert usados == [[Plano(1.0, 62.9, x=0.3, zoom=2)]]


def test_encerramento_alterna_entre_os_quatro_videos():
    escolhidos = [cortar.escolher_encerramento(n).name for n in range(1, 6)]
    assert len(set(escolhidos[:4])) == 4
    assert escolhidos[4] == escolhidos[0]
    assert all(n.startswith("Final Corte") for n in escolhidos)


def test_filtra_por_numero(tmp_path):
    pasta, cartao = preparar(tmp_path, [RUIM, BOM])
    assert list(cortar_episodio(pasta, {1}, cartao=cartao, nomes=[])) == [1]
