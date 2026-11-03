from pathlib import Path

from PIL import Image

import pytest

from esteira.folhas import ALTURA_FOLHA, LARGURA_FOLHA, _legenda, montar_folha
from esteira.wikimedia import Candidata


def cand(i: int, autor: str = "Fulano de Tal", licenca: str = "CC BY-SA 4.0", largura: int = 2000, altura: int = 1000) -> Candidata:
    return Candidata(
        titulo=f"File:Foto {i}.jpg",
        pagina=f"https://commons.wikimedia.org/wiki/File:Foto_{i}.jpg",
        miniatura=f"https://upload.wikimedia.org/foto{i}.jpg",
        largura=largura,
        altura=altura,
        autor=autor,
        licenca=licenca,
    )


def mini(tmp_path: Path, i: int) -> Path:
    tamanho = (300, 600) if i % 2 else (640, 360)
    caminho = tmp_path / f"mini{i}.jpg"
    Image.new("RGB", tamanho, (40 * i % 255, 120, 200)).save(caminho)
    return caminho


def test_folha_com_seis(tmp_path):
    saida = montar_folha("01-1 Yas Marina", [cand(i) for i in range(6)], [mini(tmp_path, i) for i in range(6)], tmp_path / "f.jpg")
    with Image.open(saida) as img:
        assert img.size == (LARGURA_FOLHA, ALTURA_FOLHA) == (1200, ALTURA_FOLHA)
        assert img.format == "JPEG"


def test_miniatura_ausente_ou_quebrada(tmp_path):
    ruim = tmp_path / "ruim.jpg"
    ruim.write_bytes(b"<html>")
    saida = montar_folha("x", [cand(0), cand(1)], [None, ruim], tmp_path / "f.jpg")
    assert saida.exists()


def test_sem_candidatas(tmp_path):
    assert montar_folha("x", [], [], tmp_path / "f.jpg").exists()


def test_autor_longo_nao_quebra(tmp_path):
    longa = cand(0, autor="A" * 200)
    saida = montar_folha("x", [longa], [mini(tmp_path, 0)], tmp_path / "f.jpg")
    with Image.open(saida) as img:
        assert img.size == (LARGURA_FOLHA, ALTURA_FOLHA)


def test_legenda_autor_longo_mantem_licenca_inteira():
    orientacao, autor, licenca = _legenda(3, cand(0, autor="A" * 200, licenca="CC BY-SA 4.0"))
    assert orientacao.startswith("3 · ")
    assert len(autor) <= 45
    assert licenca == "CC BY-SA 4.0"


@pytest.mark.parametrize(("largura", "altura", "esperado"), [(1000, 1500, "vertical"), (1000, 2000, "vertical"), (1000, 1499, "horizontal"), (2000, 1000, "horizontal")])
def test_legenda_orientacao(largura, altura, esperado):
    assert _legenda(1, cand(0, largura=largura, altura=altura))[0] == f"1 · {esperado}"
