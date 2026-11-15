"""Entrada por link: baixa um vídeo com o yt-dlp para a pasta de entrada do canal e grava de onde ele veio.

A pasta fica ao lado das outras do canal (`0 - Entrada/`), nunca dentro de `1 - Programas/`, que é só leitura.
Ao lado de cada vídeo vai um `<nome>.origem.json` com o link, o título, o canal, a data e a licença que o site
informa. O yt-dlp é opcional (extra `[entrada]`) e só é importado na hora de baixar.
"""

import json
import re
import unicodedata
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from esteira import caminhos
from esteira.midia import binario

PASTA = caminhos.RAIZ / "0 - Entrada"
SUFIXO_ORIGEM = ".origem.json"
# Até 1080p (o episódio vira 1080x1920; mais que isso só pesa), de preferência H.264 + AAC, que o ffmpeg lê rápido.
FORMATO = "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/bv*[height<=1080]+ba/b[height<=1080]/bv*+ba/b"
LIMITE_TEXTO = 200
LIMITE_NOME = 60
AVISO_DIREITOS = (
    "Atenção: só baixe e corte vídeos sobre os quais você tem direitos (o seu próprio canal, uma autorização por "
    "escrito ou uma licença que permita reutilizar e adaptar). A licença que o site informa fica no .origem.json, "
    "mas não substitui a sua conferência."
)

CriarBaixador = Callable[[dict], object]


class ErroEntrada(Exception):
    pass


@dataclass
class Origem:
    url: str
    titulo: str
    canal: str
    data: str  # AAAA-MM-DD da publicação, ou "" se o site não informa
    licenca: str  # como o site informa; "" se não informa
    site: str
    id: str
    duracao: float | None = None
    baixado_em: str = ""


def _texto(valor: object, limite: int = LIMITE_TEXTO) -> str:
    """Texto de terceiros (título, canal): numa linha, sem caracteres de controle e com tamanho limitado."""
    sem_cor = re.sub(r"\x1b\[[0-9;]*m", "", str(valor or ""))  # as mensagens de erro do yt-dlp vêm coloridas
    limpo = "".join(c for c in " ".join(sem_cor.split()) if c.isprintable())
    return limpo if len(limpo) <= limite else limpo[: limite - 1] + "…"


def _nome_seguro(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]+", "-", sem_acento).strip("-")


def origem_de(info: dict, url: str) -> Origem:
    data = str(info.get("upload_date") or "")
    duracao = info.get("duration")
    return Origem(
        url=_texto(info.get("webpage_url") or url, 500),
        titulo=_texto(info.get("title")),
        canal=_texto(info.get("channel") or info.get("uploader")),
        data=f"{data[:4]}-{data[4:6]}-{data[6:]}" if re.fullmatch(r"\d{8}", data) else "",
        licenca=_texto(info.get("license")),
        site=_texto(info.get("extractor_key") or info.get("extractor"), 60),
        id=_texto(info.get("id"), 60),
        duracao=float(duracao) if isinstance(duracao, (int, float)) and not isinstance(duracao, bool) else None,
    )


def nome_do_video(origem: Origem) -> str:
    """`Titulo-do-video-<id>.mp4`, só com letras, números e hífens: seguro em qualquer sistema de arquivos."""
    base = _nome_seguro(origem.titulo)[:LIMITE_NOME].strip("-") or "video"
    ident = _nome_seguro(origem.id)[:30]
    return f"{base}-{ident}.mp4" if ident else f"{base}.mp4"


def arquivo_de_origem(video: Path) -> Path:
    return Path(video).with_name(Path(video).stem + SUFIXO_ORIGEM)


def ler_origem(video: Path) -> dict | None:
    """O .origem.json ao lado do vídeo, ou None se não houver ou estiver ilegível."""
    try:
        dados = json.loads(arquivo_de_origem(video).read_text("utf-8"))
    except (OSError, ValueError):
        return None
    return dados if isinstance(dados, dict) else None


def resumo(origem: Origem, destino: Path) -> list[str]:
    if origem.duracao is None:
        duracao = "?"
    else:
        horas, resto = divmod(int(origem.duracao), 3600)
        duracao = f"{horas}:{resto // 60:02d}:{resto % 60:02d}" if horas else f"{resto // 60}:{resto % 60:02d}"
    return [
        f"Título: {origem.titulo or '(sem título)'}",
        f"Canal: {origem.canal or '(não informado)'}",
        f"Publicado em: {origem.data or '(não informado)'}",
        f"Duração: {duracao}",
        f"Licença: {origem.licenca or 'não informada pelo site'}",
        f"Link: {origem.url}",
        f"Destino: {destino}",
    ]


def _criar_ydl(opcoes: dict):
    try:
        from yt_dlp import YoutubeDL
    except ImportError:
        raise ErroEntrada(
            'baixar precisa do yt-dlp: rode .venv\\Scripts\\python.exe -m pip install -e ".[entrada]"'
        ) from None
    return YoutubeDL(opcoes)


def _extrair(criar: CriarBaixador, opcoes: dict, url: str, baixar: bool) -> tuple[dict, str | None]:
    """Roda o yt-dlp e devolve as informações e, se baixou, o arquivo gravado."""
    try:
        with criar(opcoes) as ydl:
            info = ydl.extract_info(url, download=baixar)
            if not isinstance(info, dict):
                raise ErroEntrada(f"o yt-dlp não reconheceu o link: {_texto(url)}")
            gravados = info.get("requested_downloads") or []
            arquivo = gravados[0].get("filepath") if gravados and isinstance(gravados[0], dict) else None
            if baixar and not arquivo:
                arquivo = ydl.prepare_filename(info)
    except ErroEntrada:
        raise
    except Exception as erro:  # DownloadError e afins: rede, link privado, site sem suporte
        raise ErroEntrada(f"o yt-dlp falhou: {_texto(erro, 300)}") from None
    if info.get("_type") in ("playlist", "multi_video") or "entries" in info:
        raise ErroEntrada("o link é de uma lista de vídeos: passe o link de um vídeo só")
    if info.get("is_live"):
        raise ErroEntrada("o link é de uma transmissão ao vivo: espere ela terminar")
    return info, arquivo


def consultar(url: str, pasta: Path | None = None, criar: CriarBaixador | None = None) -> tuple[Origem, Path]:
    """Lê título, canal, data e licença sem baixar nada, e diz onde o vídeo ficaria."""
    # extract_flat: um link de lista volta como lista, sem abrir vídeo por vídeo, e é recusado.
    opcoes = {"quiet": True, "no_warnings": True, "noplaylist": True, "skip_download": True,
              "extract_flat": "in_playlist"}
    info, _ = _extrair(criar or _criar_ydl, opcoes, url, baixar=False)
    origem = origem_de(info, url)
    return origem, Path(pasta or PASTA) / nome_do_video(origem)


def baixar(
    url: str,
    pasta: Path | None = None,
    criar: CriarBaixador | None = None,
    forcar: bool = False,
    agora: Callable[[], datetime] = datetime.now,
) -> tuple[Path, Origem]:
    """Baixa o vídeo para a pasta de entrada e grava o .origem.json ao lado. Nada é sobrescrito sem `forcar`."""
    pasta = Path(pasta or PASTA)
    criar = criar or _criar_ydl
    origem, destino = consultar(url, pasta, criar)
    destino = caminhos.garantir_escrita(destino, base_extra=pasta)
    if not forcar and (destino.exists() or arquivo_de_origem(destino).exists()):
        raise FileExistsError(f"Vídeo já baixado: {destino} (use --forcar para baixar de novo)")
    destino.parent.mkdir(parents=True, exist_ok=True)
    opcoes = {
        "outtmpl": str(destino.with_suffix("")).replace("%", "%%") + ".%(ext)s",  # % na pasta não vira campo
        "format": FORMATO,
        "merge_output_format": "mp4",
        "noplaylist": True,
        "overwrites": forcar,
        "no_warnings": True,
    }
    ffmpeg = Path(binario("ffmpeg"))
    if ffmpeg.is_file():
        opcoes["ffmpeg_location"] = str(ffmpeg)
    _, arquivo = _extrair(criar, opcoes, origem.url or url, baixar=True)
    video = caminhos.garantir_escrita(Path(arquivo or destino), base_extra=pasta)
    if not video.is_file():
        raise ErroEntrada(f"o yt-dlp terminou sem gravar o vídeo em {pasta}")
    origem.baixado_em = agora().isoformat(timespec="seconds")
    registro = caminhos.garantir_escrita(arquivo_de_origem(video), base_extra=pasta)
    caminhos.gravar_atomico(registro, json.dumps(asdict(origem), ensure_ascii=False, indent=2) + "\n")
    return video, origem
