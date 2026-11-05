from PIL import Image

from esteira import pessoas
from esteira.enquadrar import Cena, Rosto, TrechoVoz


def _rosto(pessoa, x=0.5):
    return Rosto(pessoa, x, 0.4, 0.1, 0.2)


def test_liga_pelo_close():
    vozes = [TrechoVoz(0, 10, "V2"), TrechoVoz(10, 20, "V1")]
    cenas = [Cena(0, 10, [_rosto("P1")]), Cena(10, 20, [_rosto("P2")])]
    assert pessoas.ligar(vozes, cenas) == {"V2": "P1", "V1": "P2"}


def test_voz_sem_close_fica_fora():
    vozes = [TrechoVoz(0, 10, "V1"), TrechoVoz(10, 20, "V3")]
    cenas = [Cena(0, 10, [_rosto("P1")]), Cena(10, 20, [_rosto("P1", 0.3), _rosto("P2", 0.7)])]
    ligacao = pessoas.ligar(vozes, cenas)
    assert ligacao == {"V1": "P1"}
    assert "V3" not in ligacao


def test_nao_repete_pessoa():
    # V1 (8 s) e V2 (5 s) têm a maior soma em P1; V2 cai para P2 (3 s)
    vozes = [TrechoVoz(0, 8, "V1"), TrechoVoz(8, 13, "V2"), TrechoVoz(13, 16, "V2")]
    cenas = [Cena(0, 13, [_rosto("P1")]), Cena(13, 16, [_rosto("P2")])]
    assert pessoas.ligar(vozes, cenas) == {"V1": "P1", "V2": "P2"}


def test_nao_repete_pessoa_sem_alternativa():
    vozes = [TrechoVoz(0, 8, "V1"), TrechoVoz(8, 13, "V2")]
    cenas = [Cena(0, 13, [_rosto("P1")])]
    assert pessoas.ligar(vozes, cenas) == {"V1": "P1"}


def test_empate_vai_pela_ordem_do_nome():
    vozes = [TrechoVoz(0, 5, "V2"), TrechoVoz(5, 10, "V1")]
    cenas = [Cena(0, 10, [_rosto("P1")])]
    assert pessoas.ligar(vozes, cenas) == {"V1": "P1"}


def test_gravar_e_ler_pessoas(tmp_path):
    assert pessoas.ler_pessoas(tmp_path) is None
    (tmp_path / "transcricao").mkdir()
    pessoas.gravar_pessoas(tmp_path, {"V1": "P2"}, {"P2": [0.1, 0.2]}, {"P2": ""})
    assert pessoas.ler_pessoas(tmp_path) == ({"V1": "P2"}, {"P2": [0.1, 0.2]}, {"P2": ""})
    assert not list((tmp_path / "transcricao").glob("*.tmp"))


def test_folha_pessoas(tmp_path, monkeypatch):
    chamadas = []

    def falso(args, cwd=None):
        chamadas.append(args)
        Image.new("RGB", (640, 360), "#336699").save(args[-1])

    monkeypatch.setattr(pessoas, "executar_ffmpeg", falso)
    amostras = {"P2": (12.0, _rosto("P2")), "P3": (30.0, _rosto("P3", 0.2))}
    saida = tmp_path / "pessoas.jpg"
    resultado = pessoas.folha_pessoas(
        tmp_path / "v.mp4", amostras, {"V1": "P2"}, {"V1": 312.0}, {"P2": "Ana"}, saida
    )
    assert resultado == saida and saida.exists()
    assert len(chamadas) == 2
    with Image.open(saida) as folha:
        assert folha.width <= 2 * 640


def test_vazamento_nao_liga():
    # V1 fala 30 s, só 0,5 s dentro do close de P4; P2 já é de V2
    vozes = [TrechoVoz(0, 20, "V2"), TrechoVoz(20, 20.5, "V1"), TrechoVoz(20.5, 50, "V1")]
    cenas = [
        Cena(0, 20, [_rosto("P2")]),
        Cena(20, 20.5, [_rosto("P4")]),
        Cena(20.5, 50, [_rosto("P2", 0.3), _rosto("P1", 0.7)]),
    ]
    assert pessoas.ligar(vozes, cenas) == {"V2": "P2"}


def test_folha_sem_pessoas(tmp_path):
    import pytest

    with pytest.raises(ValueError, match="nenhuma pessoa"):
        pessoas.folha_pessoas(tmp_path / "v.mp4", {}, {}, {}, {}, tmp_path / "p.jpg")


def test_gravar_cria_pasta(tmp_path):
    pessoas.gravar_pessoas(tmp_path, {}, {}, {})
    assert pessoas.ler_pessoas(tmp_path) == ({}, {}, {})
