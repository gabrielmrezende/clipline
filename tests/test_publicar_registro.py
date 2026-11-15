"""Log do publicar rodar: rotação por tamanho e convivência com a tarefa antiga, que redireciona pelo cmd."""
import io
import sys

import pytest

from esteira.publicar import registro
from esteira.publicar.registro import RotacaoTolerante, saida_e_o_log


def _gravar(log, linhas, **opcoes):
    with registro.registro(log, saida=io.StringIO(), **opcoes) as (logger, antiga):
        for linha in linhas:
            logger.info(linha)
    return antiga


def test_grava_e_solta_o_arquivo(tmp_path):
    log = tmp_path / "logs" / "publicar.log"
    assert _gravar(log, ["01 youtube: privado L"]) is False
    assert log.read_text("utf-8").endswith(" 01 youtube: privado L\n")
    log.rename(tmp_path / "solto.log")  # no Windows só dá se o arquivo foi fechado


def test_gira_por_tamanho(tmp_path, monkeypatch):
    monkeypatch.setattr(registro, "TAMANHO_MAXIMO", 200)
    log = tmp_path / "publicar.log"
    _gravar(log, [f"linha {i:03d} " + "x" * 40 for i in range(20)])
    copias = sorted(p.name for p in tmp_path.iterdir())
    assert copias == ["publicar.log"] + [f"publicar.log.{i}" for i in range(1, registro.COPIAS + 1)]
    assert all(p.stat().st_size <= 200 for p in tmp_path.iterdir())
    assert "linha 019" in log.read_text("utf-8")


def test_rotacao_que_falha_segue_no_mesmo_arquivo(tmp_path, monkeypatch):
    """No Windows, o arquivo aberto por outro processo não pode ser renomeado: o registro não para."""
    def sem_renomear(self, origem, destino):
        raise PermissionError(32, "O arquivo já está sendo usado por outro processo")

    monkeypatch.setattr(RotacaoTolerante, "rotate", sem_renomear)
    monkeypatch.setattr(registro, "TAMANHO_MAXIMO", 100)
    log = tmp_path / "publicar.log"
    log.write_text("x" * 150 + "\n", "utf-8")
    _gravar(log, ["01 instagram: publicado L", "02 tiktok: rascunho"])
    texto = log.read_text("utf-8")
    assert "01 instagram: publicado L" in texto and "02 tiktok: rascunho" in texto
    assert sorted(p.name for p in tmp_path.iterdir()) == ["publicar.log"]


@pytest.mark.skipif(sys.platform != "win32", reason="o bloqueio de renomear arquivo aberto é do Windows")
def test_windows_arquivo_aberto_por_outro_programa(tmp_path, monkeypatch):
    monkeypatch.setattr(registro, "TAMANHO_MAXIMO", 100)
    log = tmp_path / "publicar.log"
    log.write_text("y" * 150 + "\n", "utf-8")
    with open(log, "a", encoding="utf-8"):  # como o >> do cmd: aberto sem permitir renomear
        _gravar(log, ["01 instagram: publicado L"])
    assert "01 instagram: publicado L" in log.read_text("utf-8")


def test_saida_e_o_log(tmp_path):
    log = tmp_path / "publicar.log"
    outro = tmp_path / "outro.log"
    with open(log, "a", encoding="utf-8") as mesmo, open(outro, "a", encoding="utf-8") as diferente:
        assert saida_e_o_log(log, mesmo)
        assert not saida_e_o_log(log, diferente)
    assert not saida_e_o_log(log, io.StringIO())  # sem fileno (terminal capturado nos testes)
    assert not saida_e_o_log(tmp_path / "nao-existe.log", io.StringIO())


def test_tarefa_antiga_escreve_so_pela_saida(tmp_path):
    log = tmp_path / "publicar.log"
    with open(log, "a", encoding="utf-8") as saida_do_cmd:
        with registro.registro(log, saida=saida_do_cmd) as (logger, antiga):
            logger.info("01 youtube: privado L")
    assert antiga is True
    assert log.read_text("utf-8").count("01 youtube: privado L") == 1


def test_registro_nao_acumula_manipuladores(tmp_path):
    log = tmp_path / "publicar.log"
    for _ in range(3):
        _gravar(log, ["uma linha"])
    assert log.read_text("utf-8").count("uma linha") == 3
    import logging
    assert not any(isinstance(h, RotacaoTolerante) for h in logging.getLogger(registro.NOME).handlers)


def test_log_que_nao_abre_vai_para_a_saida(tmp_path):
    bloqueio = tmp_path / "logs"
    bloqueio.write_text("um arquivo no lugar da pasta", "utf-8")
    saida = io.StringIO()
    with registro.registro(bloqueio / "publicar.log", saida=saida) as (logger, antiga):
        logger.info("01 youtube: privado L")
    assert antiga is False and saida.getvalue().endswith(" 01 youtube: privado L\n")
