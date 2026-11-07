import json
import secrets
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

from esteira.publicar import credenciais
from esteira.publicar.credenciais import PORTA, REDIRECIONAMENTO, ErroConexao, esperar_codigo, pedir_segredo
from esteira.publicar.http import ErroRede, Resultado, json_de, pedir
from esteira.publicar.post import Textos

REDE = "youtube"
AUTORIZAR = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN = "https://oauth2.googleapis.com/token"
ENVIO = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status"
ESCOPO = "https://www.googleapis.com/auth/youtube.upload"
FORM = {"Content-Type": "application/x-www-form-urlencoded"}


def _token(campos: dict) -> dict:
    try:
        _, _, corpo = pedir("POST", TOKEN, urllib.parse.urlencode(campos).encode(), FORM)
    except ErroRede as erro:
        if erro.codigo in (400, 401):
            raise ErroConexao("token recusado pelo Google", REDE) from None
        raise
    return json_de(corpo)


def _acesso() -> str:
    campos = {c: credenciais.ler(REDE, c) for c in ("client_id", "client_secret", "refresh_token")}
    if not all(campos.values()):
        raise ErroConexao("conta não conectada", REDE)
    dados = _token({**campos, "grant_type": "refresh_token"})
    if not dados.get("access_token"):
        raise ErroConexao("o Google não devolveu token", REDE)
    return dados["access_token"]


class YouTube:
    def publicar(self, video: Path, textos: Textos, data: datetime, modo: str) -> Resultado:
        acesso = _acesso()
        status = {"privacyStatus": "private", "selfDeclaredMadeForKids": False}
        if modo == "agendado" and data <= datetime.now(timezone.utc):
            status["privacyStatus"] = "public"  # passou da hora: publica já
        elif modo == "agendado":
            status["publishAt"] = data.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        meta = {
            "snippet": {"title": textos.youtube_titulo, "description": textos.youtube_descricao, "categoryId": "22"},
            "status": status,
        }
        conteudo = Path(video).read_bytes()
        try:
            _, cabecalhos, _ = pedir("POST", ENVIO, json.dumps(meta).encode(), {
                "Authorization": f"Bearer {acesso}",
                "Content-Type": "application/json; charset=UTF-8",
                "X-Upload-Content-Type": "video/mp4",
                "X-Upload-Content-Length": str(len(conteudo)),
            })
            sessao = cabecalhos.get("Location") or cabecalhos.get("location")
            if not sessao:
                raise ErroRede("youtube: resposta sem endereço de envio", True)
            _, _, corpo = pedir("PUT", sessao, conteudo, {"Authorization": f"Bearer {acesso}", "Content-Type": "video/mp4"})
        except ErroRede as erro:
            if erro.codigo == 401:
                raise ErroConexao("acesso negado", REDE) from None
            raise ErroRede(f"youtube: {erro}", erro.temporario, erro.codigo) from None
        id_video = json_de(corpo).get("id")
        if not id_video:
            raise ErroRede("youtube: envio sem id do vídeo", False)
        estado = "publicado" if modo == "agendado" else "privado"
        return Resultado(estado, f"https://youtube.com/shorts/{id_video}", id_video)


def conectar() -> None:
    cliente = pedir_segredo("Client ID do YouTube")
    segredo = pedir_segredo("Client secret do YouTube")
    credenciais.gravar(REDE, "client_id", cliente)
    credenciais.gravar(REDE, "client_secret", segredo)
    estado = secrets.token_urlsafe(16)
    url = AUTORIZAR + "?" + urllib.parse.urlencode({
        "client_id": cliente, "redirect_uri": REDIRECIONAMENTO, "response_type": "code", "scope": ESCOPO,
        "access_type": "offline", "prompt": "consent", "state": estado,
    })
    codigo = esperar_codigo(PORTA, estado, url)
    dados = _token({
        "code": codigo, "client_id": cliente, "client_secret": segredo,
        "redirect_uri": REDIRECIONAMENTO, "grant_type": "authorization_code",
    })
    if not dados.get("refresh_token"):
        raise ErroConexao("o Google não devolveu refresh token; tente de novo", REDE)
    credenciais.gravar(REDE, "refresh_token", dados["refresh_token"])
