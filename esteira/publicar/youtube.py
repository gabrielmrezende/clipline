import json
import re
import secrets
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

from esteira import config
from esteira.publicar import credenciais
from esteira.publicar.credenciais import PORTA, REDIRECIONAMENTO, ErroConexao, esperar_codigo, pedir_segredo, pkce
from esteira.publicar.http import ErroIncerto, ErroRede, Resultado, cabecalho, json_de, pedir
from esteira.publicar.post import TIPOS_MINIATURA, ExtrasYouTube, Textos

REDE = "youtube"
AUTORIZAR = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN = "https://oauth2.googleapis.com/token"
ENVIO = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status"
VIDEOS = "https://www.googleapis.com/youtube/v3/videos"
PLAYLIST = "https://www.googleapis.com/youtube/v3/playlistItems?part=snippet"
MINIATURA = "https://www.googleapis.com/upload/youtube/v3/thumbnails/set"
ESCOPO = "https://www.googleapis.com/auth/youtube.upload"
# Pôr o vídeo numa playlist pede mais que o envio (playlistItems.insert não aceita o youtube.upload).
ESCOPO_PLAYLIST = "https://www.googleapis.com/auth/youtube.force-ssl"
FORM = {"Content-Type": "application/x-www-form-urlencoded"}

# Envio retomável: o vídeo vai em partes, lidas do disco uma a uma. Cada parte (menos a última) tem de ser
# múltipla de 256 KiB. Depois de uma falha, o YouTube diz até que byte recebeu e o envio segue dali.
QUANTUM = 256 * 1024
PARTE = 32 * QUANTUM  # 8 MiB
RETOMAVEIS = (500, 502, 503, 504)
FALHAS_SEGUIDAS = 5
ESPERA_FALHA = 2  # segundos; dobra a cada falha seguida (2, 4, 8, 16, 32)
ESPERA_PROCESSAMENTO = 10
CONSULTAS_PROCESSAMENTO = 30  # 5 min


def _token(campos: dict, pedir_http=pedir) -> dict:
    try:
        _, _, corpo = pedir_http("POST", TOKEN, urllib.parse.urlencode(campos).encode(), FORM)
    except ErroRede as erro:
        if erro.codigo in (400, 401):
            raise ErroConexao("token recusado pelo Google", REDE) from None
        raise
    return json_de(corpo)


def _acesso(pedir_http=pedir) -> str:
    campos = {c: credenciais.ler(REDE, c) for c in ("client_id", "client_secret", "refresh_token")}
    if not all(campos.values()):
        raise ErroConexao("conta não conectada", REDE)
    dados = _token({**campos, "grant_type": "refresh_token"}, pedir_http)
    if not dados.get("access_token"):
        raise ErroConexao("o Google não devolveu token", REDE)
    return dados["access_token"]


def ultimo_byte(cabecalhos: dict) -> int:
    """O último byte que o YouTube confirmou (cabeçalho Range: bytes=0-N); -1 se nada chegou."""
    achado = re.fullmatch(r"\s*bytes=0-(\d+)\s*", cabecalho(cabecalhos, "Range"))
    return int(achado.group(1)) if achado else -1


class YouTube:
    def __init__(self, pedir_http=pedir, esperar=time.sleep, parte: int = PARTE):
        if parte <= 0 or parte % QUANTUM:
            raise ValueError(f"parte de envio precisa ser múltipla de {QUANTUM} bytes")
        self.pedir = pedir_http
        self.esperar = esperar
        self.parte = parte

    def publicar(self, video: Path, textos: Textos, data: datetime, modo: str, ia: bool = False,
                 extras: ExtrasYouTube | None = None) -> Resultado:
        extras = extras or ExtrasYouTube()
        acesso = _acesso(self.pedir)
        status = {"privacyStatus": "private", "selfDeclaredMadeForKids": False}
        if ia:  # rótulo de conteúdo alterado ou sintético (status.containsSyntheticMedia, desde 30/10/2024)
            status["containsSyntheticMedia"] = True
        if modo == "agendado" and data <= datetime.now(timezone.utc):
            status["privacyStatus"] = "public"  # passou da hora: publica já
        elif modo == "agendado":
            status["publishAt"] = data.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        snippet = {
            "title": textos.youtube_titulo, "description": textos.youtube_descricao,
            "categoryId": config.atual().youtube_categoria,
        }
        if extras.tags:
            snippet["tags"] = list(extras.tags)
        meta = {"snippet": snippet, "status": status}
        total = Path(video).stat().st_size
        if not total:
            raise ErroRede("youtube: vídeo vazio", False)
        try:
            _, cabecalhos, _ = self.pedir("POST", ENVIO, json.dumps(meta).encode(), {
                "Authorization": f"Bearer {acesso}",
                "Content-Type": "application/json; charset=UTF-8",
                "X-Upload-Content-Type": "video/mp4",
                "X-Upload-Content-Length": str(total),
            })
            sessao = cabecalho(cabecalhos, "Location")
            if not sessao:
                raise ErroRede("youtube: resposta sem endereço de envio", True)
            corpo = self._enviar(sessao, Path(video), total, acesso)
        except ErroRede as erro:
            if erro.codigo == 401:
                raise ErroConexao("acesso negado", REDE) from None
            raise ErroRede(f"youtube: {erro}", erro.temporario, erro.codigo) from None
        id_video = json_de(corpo).get("id")
        if not id_video:
            raise ErroRede("youtube: envio sem id do vídeo", False)
        estado = "publicado" if modo == "agendado" else "privado"
        avisos = self._depois_do_envio(id_video, extras, acesso)
        return Resultado(estado, f"https://youtube.com/shorts/{id_video}", id_video, "; ".join(avisos))

    def _enviar(self, sessao: str, video: Path, total: int, acesso: str) -> bytes:
        """Manda o vídeo em partes e devolve o corpo da resposta final (o recurso do vídeo).

        Falha de conexão ou 500/502/503/504: espera, pergunta ao YouTube até onde chegou e segue dali. Depois de
        FALHAS_SEGUIDAS sem avanço, desiste: se a última parte já tinha ido, o vídeo pode ter sido criado
        (ErroIncerto, para conferir no Studio e não duplicar); senão, erro temporário (tenta de novo na próxima
        rodada, do começo)."""
        autorizacao = {"Authorization": f"Bearer {acesso}"}
        proximo, falhas, consultar, final_enviado = 0, 0, False, False
        with open(video, "rb") as arquivo:
            while True:
                try:
                    if consultar:  # depois de uma falha: até onde o YouTube recebeu?
                        resposta = self.pedir("PUT", sessao, b"", {**autorizacao, "Content-Range": f"bytes */{total}"},
                                              aceitar=(308,))
                    else:
                        arquivo.seek(proximo)
                        pedaco = arquivo.read(self.parte)
                        fim = proximo + len(pedaco) - 1
                        final_enviado = final_enviado or fim == total - 1
                        faixa = f"bytes {proximo}-{fim}/{total}"
                        resposta = self.pedir("PUT", sessao, pedaco, {
                            **autorizacao, "Content-Type": "video/mp4", "Content-Range": faixa,
                        }, aceitar=(308,))
                except ErroRede as erro:
                    if erro.codigo is not None and erro.codigo not in RETOMAVEIS:
                        raise self._desistir(erro, final_enviado) from None
                    motivo = erro
                else:
                    codigo, cabecalhos, corpo = resposta
                    if codigo in (200, 201):
                        return corpo
                    confirmado = ultimo_byte(cabecalhos) + 1
                    avancou = confirmado > proximo
                    if avancou:
                        falhas = 0
                    proximo = confirmado
                    if proximo < total and (consultar or avancou):
                        consultar = False  # segue mandando do byte seguinte ao confirmado
                        continue
                    motivo = ErroRede("o YouTube não confirmou a parte enviada", True)
                # falha: exceção retomável, parte sem avanço ou tudo enviado sem a resposta final
                if falhas >= FALHAS_SEGUIDAS:
                    raise self._desistir(motivo, final_enviado) from None
                falhas += 1
                consultar = True
                self.esperar(ESPERA_FALHA * 2 ** (falhas - 1))

    @staticmethod
    def _desistir(erro: ErroRede, final_enviado: bool) -> Exception:
        if erro.codigo == 401:
            return erro
        if final_enviado:
            return ErroIncerto(f"youtube: o vídeo foi enviado inteiro, mas o YouTube não confirmou ({erro}); "
                               "confira no Studio antes de enviar de novo")
        if erro.codigo == 404:
            return ErroRede("a sessão de envio expirou", True, 404)
        return erro

    def _depois_do_envio(self, id_video: str, extras: ExtrasYouTube, acesso: str) -> list[str]:
        """Playlist e miniatura. O vídeo já subiu: uma falha aqui vira aviso, nunca erro (não duplica o envio)."""
        avisos = []
        autorizacao = {"Authorization": f"Bearer {acesso}"}
        if extras.playlist:
            recurso = {"kind": "youtube#video", "videoId": id_video}
            corpo = {"snippet": {"playlistId": extras.playlist, "resourceId": recurso}}
            try:
                self.pedir("POST", PLAYLIST, json.dumps(corpo).encode(),
                           {**autorizacao, "Content-Type": "application/json; charset=UTF-8"})
            except ErroRede as erro:
                dica = "; reconecte com publicar conectar youtube --playlist" if erro.codigo == 403 else ""
                avisos.append(f"playlist não aplicada ({erro}){dica}")
        if extras.miniatura is not None:
            processado = self._esperar_processamento(id_video, autorizacao)
            try:
                imagem = extras.miniatura.read_bytes()
                tipo = TIPOS_MINIATURA.get(extras.miniatura.suffix.lower(), "application/octet-stream")
                consulta = urllib.parse.urlencode({"videoId": id_video, "uploadType": "media"})
                self.pedir("POST", f"{MINIATURA}?{consulta}", imagem, {**autorizacao, "Content-Type": tipo})
            except (ErroRede, OSError) as erro:
                avisos.append(f"miniatura não aplicada ({erro})")
            else:
                if not processado:
                    avisos.append("miniatura enviada antes do fim do processamento: confira no Studio se ela ficou")
        return avisos

    def _esperar_processamento(self, id_video: str, autorizacao: dict) -> bool:
        """Em Shorts, a miniatura só pega depois que o YouTube termina de processar o vídeo."""
        consulta = urllib.parse.urlencode({"part": "processingDetails", "id": id_video})
        for vez in range(CONSULTAS_PROCESSAMENTO):
            if vez:
                self.esperar(ESPERA_PROCESSAMENTO)
            try:
                _, _, corpo = self.pedir("GET", f"{VIDEOS}?{consulta}", None, autorizacao)
            except ErroRede:
                return False  # sem permissão de leitura (conta conectada só com o envio), por exemplo
            itens = json_de(corpo).get("items") or [{}]
            situacao = ((itens[0] or {}).get("processingDetails") or {}).get("processingStatus")
            if situacao == "succeeded":
                return True
            if situacao in ("failed", "terminated", None):
                return False
        return False


def conectar(playlist: bool = False) -> None:
    """`playlist`: pede também a permissão de gerenciar a conta, que pôr o vídeo numa playlist exige."""
    cliente = pedir_segredo("Client ID do YouTube")
    segredo = pedir_segredo("Client secret do YouTube")
    credenciais.gravar(REDE, "client_id", cliente)
    credenciais.gravar(REDE, "client_secret", segredo)
    estado = secrets.token_urlsafe(16)
    verificador, desafio = pkce()
    url = AUTORIZAR + "?" + urllib.parse.urlencode({
        "client_id": cliente, "redirect_uri": REDIRECIONAMENTO, "response_type": "code",
        "scope": f"{ESCOPO} {ESCOPO_PLAYLIST}" if playlist else ESCOPO,
        "access_type": "offline", "prompt": "consent", "state": estado,
        "code_challenge": desafio, "code_challenge_method": "S256",
    })
    codigo = esperar_codigo(PORTA, estado, url)
    dados = _token({
        "code": codigo, "client_id": cliente, "client_secret": segredo,
        "redirect_uri": REDIRECIONAMENTO, "grant_type": "authorization_code", "code_verifier": verificador,
    })
    if not dados.get("refresh_token"):
        raise ErroConexao("o Google não devolveu refresh token; tente de novo", REDE)
    credenciais.gravar(REDE, "refresh_token", dados["refresh_token"])
