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


# --- trava com PID ------------------------------------------------------------------------------------------


def test_trava_grava_pid_e_inicio(tmp_path):
    import json

    with trava(tmp_path / "t.trava"):
        dados = json.loads((tmp_path / "t.trava").read_text("utf-8"))
    assert dados["pid"] == os.getpid()
    assert dados["inicio"][:2] == "20" and "T" in dados["inicio"]


def test_trava_de_processo_morto_e_removida_na_hora(tmp_path):
    import json

    p = tmp_path / "t.trava"
    p.write_text(json.dumps({"pid": 4321, "inicio": "2026-11-15T10:00:00-03:00"}), "utf-8")
    with trava(p, vivo=lambda pid: False):
        assert json.loads(p.read_text("utf-8"))["pid"] == os.getpid()


def test_trava_de_processo_vivo_segura(tmp_path):
    import json

    p = tmp_path / "t.trava"
    p.write_text(json.dumps({"pid": 4321, "inicio": "2026-11-15T10:00:00-03:00"}), "utf-8")
    vistos = []
    with pytest.raises(Ocupado):
        with trava(p, vivo=lambda pid: vistos.append(pid) or True):
            pass
    assert vistos == [4321] and p.exists()


def test_trava_de_processo_vivo_mas_velha_cai_pela_reserva_de_2h(tmp_path):
    import json

    p = tmp_path / "t.trava"
    p.write_text(json.dumps({"pid": 4321}), "utf-8")
    os.utime(p, (time.time() - 7300,) * 2)
    with trava(p, vivo=lambda pid: True):
        pass
    assert not p.exists()


def test_trava_antiga_sem_pid_vale_pela_idade(tmp_path):
    p = tmp_path / "t.trava"
    p.write_text("", "utf-8")  # versão anterior, ou outro processo entre criar e escrever
    with pytest.raises(Ocupado):
        with trava(p, vivo=lambda pid: False):
            pass


def test_processo_vivo_de_verdade():
    import subprocess
    import sys

    from esteira.publicar.fila import processo_vivo

    assert processo_vivo(os.getpid())
    filho = subprocess.Popen([sys.executable, "-c", "pass"])
    filho.wait()
    assert not processo_vivo(filho.pid)
    assert not processo_vivo(0) and not processo_vivo(-1)


def test_processo_vivo_no_windows_nao_usa_os_kill(monkeypatch):
    import sys

    from esteira.publicar import fila as modulo

    if sys.platform != "win32":
        pytest.skip("OpenProcess só existe no Windows")

    def proibido(*a):
        raise AssertionError("os.kill no Windows encerra o processo")

    monkeypatch.setattr(modulo.os, "kill", proibido)
    assert modulo.processo_vivo(os.getpid())


def test_processo_vivo_no_posix_usa_sinal_zero(monkeypatch):
    from esteira.publicar import fila as modulo

    sinais = []

    def kill(pid, sinal):
        sinais.append((pid, sinal))
        if pid == 99:
            raise ProcessLookupError
        if pid == 98:
            raise PermissionError

    monkeypatch.setattr(modulo.os, "kill", kill)
    assert modulo.processo_vivo(97, "linux") and not modulo.processo_vivo(99, "linux")
    assert modulo.processo_vivo(98, "darwin")  # existe, mas é de outro usuário
    assert sinais == [(97, 0), (99, 0), (98, 0)]
