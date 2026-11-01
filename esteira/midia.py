import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from esteira.caminhos import BIN


class ErroMidia(Exception):
    pass


@dataclass
class Midia:
    duracao: float
    largura: int
    altura: int
    tem_audio: bool


def _rodar(comando: list[str], cwd: Path | None) -> subprocess.CompletedProcess:
    return subprocess.run(
        comando, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )


def executar_ffmpeg(args: list[str], cwd: Path | None = None) -> None:
    resultado = _rodar([str(BIN / "ffmpeg.exe"), "-hide_banner", "-loglevel", "error", *args], cwd)
    if resultado.returncode != 0:
        raise ErroMidia(f"ffmpeg falhou: {resultado.stderr[-800:]}")


def sondar(video: Path) -> Midia:
    resultado = _rodar(
        [
            str(BIN / "ffprobe.exe"), "-v", "error", "-print_format", "json",
            "-show_format", "-show_streams", str(video),
        ],
        None,
    )
    if resultado.returncode != 0:
        raise ErroMidia(f"Não consegui ler o vídeo {video}: {resultado.stderr[-400:]}")
    dados = json.loads(resultado.stdout)
    videos = [s for s in dados["streams"] if s["codec_type"] == "video"]
    if not videos:
        raise ErroMidia(f"Arquivo sem faixa de vídeo: {video}")
    return Midia(
        duracao=float(dados["format"]["duration"]),
        largura=int(videos[0]["width"]),
        altura=int(videos[0]["height"]),
        tem_audio=any(s["codec_type"] == "audio" for s in dados["streams"]),
    )
