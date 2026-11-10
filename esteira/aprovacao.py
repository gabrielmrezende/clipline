"""Aprovar o corte pelo painel: copia o corte.mp4 para video-final/.

A esteira só grava em video-final/ por aqui, e só substitui a própria cópia: um arquivo cujo nome, tamanho e data
de modificação batem com o trabalho/aprovado.json. Qualquer outro vídeo de video-final/ é do dono e nunca é tocado.
"""

import json
import os
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from esteira.caminhos import garantir_escrita
from esteira.cortar import CORTE_MP4, TRABALHO, VIDEO_FINAL

ARQUIVO_APROVADO = "corte-aprovado.mp4"
REGISTRO_APROVADO = "aprovado.json"
TEMPORARIO = ".corte-aprovado.tmp"
EXTENSOES_VIDEO = (".mp4", ".mov")
SEM_CORTE = "corte não montado"
MONTANDO = "o corte está sendo montado"
DO_DONO = "video-final/ já tem um vídeo seu ({nome}). Para aprovar o corte da esteira, tire esse vídeo de lá."


@dataclass
class Aprovacao:
    estado: str  # "aprovar" | "aprovar de novo" | "aprovado" | "bloqueado"
    motivo: str | None = None


class ErroAprovacao(Exception):
    def __init__(self, motivo: str, status: int) -> None:
        super().__init__(motivo)
        self.status = status


def _ler_json(caminho: Path):
    try:
        return json.loads(caminho.read_text("utf-8"))
    except (OSError, ValueError):
        return None


def da_esteira(destino: Path) -> dict | None:
    """O aprovado.json, se o arquivo que ele descreve está em video-final/ intacto (mesmo tamanho e data)."""
    dados = _ler_json(Path(destino) / TRABALHO / REGISTRO_APROVADO)
    if not isinstance(dados, dict) or dados.get("arquivo") != ARQUIVO_APROVADO:
        return None
    try:
        info = (Path(destino) / VIDEO_FINAL / ARQUIVO_APROVADO).stat()
    except OSError:
        return None
    if (info.st_size, info.st_mtime_ns) != (dados.get("tamanho"), dados.get("modificado_ns")):
        return None
    return dados


def _videos(destino: Path) -> list[Path]:
    pasta = Path(destino) / VIDEO_FINAL
    if not pasta.is_dir():
        return []
    return sorted((a for a in pasta.iterdir() if a.is_file() and a.suffix.lower() in EXTENSOES_VIDEO), key=lambda a: a.name.lower())


def estado_aprovacao(destino: Path, montando: bool = False) -> Aprovacao:
    destino = Path(destino)
    if montando:
        return Aprovacao("bloqueado", MONTANDO)
    corte = destino / CORTE_MP4
    if not corte.is_file():
        return Aprovacao("bloqueado", SEM_CORTE)
    esteira = da_esteira(destino)
    do_dono = [v for v in _videos(destino) if esteira is None or v.name != esteira["arquivo"]]
    if do_dono:
        return Aprovacao("bloqueado", DO_DONO.format(nome=do_dono[0].name))
    if esteira is None:
        return Aprovacao("aprovar")
    info = corte.stat()
    origem = esteira.get("corte")
    em_dia = isinstance(origem, dict) and (info.st_size, info.st_mtime_ns) == (origem.get("tamanho"), origem.get("modificado_ns"))
    return Aprovacao("aprovado" if em_dia else "aprovar de novo")


def _imagens_do_registro(destino: Path) -> list[dict] | None:
    """As imagens da última montagem que deu certo; None num registro de antes da Fase B."""
    registro = _ler_json(Path(destino) / TRABALHO / "registro.json")
    if not isinstance(registro, dict) or not str(registro.get("resultado", "")).startswith("ok"):
        return None
    imagens = registro.get("imagens")
    return [i for i in imagens if isinstance(i, dict)] if isinstance(imagens, list) else None


def aprovar(
    destino: Path, montando: bool = False, base: Path | None = None, agora: Callable[[], datetime] = datetime.now
) -> Aprovacao:
    """Copia o corte.mp4 para video-final/corte-aprovado.mp4. Recusa (ErroAprovacao) sem gravar nada."""
    destino = Path(destino)
    atual = estado_aprovacao(destino, montando)
    if atual.estado == "aprovado":
        return atual
    if atual.estado == "bloqueado":
        raise ErroAprovacao(atual.motivo, 422 if atual.motivo == SEM_CORTE else 409)
    pasta = destino / VIDEO_FINAL
    final = garantir_escrita(pasta / ARQUIVO_APROVADO, base_extra=base)
    temporario = garantir_escrita(pasta / TEMPORARIO, base_extra=base)
    registro = garantir_escrita(destino / TRABALHO / REGISTRO_APROVADO, base_extra=base)
    pasta.mkdir(exist_ok=True)
    origem = (destino / CORTE_MP4).stat()
    try:
        shutil.copyfile(destino / CORTE_MP4, temporario)
        os.replace(temporario, final)
    except OSError as erro:
        temporario.unlink(missing_ok=True)
        raise ErroAprovacao(f"Não consegui copiar o corte para video-final/: {erro}", 422) from erro
    info = final.stat()
    dados = {
        "arquivo": ARQUIVO_APROVADO,
        "tamanho": info.st_size,
        "modificado_ns": info.st_mtime_ns,
        "data": agora().isoformat(timespec="seconds"),
        "corte": {"tamanho": origem.st_size, "modificado_ns": origem.st_mtime_ns},  # o corte.mp4 copiado
        "imagens": _imagens_do_registro(destino),
    }
    provisorio = registro.with_name(registro.name + ".tmp")
    provisorio.write_text(json.dumps(dados, ensure_ascii=False, indent=2) + "\n", "utf-8", newline="\n")
    os.replace(provisorio, registro)
    return estado_aprovacao(destino, montando)


def imagens_aprovadas(destino: Path, video: Path) -> list[dict] | None:
    """As imagens do vídeo aprovado pelo painel, se `video` é essa cópia e a lista é conhecida; senão None."""
    destino = Path(destino)
    dados = da_esteira(destino)
    if dados is None or Path(video).resolve() != (destino / VIDEO_FINAL / ARQUIVO_APROVADO).resolve():
        return None
    imagens = dados.get("imagens")
    return [i for i in imagens if isinstance(i, dict)] if isinstance(imagens, list) else None
