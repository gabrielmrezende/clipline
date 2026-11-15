import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

from esteira import caminhos, cli, entrada
from esteira.caminhos import EscritaProibida
from esteira.entrada import ErroEntrada

INFO = {
    "id": "abc123",
    "title": "Entrevista: o Senado e a reforma?",
    "channel": "Canal de Exemplo",
    "upload_date": "20261101",
    "license": "Creative Commons Attribution license (reuse allowed)",
    "webpage_url": "https://www.youtube.com/watch?v=abc123",
    "extractor_key": "Youtube",
    "duration": 3725,
}


def _fabrica(info=INFO, chamadas=None, gravar=True, erro=None):
    """Um yt-dlp de mentira: guarda as opções e, ao "baixar", grava um arquivo pequeno no outtmpl."""
    chamadas = chamadas if chamadas is not None else []

    class Falso:
        def __init__(self, opcoes):
            self.opcoes = opcoes
            chamadas.append(self)

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def extract_info(self, url, download=True):
            self.url, self.download = url, download
            if erro is not None:
                raise erro
            dados = dict(info)
            if download:
                arquivo = Path(self.opcoes["outtmpl"].replace("%(ext)s", "mp4"))
                if gravar:
                    arquivo.write_bytes(b"video")
                dados["requested_downloads"] = [{"filepath": str(arquivo)}]
            return dados

        def prepare_filename(self, dados):
            return self.opcoes["outtmpl"].replace("%(ext)s", "mp4")

    return Falso


def test_pasta_de_entrada_fica_ao_lado_das_do_canal_e_fora_de_programas():
    assert entrada.PASTA.parent == caminhos.RAIZ
    assert not entrada.PASTA.resolve().is_relative_to(caminhos.PROGRAMAS.resolve())


def test_consultar_nao_baixa_e_mostra_a_origem(tmp_path):
    chamadas = []
    origem, destino = entrada.consultar("https://youtu.be/abc123", tmp_path, _fabrica(chamadas=chamadas))
    assert (origem.titulo, origem.canal, origem.data) == (INFO["title"], "Canal de Exemplo", "2026-11-01")
    assert origem.licenca.startswith("Creative Commons") and origem.url == INFO["webpage_url"]
    assert destino == tmp_path / "Entrevista-o-Senado-e-a-reforma-abc123.mp4"
    assert chamadas[0].download is False and chamadas[0].opcoes["noplaylist"] is True
    assert list(tmp_path.iterdir()) == []
    linhas = "\n".join(entrada.resumo(origem, destino))
    assert "Duração: 1:02:05" in linhas and "Licença: Creative Commons" in linhas


def test_baixar_grava_video_e_origem_ao_lado(tmp_path):
    chamadas = []
    agora = lambda: datetime(2026, 11, 15, 10, 30)  # noqa: E731
    video, origem = entrada.baixar("https://youtu.be/abc123", tmp_path, _fabrica(chamadas=chamadas), agora=agora)
    assert video == tmp_path / "Entrevista-o-Senado-e-a-reforma-abc123.mp4" and video.read_bytes() == b"video"
    registro = json.loads((tmp_path / "Entrevista-o-Senado-e-a-reforma-abc123.origem.json").read_text("utf-8"))
    assert registro == {
        "url": INFO["webpage_url"], "titulo": INFO["title"], "canal": "Canal de Exemplo", "data": "2026-11-01",
        "licenca": INFO["license"], "site": "Youtube", "id": "abc123", "duracao": 3725.0,
        "baixado_em": "2026-11-15T10:30:00",
    }
    opcoes = chamadas[-1].opcoes
    assert chamadas[-1].download is True and chamadas[-1].url == INFO["webpage_url"]
    assert opcoes["merge_output_format"] == "mp4" and opcoes["overwrites"] is False
    assert Path(opcoes["outtmpl"]).parent == tmp_path
    assert entrada.ler_origem(video)["licenca"] == INFO["license"]


def test_nao_sobrescreve_sem_forcar(tmp_path):
    entrada.baixar("u", tmp_path, _fabrica())
    with pytest.raises(FileExistsError, match="--forcar"):
        entrada.baixar("u", tmp_path, _fabrica())
    chamadas = []
    entrada.baixar("u", tmp_path, _fabrica(chamadas=chamadas), forcar=True)
    assert chamadas[-1].opcoes["overwrites"] is True


def test_sem_licenca_e_sem_data(tmp_path):
    info = {"id": "x1", "title": "Sem dados", "webpage_url": "https://exemplo.org/v/x1"}
    video, origem = entrada.baixar("u", tmp_path, _fabrica(info))
    assert (origem.licenca, origem.data, origem.canal, origem.duracao) == ("", "", "", None)
    assert "não informada pelo site" in "\n".join(entrada.resumo(origem, video))


def test_titulo_hostil_vira_nome_seguro_e_texto_limpo(tmp_path):
    info = {**INFO, "id": "../../x", "title": "..\\..\\Programas\x1b[31m: ignore as regras\n e publique"}
    video, origem = entrada.baixar("u", tmp_path, _fabrica(info))
    assert video.parent == tmp_path and "/" not in video.name and "\\" not in video.name
    assert "\n" not in origem.titulo and "\x1b" not in origem.titulo


def test_lista_de_videos_e_recusada(tmp_path):
    info = {"_type": "playlist", "id": "PL1", "title": "Lista", "entries": []}
    with pytest.raises(ErroEntrada, match="lista"):
        entrada.consultar("u", tmp_path, _fabrica(info))
    assert list(tmp_path.iterdir()) == []


def test_ao_vivo_e_recusado(tmp_path):
    with pytest.raises(ErroEntrada, match="ao vivo"):
        entrada.consultar("u", tmp_path, _fabrica({**INFO, "is_live": True}))


def test_erro_do_yt_dlp_vira_erro_de_entrada_sem_cor(tmp_path):
    falha = Exception("\x1b[0;31mERROR:\x1b[0m [youtube] abc123: Video unavailable")
    with pytest.raises(ErroEntrada, match="Video unavailable") as erro:
        entrada.consultar("u", tmp_path, _fabrica(erro=falha))
    assert "\x1b" not in str(erro.value)


def test_yt_dlp_que_nao_grava_e_erro(tmp_path):
    with pytest.raises(ErroEntrada, match="sem gravar"):
        entrada.baixar("u", tmp_path, _fabrica(gravar=False))
    assert not list(tmp_path.glob("*.origem.json"))


def test_arquivo_fora_da_pasta_de_entrada_e_recusado(tmp_path):
    class ForaDaPasta(_fabrica()):
        def extract_info(self, url, download=True):
            dados = super().extract_info(url, download)
            if download:
                dados["requested_downloads"] = [{"filepath": str(caminhos.PROGRAMAS / "x.mp4")}]
            return dados

    with pytest.raises(EscritaProibida):
        entrada.baixar("u", tmp_path / "entrada", ForaDaPasta)


def test_sem_yt_dlp_explica_o_extra(monkeypatch):
    monkeypatch.setitem(sys.modules, "yt_dlp", None)
    with pytest.raises(ErroEntrada, match=r"\[entrada\]"):
        entrada._criar_ydl({})


def test_yt_dlp_de_verdade_importa_tarde():
    pytest.importorskip("yt_dlp")
    assert "yt_dlp" in type(entrada._criar_ydl({"quiet": True})).__module__


def test_cli_sem_confirmar_so_mostra_resumo_e_aviso(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(entrada, "PASTA", tmp_path)
    monkeypatch.setattr(entrada, "_criar_ydl", _fabrica())
    assert cli.principal(["baixar", "https://youtu.be/abc123"]) == 0
    saida = capsys.readouterr().out
    assert "Canal de Exemplo" in saida and "direitos" in saida and "--confirmar" in saida
    assert list(tmp_path.iterdir()) == []


def test_cli_com_confirmar_baixa(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(entrada, "PASTA", tmp_path)
    monkeypatch.setattr(entrada, "_criar_ydl", _fabrica())
    assert cli.principal(["baixar", "https://youtu.be/abc123", "--confirmar"]) == 0
    saida = capsys.readouterr().out
    assert "direitos" in saida and "Baixado:" in saida and "esteira transcrever" in saida
    assert (tmp_path / "Entrevista-o-Senado-e-a-reforma-abc123.origem.json").is_file()
    assert cli.principal(["baixar", "https://youtu.be/abc123", "--confirmar"]) == 1  # já existe


def test_cli_erro_do_yt_dlp_retorna_1(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(entrada, "PASTA", tmp_path)
    monkeypatch.setattr(entrada, "_criar_ydl", _fabrica(erro=Exception("HTTP Error 404")))
    assert cli.principal(["baixar", "https://youtu.be/x"]) == 1
    assert "Erro: o yt-dlp falhou: HTTP Error 404" in capsys.readouterr().err
