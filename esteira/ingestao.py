import shutil
from pathlib import Path

from esteira.imagens import EXTENSOES

PASTA_ENTRADA = "ia-entrada"
MAPA = ".mapa.tsv"


def arquivos_ia(pasta: Path) -> list[Path]:
    entrada = Path(pasta) / PASTA_ENTRADA
    if not entrada.is_dir():
        return []
    arquivos = [
        p for p in entrada.iterdir()
        if p.is_file() and not p.name.startswith(".") and p.suffix.lower() in EXTENSOES
    ]
    return sorted(arquivos, key=lambda p: (p.stat().st_mtime, p.name))


def encaixar_ia(
    pasta: Path,
    destinos: list[tuple[Path, str, str]],
    pular: frozenset[Path] | set[Path] = frozenset(),
) -> list[Path]:
    """Copia as imagens de ia-entrada/ para os cortes, na ordem do download.

    Os cortes em `pular` contam na verificação, mas não recebem arquivo.
    """
    if not destinos:
        return []
    arquivos = arquivos_ia(pasta)
    if len(arquivos) != len(destinos):
        raise ValueError(f"{PASTA_ENTRADA}/: esperadas {len(destinos)} imagens, encontradas {len(arquivos)}")
    copiados: list[Path] = []
    linhas: list[str] = []
    for origem, (corte, nome, rotulo) in zip(arquivos, destinos):
        linhas.append(f"{rotulo}\t{origem.name}")
        if corte in pular:
            continue
        (corte / "imagens").mkdir(exist_ok=True)
        destino = corte / "imagens" / f"{nome}{origem.suffix.lower()}"
        shutil.copyfile(origem, destino)
        copiados.append(destino)
    (Path(pasta) / PASTA_ENTRADA / MAPA).write_text("\n".join(linhas) + "\n", "utf-8", newline="\n")
    return copiados
