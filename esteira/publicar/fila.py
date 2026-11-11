import json
import os
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path

from esteira.caminhos import garantir_escrita

ARQUIVO = "postagens.json"


@dataclass
class Item:
    numero: int
    rede: str
    data: str
    estado: str = "agendado"
    tentativas: int = 0
    link: str = ""
    id_rede: str = ""
    erro: str = ""
    assinatura: str = ""
    ia: bool = False  # o vídeo tem imagem de IA: vai com o rótulo de conteúdo sintético das redes que têm um


class Ocupado(Exception):
    pass


def ler_fila(pasta_episodio: Path) -> list[Item]:
    caminho = Path(pasta_episodio) / ARQUIVO
    if not caminho.exists():
        return []
    dados = json.loads(caminho.read_text("utf-8"))
    return [Item(**item) for item in dados["itens"]]


def gravar_fila(pasta_episodio: Path, itens: list[Item], base: Path | None = None) -> None:
    destino = Path(pasta_episodio) / ARQUIVO
    caminho = garantir_escrita(destino, base_extra=base) if base is not None else garantir_escrita(destino)
    temporario = caminho.with_name(caminho.name + ".tmp")
    texto = json.dumps({"itens": [asdict(i) for i in itens]}, ensure_ascii=False, indent=2)
    temporario.write_text(texto, "utf-8")
    temporario.replace(caminho)


def achar(itens: list[Item], numero: int, rede: str) -> Item | None:
    for item in itens:
        if item.numero == numero and item.rede == rede and item.estado != "cancelado":
            return item
    return None


@contextmanager
def trava(caminho: Path, idade_maxima: float = 7200):
    caminho = Path(caminho)
    if caminho.exists() and time.time() - caminho.stat().st_mtime > idade_maxima:
        caminho.unlink(missing_ok=True)
    try:
        descritor = os.open(caminho, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise Ocupado(f"outra execução em andamento ({caminho.name})") from None
    os.close(descritor)
    try:
        yield
    finally:
        caminho.unlink(missing_ok=True)
