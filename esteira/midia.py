import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from esteira.caminhos import BIN


def binario(nome: str) -> str:
    """O ffmpeg/ffprobe de bin/ (Windows) ou, sem ele, o do PATH (Linux, macOS e CI)."""
    for candidato in (BIN / f"{nome}.exe", BIN / nome):
        if candidato.is_file():
            return str(candidato)
    return shutil.which(nome) or str(BIN / f"{nome}.exe")


class ErroMidia(Exception):
    pass


@dataclass
class Midia:
    duracao: float
    largura: int
    altura: int
    tem_audio: bool


def _rodar(
    comando: list[str], cwd: Path | None, timeout: float | None = None
) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            comando, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise ErroMidia(f"ffmpeg demorou mais de {timeout:g} s") from None


def executar_ffmpeg(args: list[str], cwd: Path | None = None, timeout: float | None = None) -> None:
    resultado = _rodar(
        [binario("ffmpeg"), "-hide_banner", "-loglevel", "error", *args], cwd, timeout
    )
    if resultado.returncode != 0:
        raise ErroMidia(f"ffmpeg falhou: {resultado.stderr[-800:]}")


def saida_ffmpeg(args: list[str]) -> str:
    resultado = _rodar([binario("ffmpeg"), "-hide_banner", *args], None)
    if resultado.returncode != 0:
        raise ErroMidia(f"ffmpeg falhou: {resultado.stderr[-800:]}")
    return resultado.stderr


def pico_de_audio(video: Path, duracao: float | None = None) -> float:
    limite = ["-t", f"{duracao:.3f}"] if duracao is not None else []
    log = saida_ffmpeg(["-i", str(video), *limite, "-vn", "-af", "volumedetect", "-f", "null", "-"])
    achado = re.search(r"max_volume:\s*(-?[\d.]+|-inf) dB", log)
    if not achado:
        raise ErroMidia(f"Não consegui medir o áudio de {video}")
    return float(achado.group(1))


LIMIAR_SILENCIO_DB = -35.0
SILENCIO_MINIMO = 0.25


def silencios(video: Path, inicio: float, fim: float) -> list[tuple[float, float]]:
    """Intervalos de silêncio (em segundos do episódio) entre `inicio` e `fim`, medidos no áudio (silencedetect)."""
    log = saida_ffmpeg([
        "-ss", f"{inicio:.3f}", "-t", f"{max(0.0, fim - inicio):.3f}", "-i", str(video), "-vn",
        "-af", f"silencedetect=noise={LIMIAR_SILENCIO_DB:g}dB:d={SILENCIO_MINIMO:g}", "-f", "null", "-",
    ])
    intervalos: list[tuple[float, float]] = []
    aberto: float | None = None
    for linha in log.splitlines():
        achado = re.search(r"silence_start:\s*(-?[\d.]+)", linha)
        if achado:
            aberto = inicio + max(0.0, float(achado.group(1)))
            continue
        achado = re.search(r"silence_end:\s*(-?[\d.]+)", linha)
        if achado and aberto is not None:
            intervalos.append((aberto, inicio + float(achado.group(1))))
            aberto = None
    if aberto is not None:
        intervalos.append((aberto, fim))
    return intervalos


def versao_ffmpeg() -> str:
    return _rodar([binario("ffmpeg"), "-version"], None).stdout.split("\n")[0]


def duracao_audio(arquivo: Path) -> float:
    resultado = _rodar(
        [
            binario("ffprobe"), "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(arquivo),
        ],
        None,
    )
    if resultado.returncode != 0 or not resultado.stdout.strip():
        raise ErroMidia(f"Não consegui medir a duração de {arquivo}: {resultado.stderr[-400:]}")
    return float(resultado.stdout.strip())


def sondar(video: Path) -> Midia:
    resultado = _rodar(
        [
            binario("ffprobe"), "-v", "error", "-print_format", "json",
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
