import re
from pathlib import Path

from esteira.receita import Imagem

EXTENSOES = {".jpg", ".jpeg", ".png", ".webp"}
_TITULO = re.compile(
    r"^##\s+(\d+)\.\s+(\d+:\d{2}:\d{2}(?:[.,]\d+)?)\s+a\s+(\d+:\d{2}:\d{2}(?:[.,]\d+)?)\s+[—–-]",
    re.M,
)
_LICENCA = re.compile(r"^Autor e licença:[ \t]*(.*)$", re.M)


def _segundos(texto: str) -> float:
    horas, minutos, segundos = texto.replace(",", ".").split(":")
    return int(horas) * 3600 + int(minutos) * 60 + float(segundos)


def _arquivo(pasta: Path, numero: int) -> str | None:
    prefixo = f"{numero:02d}-"
    candidatos = sorted(
        c.name
        for c in (pasta / "imagens").glob("*")
        if c.is_file() and c.name.startswith(prefixo) and c.suffix.lower() in EXTENSOES
    )
    return f"imagens/{candidatos[0]}" if candidatos else None


def secoes_sem_arquivo(pasta: Path) -> list[int]:
    pasta = Path(pasta)
    caminho = pasta / "imagens.md"
    if not caminho.exists():
        return []
    numeros = sorted(int(t.group(1)) for t in _TITULO.finditer(caminho.read_text("utf-8")))
    return [n for n in numeros if _arquivo(pasta, n) is None]


def ler_imagens(pasta: Path) -> list[Imagem]:
    pasta = Path(pasta)
    caminho = pasta / "imagens.md"
    if not caminho.exists() or not (pasta / "imagens").is_dir():
        return []
    texto = caminho.read_text("utf-8")
    titulos = list(_TITULO.finditer(texto))
    imagens = []
    for i, titulo in enumerate(titulos):
        numero = int(titulo.group(1))
        arquivo = _arquivo(pasta, numero)
        if arquivo is None:
            continue
        fim_secao = titulos[i + 1].start() if i + 1 < len(titulos) else len(texto)
        licenca = _LICENCA.search(texto, titulo.end(), fim_secao)
        imagens.append((numero, Imagem(
            _segundos(titulo.group(2)),
            _segundos(titulo.group(3)),
            arquivo,
            licenca.group(1).strip() if licenca else "",
        )))
    return [imagem for _, imagem in sorted(imagens, key=lambda par: par[0])]
