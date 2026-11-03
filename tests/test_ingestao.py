import os

import pytest

from esteira.ingestao import arquivos_ia, encaixar_ia


def _ep(tmp_path):
    ep = tmp_path / "ep"
    (ep / "ia-entrada").mkdir(parents=True)
    corte = ep / "01-corte"
    corte.mkdir()
    return ep, corte


def _arquivo(ep, nome, mtime=None, conteudo=b"x"):
    caminho = ep / "ia-entrada" / nome
    caminho.write_bytes(conteudo)
    if mtime is not None:
        os.utime(caminho, (mtime, mtime))
    return caminho


def test_ordem_por_data(tmp_path):
    ep, _ = _ep(tmp_path)
    _arquivo(ep, "a.png", 200)
    _arquivo(ep, "b.png", 100)
    assert [p.name for p in arquivos_ia(ep)] == ["b.png", "a.png"]


def test_empate_de_data_desempata_pelo_nome(tmp_path):
    ep, _ = _ep(tmp_path)
    _arquivo(ep, "b.png", 100)
    _arquivo(ep, "a.png", 100)
    assert [p.name for p in arquivos_ia(ep)] == ["a.png", "b.png"]


def test_ignora_mapa_e_ocultos(tmp_path):
    ep, _ = _ep(tmp_path)
    _arquivo(ep, ".mapa.tsv")
    _arquivo(ep, ".x.png")
    _arquivo(ep, "nota.txt")
    assert arquivos_ia(ep) == []


def test_sem_pasta_ia_entrada(tmp_path):
    assert arquivos_ia(tmp_path) == []


def test_contagem_diferente_nao_grava(tmp_path):
    ep, corte = _ep(tmp_path)
    _arquivo(ep, "a.png")
    destinos = [(corte, "01-a", "01\t1\tA\tp"), (corte, "02-b", "01\t2\tB\tq")]
    with pytest.raises(ValueError, match="esperadas 2 imagens, encontradas 1"):
        encaixar_ia(ep, destinos)
    assert not (corte / "imagens").exists() or not any((corte / "imagens").iterdir())
    assert not (ep / "ia-entrada" / ".mapa.tsv").exists()


def test_encaixa_e_grava_mapa(tmp_path):
    ep, corte = _ep(tmp_path)
    _arquivo(ep, "Qualquer.PNG")
    encaixar_ia(ep, [(corte, "02-chuva", "01\t2\tChuva\tprompt")])
    assert (corte / "imagens" / "02-chuva.png").exists()
    mapa = (ep / "ia-entrada" / ".mapa.tsv").read_text("utf-8")
    assert mapa == "01\t2\tChuva\tprompt\tQualquer.PNG\n"
    assert (ep / "ia-entrada" / "Qualquer.PNG").exists()


def test_sem_destinos_nao_exige_pasta_nem_grava_mapa(tmp_path):
    assert encaixar_ia(tmp_path / "nao-existe", []) == []
    assert not (tmp_path / "nao-existe").exists()
