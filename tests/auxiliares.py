from pathlib import Path

from esteira.midia import executar_ffmpeg


def gerar_video_teste(
    saida: Path, segundos: float, largura: int = 1920, altura: int = 1080, audio: bool = True
) -> Path:
    args = ["-y", "-f", "lavfi", "-i", f"testsrc2=size={largura}x{altura}:rate=30:duration={segundos}"]
    if audio:
        args += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={segundos}"]
    args += ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p"]
    if audio:
        args += ["-c:a", "aac"]
    executar_ffmpeg(args + [str(saida)])
    return saida
