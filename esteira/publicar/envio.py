import hashlib
from datetime import datetime
from pathlib import Path

from esteira.publicar.credenciais import ErroConexao
from esteira.publicar.fila import Item, gravar_fila
from esteira.publicar.http import ErroIncerto, ErroRede
from esteira.publicar.post import Textos

MAX_TENTATIVAS = 3
AVISO_RASCUNHO = "rascunho no app: cole o texto do post.md no app e publique"
FALTA_KEYRING = "falta instalar o pacote keyring: .venv\\Scripts\\python.exe -m pip install keyring"


def assinatura(video: Path, textos: Textos, rede: str) -> str:
    """Marca do vídeo e do texto daquela rede, para saber se mudaram depois do sim."""
    texto = {
        "youtube": textos.youtube_titulo + "\n" + textos.youtube_descricao,
        "instagram": textos.instagram,
        "tiktok": textos.tiktok,
    }[rede]
    marca = hashlib.sha256()
    with open(video, "rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(1 << 20), b""):
            marca.update(bloco)
    marca.update(texto.encode("utf-8"))
    return marca.hexdigest()


def enviar(pasta: Path, itens: list[Item], item: Item, video: Path, textos: Textos, modo: str, api) -> None:
    """Envia um item. Grava 'enviando' antes de chamar a rede e o resultado depois."""
    item.estado = "enviando"
    gravar_fila(pasta, itens)
    try:
        resultado = api.publicar(video, textos, datetime.fromisoformat(item.data), modo)
    except ErroRede as erro:
        item.tentativas += 1
        item.erro = str(erro)
        item.estado = "agendado" if erro.temporario and item.tentativas < MAX_TENTATIVAS else "erro"
    except ErroConexao as erro:
        item.estado, item.erro = "erro", str(erro)
    except ErroIncerto as erro:
        item.estado, item.erro = "conferir", f"{erro}; confira no app e use publicar marcar"
    except ImportError:
        item.estado, item.erro = "erro", FALTA_KEYRING
    except Exception as erro:  # nada se sabe do envio: conferir, nunca reenviar sozinho
        item.estado, item.erro = "conferir", f"erro inesperado: {type(erro).__name__}: {erro}; confira no app"
    else:
        item.estado, item.link, item.id_rede = resultado.estado, resultado.link, resultado.id_rede
        item.erro = AVISO_RASCUNHO if resultado.estado == "rascunho" else ""
    gravar_fila(pasta, itens)
