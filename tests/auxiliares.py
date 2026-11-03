import json
from pathlib import Path

from esteira.cortar import preparar_episodio
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


def preparar_episodio_teste(tmp_path: Path, cortes: list[dict]) -> tuple[Path, Path]:
    pasta = tmp_path / "ep"
    (pasta / "transcricao").mkdir(parents=True)
    video = gerar_video_teste(tmp_path / "v.mp4", 80)
    cartao = gerar_video_teste(tmp_path / "fim.mp4", 1, 1080, 1920)
    (pasta / "episodio.json").write_text(json.dumps({"video": str(video), "duracao": 80}), "utf-8")
    palavras = [{"texto": "fala.", "inicio": t + 0.0, "fim": t + 0.9} for t in range(1, 70)]
    (pasta / "transcricao" / "palavras.json").write_text(json.dumps(palavras), "utf-8")
    (pasta / "aprovados.json").write_text(json.dumps({"cortes": cortes}), "utf-8")
    return pasta, cartao


def preparar_teste(
    pasta: Path, numeros: set[int] | None = None, forcar: bool = False, pasta_musicas: Path | None = None
) -> dict[int, str]:
    return preparar_episodio(pasta, numeros, forcar, [], pasta_musicas or pasta.parent / "musicas")
