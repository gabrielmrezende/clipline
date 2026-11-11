import os
import time

import pytest

from esteira.publicar import fila
from esteira.publicar.fila import ARQUIVO, Item, Ocupado, achar, gravar_fila, ler_fila, trava


@pytest.fixture(autouse=True)
def _sem_restricao(monkeypatch):
    monkeypatch.setattr(fila, "garantir_escrita", lambda caminho: caminho)


def test_grava_e_le_fila(tmp_path):
    itens = [
        Item(1, "youtube", "2026-11-08T18:00:00-03:00"),
        Item(1, "tiktok", "2026-11-08T18:00:00-03:00", "erro", 3, "", "", "falhou"),
    ]
    gravar_fila(tmp_path, itens)
    assert (tmp_path / ARQUIVO).exists()
    assert ler_fila(tmp_path) == itens


def test_fila_inexistente_vazia(tmp_path):
    assert ler_fila(tmp_path) == []


def test_gravar_nao_deixa_temporario(tmp_path):
    gravar_fila(tmp_path, [Item(1, "youtube", "x")])
    assert sorted(p.name for p in tmp_path.iterdir()) == [ARQUIVO]


def test_achar_ignora_cancelado():
    cancelado = Item(1, "youtube", "x", "cancelado")
    agendado = Item(1, "youtube", "y")
    assert achar([cancelado, agendado], 1, "youtube") is agendado
    assert achar([cancelado], 1, "youtube") is None


def test_trava_impede_segunda(tmp_path):
    with trava(tmp_path / "t.trava"):
        with pytest.raises(Ocupado):
            with trava(tmp_path / "t.trava"):
                pass
    assert not (tmp_path / "t.trava").exists()


def test_trava_velha_e_removida(tmp_path):
    p = tmp_path / "t.trava"
    p.write_text("x")
    os.utime(p, (time.time() - 7300,) * 2)
    with trava(p):
        assert p.exists()
    assert not p.exists()


def test_trava_solta_mesmo_com_erro(tmp_path):
    with pytest.raises(RuntimeError):
        with trava(tmp_path / "t.trava"):
            raise RuntimeError("x")
    assert not (tmp_path / "t.trava").exists()


def test_item_antigo_sem_campo_ia_continua_legivel(tmp_path):
    from esteira.publicar.fila import ARQUIVO, ler_fila

    (tmp_path / ARQUIVO).write_text('{"itens": [{"numero": 1, "rede": "youtube", "data": "2026-11-08T18:00:00-03:00"}]}', "utf-8")
    assert ler_fila(tmp_path)[0].ia is False


def test_enviar_passa_ia_so_quando_marcado(tmp_path, monkeypatch):
    from esteira.publicar import envio, fila
    from esteira.publicar.fila import Item
    from esteira.publicar.http import Resultado
    from tests.auxiliares_publicar import TEXTOS

    monkeypatch.setattr(envio, "gravar_fila", lambda pasta, itens, base=None: None)
    recebidos = []

    class Api:
        def publicar(self, video, textos, data, modo, **extras):
            recebidos.append(extras)
            return Resultado("publicado")

    for ia in (False, True):
        item = Item(1, "youtube", "2026-11-08T18:00:00-03:00", ia=ia)
        envio.enviar(tmp_path, [item], item, tmp_path / "v.mp4", TEXTOS, "privado", Api())
    assert recebidos == [{}, {"ia": True}]
