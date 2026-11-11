import time
import urllib.parse
from datetime import datetime
from pathlib import Path

from esteira.publicar import credenciais
from esteira.publicar.credenciais import ErroConexao, pedir_segredo
from esteira.publicar.http import ErroIncerto, ErroRede, Resultado, json_de, pedir
from esteira.publicar.post import Textos

REDE = "instagram"
VERSAO_GRAPH = "v21.0"
BASE = "https://graph.instagram.com"
UM_DIA = 86400
ESPERA = 10
CONSULTAS = 60  # 10 min
FORM = {"Content-Type": "application/x-www-form-urlencoded"}


def _chamar(metodo: str, url: str, campos: dict | None = None, cabecalhos: dict | None = None, corpo: bytes | None = None) -> dict:
    if campos is not None:
        corpo, cabecalhos = urllib.parse.urlencode(campos).encode(), FORM
    try:
        _, _, resposta = pedir(metodo, url, corpo, cabecalhos)
    except ErroRede as erro:
        detalhe = erro.dados.get("error")
        if isinstance(detalhe, dict) and detalhe.get("code") == 190:
            raise ErroConexao("token vencido ou revogado", REDE) from None
        raise ErroRede(f"instagram: {erro}", erro.temporario, erro.codigo) from None
    return json_de(resposta)


def _token() -> tuple[str, str]:
    token = credenciais.ler(REDE, "token")
    usuario = credenciais.ler(REDE, "user_id")
    if not token or not usuario:
        raise ErroConexao("conta não conectada", REDE)
    renovado = float(credenciais.ler(REDE, "renovado_em") or 0)
    if time.time() - renovado > UM_DIA:
        consulta = urllib.parse.urlencode({"grant_type": "ig_refresh_token", "access_token": token})
        novo = _chamar("GET", f"{BASE}/refresh_access_token?{consulta}").get("access_token")
        if not novo:
            raise ErroConexao("a Meta não renovou o token", REDE)
        token = novo
        credenciais.gravar(REDE, "token", token)
        credenciais.gravar(REDE, "renovado_em", str(time.time()))
    return token, usuario


class Instagram:
    def __init__(self, esperar=time.sleep):
        self.esperar = esperar

    def publicar(self, video: Path, textos: Textos, data: datetime, modo: str, ia: bool = False) -> Resultado:
        # `ia` sem efeito aqui: o aviso vai no texto (o painel e o agendar exigem). Não confirmei um campo
        # equivalente na API de conteúdo do Instagram; ver docs/auditoria.
        token, usuario = _token()
        base = f"{BASE}/{VERSAO_GRAPH}"
        conteiner = _chamar("POST", f"{base}/{usuario}/media", {
            "media_type": "REELS", "upload_type": "resumable", "caption": textos.instagram, "access_token": token,
        })
        if not conteiner.get("id") or not conteiner.get("uri"):
            raise ErroRede("instagram: resposta sem contêiner de envio", False)
        conteudo = Path(video).read_bytes()
        _chamar("POST", conteiner["uri"], cabecalhos={
            "Authorization": f"OAuth {token}", "offset": "0", "file_size": str(len(conteudo)),
        }, corpo=conteudo)
        consulta = urllib.parse.urlencode({"fields": "status_code", "access_token": token})
        for _ in range(CONSULTAS):
            estado = _chamar("GET", f"{base}/{conteiner['id']}?{consulta}").get("status_code")
            if estado == "FINISHED":
                break
            if estado in ("ERROR", "EXPIRED"):
                raise ErroRede(f"instagram: o Instagram recusou o vídeo ({estado})", False)
            self.esperar(ESPERA)
        else:
            raise ErroRede("instagram: tempo de processamento esgotado (10 min)", False)
        try:
            midia = _chamar("POST", f"{base}/{usuario}/media_publish", {"creation_id": conteiner["id"], "access_token": token})
        except ErroRede as erro:
            raise ErroIncerto(f"instagram: a publicação pode ter saído ({erro})") from None
        id_midia = midia.get("id")
        if not id_midia:
            raise ErroIncerto("instagram: publicação sem id; confira no app")
        campos = urllib.parse.urlencode({"fields": "permalink", "access_token": token})
        try:
            link = _chamar("GET", f"{base}/{id_midia}?{campos}").get("permalink", "")
        except ErroRede:
            link = ""  # o Reels já saiu; só o link falhou
        return Resultado("publicado", link, id_midia)


def conectar() -> None:
    token = pedir_segredo("Token do Instagram (painel da Meta, Gerar token)")
    consulta = urllib.parse.urlencode({"fields": "user_id,username", "access_token": token})
    dados = _chamar("GET", f"{BASE}/{VERSAO_GRAPH}/me?{consulta}")
    if not dados.get("user_id"):
        raise ErroConexao("token não reconhecido pela Meta", REDE)
    credenciais.gravar(REDE, "token", token)
    credenciais.gravar(REDE, "user_id", str(dados["user_id"]))
    credenciais.gravar(REDE, "renovado_em", str(time.time()))
    print(f"Instagram conectado: @{dados.get('username', '?')}")
