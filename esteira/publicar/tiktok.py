import json
import secrets
import time
import urllib.parse
from datetime import datetime
from pathlib import Path

from esteira import config
from esteira.publicar import credenciais
from esteira.publicar.credenciais import PORTA, REDIRECIONAMENTO, ErroConexao, esperar_codigo, pedir_segredo
from esteira.publicar.http import ErroIncerto, ErroRede, Resultado, json_de, pedir
from esteira.publicar.post import Textos

REDE = "tiktok"
BASE = "https://open.tiktokapis.com"
AUTORIZAR = "https://www.tiktok.com/v2/auth/authorize/"
ESCOPO = "user.info.basic,video.upload,video.publish"
PERFIL = "https://www.tiktok.com/@tudoepoliticabr"
PARTE = 10 * 1024 * 1024
LIMITE_UMA_PARTE = 64 * 1024 * 1024
ESPERA = 10
CONSULTAS = 60
FORM = {"Content-Type": "application/x-www-form-urlencoded"}


def partes(tamanho: int) -> list[tuple[int, int]]:
    """Intervalos (início, fim) inclusivos; a última parte leva o resto."""
    if tamanho <= LIMITE_UMA_PARTE:
        return [(0, tamanho - 1)]
    total = max(1, tamanho // PARTE)
    lista = [(i * PARTE, (i + 1) * PARTE - 1) for i in range(total)]
    lista[-1] = (lista[-1][0], tamanho - 1)
    return lista


def _token(campos: dict) -> dict:
    try:
        _, _, corpo = pedir("POST", f"{BASE}/v2/oauth/token/", urllib.parse.urlencode(campos).encode(), FORM)
    except ErroRede as erro:
        if erro.codigo in (400, 401):
            raise ErroConexao("token recusado pelo TikTok", REDE) from None
        raise
    dados = json_de(corpo)
    if not dados.get("access_token"):
        raise ErroConexao("o TikTok não devolveu token", REDE)
    return dados


def _acesso() -> str:
    chave, segredo, renovacao = (credenciais.ler(REDE, c) for c in ("client_key", "client_secret", "refresh_token"))
    if not (chave and segredo and renovacao):
        raise ErroConexao("conta não conectada", REDE)
    dados = _token({"client_key": chave, "client_secret": segredo, "grant_type": "refresh_token", "refresh_token": renovacao})
    if dados.get("refresh_token"):
        credenciais.gravar(REDE, "refresh_token", dados["refresh_token"])
    return dados["access_token"]


def _api(acesso: str, caminho: str, corpo: dict) -> dict:
    try:
        _, _, resposta = pedir("POST", BASE + caminho, json.dumps(corpo).encode(), {
            "Authorization": f"Bearer {acesso}", "Content-Type": "application/json; charset=UTF-8",
        })
    except ErroRede as erro:
        if erro.codigo == 401:
            raise ErroConexao("acesso negado", REDE) from None
        raise ErroRede(f"tiktok: {erro}", erro.temporario, erro.codigo) from None
    dados = json_de(resposta)
    codigo = (dados.get("error") or {}).get("code", "ok")
    if codigo != "ok":
        raise ErroRede(f"tiktok: {codigo}", codigo == "rate_limit_exceeded")
    return dados.get("data") or {}


def _enviar(endereco: str, conteudo: bytes) -> None:
    total = len(conteudo)
    for inicio, fim in partes(total):
        try:
            pedir("PUT", endereco, conteudo[inicio:fim + 1], {
                "Content-Type": "video/mp4", "Content-Range": f"bytes {inicio}-{fim}/{total}",
            })
        except ErroRede as erro:
            raise ErroRede(f"tiktok: envio do vídeo: {erro}", erro.temporario, erro.codigo) from None


class TikTok:
    def __init__(self, esperar=time.sleep):
        self.esperar = esperar

    def publicar(self, video: Path, textos: Textos, data: datetime, modo: str, ia: bool = False) -> Resultado:
        """`ia`: marca o post como gerado por IA (post_info.is_aigc). O rascunho (inbox) não tem esse campo:
        lá o dono liga o rótulo no app."""
        acesso = _acesso()
        conteudo = Path(video).read_bytes()
        lista = partes(len(conteudo))
        origem = {
            "source": "FILE_UPLOAD",
            "video_size": len(conteudo),
            "chunk_size": lista[0][1] - lista[0][0] + 1,
            "total_chunk_count": len(lista),
        }
        if modo == "rascunho":
            inicio = _api(acesso, "/v2/post/publish/inbox/video/init/", {"source_info": origem})
            _enviar(inicio["upload_url"], conteudo)
            return Resultado("rascunho", "", inicio["publish_id"])
        opcoes = _api(acesso, "/v2/post/creator_info/query/", {}).get("privacy_level_options", [])
        if "PUBLIC_TO_EVERYONE" not in opcoes:
            raise ErroRede("tiktok: conta não permite público (o app já passou na auditoria?)", False)
        inicio = _api(acesso, "/v2/post/publish/video/init/", {
            "post_info": {
                "title": textos.tiktok, "privacy_level": "PUBLIC_TO_EVERYONE",
                "disable_comment": False, "disable_duet": False, "disable_stitch": False,
                **({"is_aigc": True} if ia else {}),
            },
            "source_info": origem,
        })
        _enviar(inicio["upload_url"], conteudo)
        for _ in range(CONSULTAS):
            try:
                situacao = _api(acesso, "/v2/post/publish/status/fetch/", {"publish_id": inicio["publish_id"]})
            except ErroRede as erro:
                raise ErroIncerto(f"tiktok: vídeo enviado, status desconhecido ({erro})") from None
            if situacao.get("status") == "PUBLISH_COMPLETE":
                return Resultado("publicado", config.atual().perfil_tiktok or PERFIL, inicio["publish_id"])
            if situacao.get("status") == "FAILED":
                raise ErroRede(f"tiktok: publicação recusada ({situacao.get('fail_reason', '?')})", False)
            self.esperar(ESPERA)
        raise ErroIncerto("tiktok: vídeo enviado, processamento passou de 10 min")


def conectar() -> None:
    chave = pedir_segredo("Client key do TikTok")
    segredo = pedir_segredo("Client secret do TikTok")
    credenciais.gravar(REDE, "client_key", chave)
    credenciais.gravar(REDE, "client_secret", segredo)
    estado = secrets.token_urlsafe(16)
    url = AUTORIZAR + "?" + urllib.parse.urlencode({
        "client_key": chave, "scope": ESCOPO, "response_type": "code",
        "redirect_uri": REDIRECIONAMENTO, "state": estado,
    })
    codigo = esperar_codigo(PORTA, estado, url)
    dados = _token({
        "client_key": chave, "client_secret": segredo, "code": codigo,
        "grant_type": "authorization_code", "redirect_uri": REDIRECIONAMENTO,
    })
    credenciais.gravar(REDE, "refresh_token", dados["refresh_token"])
    credenciais.gravar(REDE, "open_id", dados.get("open_id", ""))
