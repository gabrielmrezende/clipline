"""Envio retomável do YouTube em partes, com um servidor falso que segue o protocolo resumable da Data API.

Também tags, playlist e miniatura vindos do post.md. Nada sai do PC.
"""
import json
import re
from datetime import datetime

import pytest

from esteira.publicar import credenciais, youtube
from esteira.publicar.credenciais import ErroConexao
from esteira.publicar.http import ErroIncerto, ErroRede
from esteira.publicar.post import ExtrasYouTube
from esteira.publicar.youtube import QUANTUM, YouTube, ultimo_byte
from tests.auxiliares_publicar import DATA, FUSO, TEXTOS, Cofre

CHEIO = {"youtube:client_id": "cid", "youtube:client_secret": "csec", "youtube:refresh_token": "rt"}
SESSAO = "https://up/sessao"


class ServidorRetomavel:
    """Faz o papel do Google: token, abertura da sessão, partes com 308 e Range, consulta de status.

    `falhas`: {índice do PUT (0, 1, ...): exceção ou ("parcial", n)} para simular quedas no meio do envio.
    """

    def __init__(self, falhas=None, depois=None):
        self.recebido = bytearray()
        self.falhas = dict(falhas or {})
        self.depois = list(depois or [])  # respostas das chamadas depois do envio (playlist, status, miniatura)
        self.puts = 0
        self.pedidos = []
        self.meta = None
        self.total = None

    def __call__(self, metodo, url, corpo=None, cabecalhos=None, aceitar=()):
        cabecalhos = cabecalhos or {}
        self.pedidos.append((metodo, url, corpo, cabecalhos))
        if url == youtube.TOKEN:
            return 200, {}, json.dumps({"access_token": "SEGREDO-ACESSO"}).encode()
        if url == youtube.ENVIO:
            self.meta = json.loads(corpo)
            self.total = int(cabecalhos["X-Upload-Content-Length"])
            return 200, {"Location": SESSAO}, b""
        if url == SESSAO:
            return self._put(corpo, cabecalhos, aceitar)
        resposta = self.depois.pop(0)
        if isinstance(resposta, Exception):
            raise resposta
        return resposta

    def _confirmado(self):
        return {"Range": f"bytes=0-{len(self.recebido) - 1}"} if self.recebido else {}

    def _put(self, corpo, cabecalhos, aceitar):
        assert 308 in aceitar
        faixa = cabecalhos["Content-Range"]
        if faixa == f"bytes */{self.total}":  # consulta de status
            if len(self.recebido) == self.total:
                return 201, {}, json.dumps({"id": "abc123"}).encode()
            return 308, self._confirmado(), b""
        indice = self.puts
        self.puts += 1
        inicio, fim, total = map(int, re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", faixa).groups())
        assert total == self.total and inicio == len(self.recebido) and fim - inicio + 1 == len(corpo)
        if fim != total - 1:
            assert len(corpo) % QUANTUM == 0  # o protocolo exige partes múltiplas de 256 KiB
        falha = self.falhas.get(indice)
        if isinstance(falha, tuple):  # a conexão caiu depois de parte dos bytes chegar
            self.recebido += corpo[:falha[1]]
            raise ErroRede("falha de conexão: reset", True)
        if isinstance(falha, Exception):
            if getattr(falha, "chegou", False):
                self.recebido += corpo
            raise falha
        self.recebido += corpo
        if len(self.recebido) == total:
            return 201, {}, json.dumps({"id": "abc123"}).encode()
        return 308, self._confirmado(), b""


@pytest.fixture
def cofre(monkeypatch):
    cofre = Cofre(CHEIO)
    monkeypatch.setattr(credenciais, "ler", cofre.ler)
    monkeypatch.setattr(credenciais, "gravar", cofre.gravar)
    return cofre


def _video(tmp_path, tamanho):
    caminho = tmp_path / "Corte 1.mp4"
    caminho.write_bytes(bytes(i % 251 for i in range(tamanho)))
    return caminho


def _youtube(servidor, esperas=None):
    esperar = esperas.append if esperas is not None else (lambda s: None)
    return YouTube(pedir_http=servidor, esperar=esperar, parte=QUANTUM)


def test_envia_em_partes_de_256_kib_sem_ler_o_video_inteiro(tmp_path, cofre, monkeypatch):
    video = _video(tmp_path, 3 * QUANTUM + 1000)
    servidor = ServidorRetomavel()
    lidos = []

    class Leitor:
        """O arquivo de verdade, anotando o tamanho de cada leitura."""

        def __init__(self, caminho, modo):
            self.arquivo = open(caminho, modo)

        def read(self, n=-1):
            lidos.append(n)
            return self.arquivo.read(n)

        def seek(self, posicao):
            return self.arquivo.seek(posicao)

        def __enter__(self):
            return self

        def __exit__(self, *erro):
            self.arquivo.close()

    monkeypatch.setattr(youtube, "open", Leitor, raising=False)
    r = _youtube(servidor).publicar(video, TEXTOS, DATA, "privado")
    assert r.id_rede == "abc123" and r.aviso == ""
    assert bytes(servidor.recebido) == video.read_bytes()
    assert servidor.puts == 4
    assert lidos == [QUANTUM] * 4  # nunca read() sem limite
    faixas = [c["Content-Range"] for m, u, _, c in servidor.pedidos if u == SESSAO]
    assert faixas[0] == f"bytes 0-{QUANTUM - 1}/{3 * QUANTUM + 1000}"
    assert faixas[-1] == f"bytes {3 * QUANTUM}-{3 * QUANTUM + 999}/{3 * QUANTUM + 1000}"


def test_queda_no_meio_retoma_do_ultimo_byte_confirmado(tmp_path, cofre):
    video = _video(tmp_path, 3 * QUANTUM)
    servidor = ServidorRetomavel(falhas={1: ("parcial", 1000)})
    esperas = []
    r = _youtube(servidor, esperas).publicar(video, TEXTOS, DATA, "privado")
    assert r.id_rede == "abc123"
    assert bytes(servidor.recebido) == video.read_bytes()
    faixas = [c["Content-Range"] for m, u, _, c in servidor.pedidos if u == SESSAO]
    total = 3 * QUANTUM
    assert faixas == [
        f"bytes 0-{QUANTUM - 1}/{total}",
        f"bytes {QUANTUM}-{2 * QUANTUM - 1}/{total}",  # caiu depois de 1000 bytes
        f"bytes */{total}",  # pergunta onde parou
        f"bytes {QUANTUM + 1000}-{2 * QUANTUM + 999}/{total}",  # segue do byte seguinte ao confirmado
        f"bytes {2 * QUANTUM + 1000}-{total - 1}/{total}",
    ]
    assert esperas == [2]


def test_503_na_parte_espera_com_recuo_e_segue(tmp_path, cofre):
    video = _video(tmp_path, 2 * QUANTUM)
    servidor = ServidorRetomavel(falhas={0: ErroRede("HTTP 503: sem detalhe", True, 503),
                                         1: ErroRede("HTTP 502: sem detalhe", True, 502)})
    esperas = []
    r = _youtube(servidor, esperas).publicar(video, TEXTOS, DATA, "privado")
    assert r.id_rede == "abc123" and bytes(servidor.recebido) == video.read_bytes()
    assert esperas == [2, 4]


def test_resposta_final_perdida_e_recuperada_pela_consulta(tmp_path, cofre):
    """A última parte chegou e o vídeo foi criado, mas a resposta se perdeu: a consulta devolve o 201."""
    video = _video(tmp_path, QUANTUM)
    queda = ErroRede("falha de conexão: timed out", True)
    queda.chegou = True
    servidor = ServidorRetomavel(falhas={0: queda})
    r = _youtube(servidor).publicar(video, TEXTOS, DATA, "privado")
    assert r.id_rede == "abc123" and servidor.puts == 1  # não mandou o vídeo de novo


def test_desiste_depois_de_muitas_falhas_sem_avanco(tmp_path, cofre):
    video = _video(tmp_path, 2 * QUANTUM)
    queda = ErroRede("falha de conexão: reset", True)
    servidor = ServidorRetomavel(falhas={i: queda for i in range(20)})
    esperas = []
    with pytest.raises(ErroRede, match="youtube: falha de conexão") as erro:
        _youtube(servidor, esperas).publicar(video, TEXTOS, DATA, "privado")
    assert erro.value.temporario  # a fila tenta de novo na próxima rodada
    assert esperas == [2, 4, 8, 16, 32]


def test_falha_depois_da_ultima_parte_e_incerta(tmp_path, cofre):
    """Sem confirmação depois de mandar o último byte, o vídeo pode existir: conferir, não reenviar."""
    video = _video(tmp_path, QUANTUM)
    queda = ErroRede("HTTP 503: sem detalhe", True, 503)
    servidor = ServidorRetomavel(falhas={0: queda})

    def consulta_quebrada(metodo, url, corpo=None, cabecalhos=None, aceitar=()):
        if url == SESSAO and (cabecalhos or {}).get("Content-Range", "").startswith("bytes */"):
            raise ErroRede("falha de conexão: reset", True)
        return servidor(metodo, url, corpo, cabecalhos, aceitar)

    with pytest.raises(ErroIncerto, match="confira no Studio"):
        _youtube(consulta_quebrada).publicar(video, TEXTOS, DATA, "privado")


def test_erro_definitivo_na_parte_nao_insiste(tmp_path, cofre):
    video = _video(tmp_path, 2 * QUANTUM)
    servidor = ServidorRetomavel(falhas={0: ErroRede("HTTP 400: badContent", False, 400)})
    with pytest.raises(ErroRede, match="youtube: HTTP 400") as erro:
        _youtube(servidor).publicar(video, TEXTOS, DATA, "privado")
    assert not erro.value.temporario and servidor.puts == 1


def test_sessao_expirada_recomeca_na_proxima_rodada(tmp_path, cofre):
    video = _video(tmp_path, 2 * QUANTUM)
    servidor = ServidorRetomavel(falhas={0: ErroRede("HTTP 404: sem detalhe", False, 404)})
    with pytest.raises(ErroRede, match="sessão de envio expirou") as erro:
        _youtube(servidor).publicar(video, TEXTOS, DATA, "privado")
    assert erro.value.temporario


def test_401_no_meio_pede_reconexao(tmp_path, cofre):
    video = _video(tmp_path, 2 * QUANTUM)
    servidor = ServidorRetomavel(falhas={1: ErroRede("HTTP 401: sem detalhe", False, 401)})
    with pytest.raises(ErroConexao, match="conectar youtube$"):
        _youtube(servidor).publicar(video, TEXTOS, DATA, "privado")


def test_parte_precisa_ser_multipla_de_256_kib():
    with pytest.raises(ValueError):
        YouTube(parte=1000)


def test_ultimo_byte():
    assert ultimo_byte({"Range": "bytes=0-524287"}) == 524287
    assert ultimo_byte({"range": "bytes=0-9"}) == 9
    assert ultimo_byte({}) == -1


# --- tags, playlist e miniatura ----------------------------------------------------------------------------


def test_tags_vao_no_snippet(tmp_path, cofre):
    servidor = ServidorRetomavel()
    _youtube(servidor).publicar(_video(tmp_path, 10), TEXTOS, DATA, "privado",
                                extras=ExtrasYouTube(tags=("política", "Fórmula 1")))
    assert servidor.meta["snippet"]["tags"] == ["política", "Fórmula 1"]


def test_sem_extras_o_snippet_fica_como_sempre(tmp_path, cofre):
    servidor = ServidorRetomavel()
    _youtube(servidor).publicar(_video(tmp_path, 10), TEXTOS, DATA, "privado")
    assert set(servidor.meta["snippet"]) == {"title", "description", "categoryId"}
    assert [u for _, u, _, _ in servidor.pedidos] == [youtube.TOKEN, youtube.ENVIO, SESSAO]


def test_playlist_depois_do_envio(tmp_path, cofre):
    servidor = ServidorRetomavel(depois=[(200, {}, b"{}")])
    extras = ExtrasYouTube(playlist="PL123")
    r = _youtube(servidor).publicar(_video(tmp_path, 10), TEXTOS, DATA, "privado", extras=extras)
    metodo, url, corpo, cabecalhos = servidor.pedidos[-1]
    assert (metodo, url) == ("POST", youtube.PLAYLIST)
    recurso = {"kind": "youtube#video", "videoId": "abc123"}
    assert json.loads(corpo) == {"snippet": {"playlistId": "PL123", "resourceId": recurso}}
    assert cabecalhos["Authorization"] == "Bearer SEGREDO-ACESSO"
    assert r.estado == "privado" and r.aviso == ""


def test_playlist_sem_permissao_vira_aviso_e_nao_erro(tmp_path, cofre):
    servidor = ServidorRetomavel(depois=[ErroRede("HTTP 403: insufficientPermissions", False, 403)])
    extras = ExtrasYouTube(playlist="PL123")
    r = _youtube(servidor).publicar(_video(tmp_path, 10), TEXTOS, DATA, "privado", extras=extras)
    assert r.id_rede == "abc123"
    assert "playlist não aplicada" in r.aviso and "publicar conectar youtube --playlist" in r.aviso


def test_miniatura_espera_o_processamento(tmp_path, cofre):
    imagem = tmp_path / "miniatura.jpg"
    imagem.write_bytes(b"\xff\xd8JPEG")
    processando = (200, {}, json.dumps({"items": [{"processingDetails": {"processingStatus": "processing"}}]}).encode())
    pronto = (200, {}, json.dumps({"items": [{"processingDetails": {"processingStatus": "succeeded"}}]}).encode())
    servidor = ServidorRetomavel(depois=[processando, pronto, (200, {}, b"{}")])
    esperas = []
    r = _youtube(servidor, esperas).publicar(_video(tmp_path, 10), TEXTOS, DATA, "privado",
                                             extras=ExtrasYouTube(miniatura=imagem))
    assert r.aviso == "" and esperas == [youtube.ESPERA_PROCESSAMENTO]
    consulta, _, miniatura = servidor.pedidos[-3:]
    assert consulta[0] == "GET" and consulta[1].startswith(youtube.VIDEOS + "?part=processingDetails&id=abc123")
    assert miniatura[0] == "POST" and miniatura[1] == youtube.MINIATURA + "?videoId=abc123&uploadType=media"
    assert miniatura[2] == b"\xff\xd8JPEG" and miniatura[3]["Content-Type"] == "image/jpeg"


def test_miniatura_sem_como_saber_do_processamento_avisa(tmp_path, cofre):
    imagem = tmp_path / "miniatura.png"
    imagem.write_bytes(b"PNG")
    servidor = ServidorRetomavel(depois=[ErroRede("HTTP 403: insufficientPermissions", False, 403), (200, {}, b"{}")])
    extras = ExtrasYouTube(miniatura=imagem)
    r = _youtube(servidor).publicar(_video(tmp_path, 10), TEXTOS, DATA, "privado", extras=extras)
    assert servidor.pedidos[-1][3]["Content-Type"] == "image/png"
    assert "confira no Studio" in r.aviso


def test_miniatura_recusada_vira_aviso(tmp_path, cofre):
    imagem = tmp_path / "miniatura.jpg"
    imagem.write_bytes(b"x")
    pronto = (200, {}, json.dumps({"items": [{"processingDetails": {"processingStatus": "succeeded"}}]}).encode())
    servidor = ServidorRetomavel(depois=[pronto, ErroRede("HTTP 403: forbidden", False, 403)])
    extras = ExtrasYouTube(miniatura=imagem)
    r = _youtube(servidor).publicar(_video(tmp_path, 10), TEXTOS, DATA, "privado", extras=extras)
    assert r.estado == "privado" and r.aviso.startswith("miniatura não aplicada")


def test_agendado_continua_com_publish_at(tmp_path, cofre):
    servidor = ServidorRetomavel()
    futura = datetime(2099, 11, 8, 18, 0, tzinfo=FUSO)
    r = _youtube(servidor).publicar(_video(tmp_path, 10), TEXTOS, futura, "agendado")
    assert r.estado == "publicado" and servidor.meta["status"]["publishAt"] == "2099-11-08T21:00:00Z"


def test_conectar_com_playlist_pede_o_escopo_a_mais(monkeypatch):
    urls = []
    monkeypatch.setattr(youtube, "pedir_segredo", lambda rotulo: "valor")
    monkeypatch.setattr(credenciais, "gravar", lambda *a: None)
    monkeypatch.setattr(youtube, "esperar_codigo", lambda porta, estado, url: urls.append(url) or "CODIGO")
    monkeypatch.setattr(youtube, "_token", lambda campos, pedir_http=None: {"refresh_token": "rt"})
    youtube.conectar()
    youtube.conectar(playlist=True)
    from urllib.parse import parse_qs, urlsplit
    escopos = [parse_qs(urlsplit(u).query)["scope"][0] for u in urls]
    assert escopos == [youtube.ESCOPO, f"{youtube.ESCOPO} {youtube.ESCOPO_PLAYLIST}"]
