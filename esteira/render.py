import shutil
from pathlib import Path

from esteira.caminhos import FONTES
from esteira.midia import ErroMidia, executar_ffmpeg, sondar

Y_FAIXA = 442
ALTURA_FAIXA = 1036
FOLGA_BUSCA = 1.0
ENCODERS = [
    ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "19", "-b:v", "0"],
    ["-c:v", "libx264", "-preset", "medium", "-crf", "18"],
]
SAIDA_COMUM = ["-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2"]


def filtro_9x16() -> str:
    return (
        "[entrada]split=2[a][b];"
        "[a]scale=-2:1920,crop=1080:1920,gblur=sigma=40[fundo];"
        f"[b]scale=-2:{ALTURA_FAIXA},crop=1080:{ALTURA_FAIXA}[frente];"
        f"[fundo][frente]overlay=0:{Y_FAIXA},fps=30,setsar=1,format=yuv420p[montado]"
    )


def _filtro_completo(faixas: list[tuple[float, float]], deslocamento: float, cartao_tem_audio: bool, duracao_cartao: float) -> str:
    partes: list[str] = []
    rotulos = ""
    for i, (de, ate) in enumerate(faixas):
        a, b = de - deslocamento, ate - deslocamento
        partes.append(f"[0:v]trim=start={a:.3f}:end={b:.3f},setpts=PTS-STARTPTS[v{i}]")
        partes.append(f"[0:a]atrim=start={a:.3f}:end={b:.3f},asetpts=PTS-STARTPTS,aresample=44100,aformat=channel_layouts=stereo[a{i}]")
        rotulos += f"[v{i}][a{i}]"
    partes.append(f"{rotulos}concat=n={len(faixas)}:v=1:a=1[entrada][audio]")
    partes.append(filtro_9x16())
    partes.append("[1:v]scale=1080:1920,setsar=1,fps=30,format=yuv420p[vfim]")
    if cartao_tem_audio:
        partes.append("[1:a]aresample=44100,aformat=channel_layouts=stereo[afim]")
    else:
        partes.append(f"anullsrc=r=44100:cl=stereo,atrim=duration={duracao_cartao:.3f}[afim]")
    partes.append("[montado][audio][vfim][afim]concat=n=2:v=1:a=1[vsaida][asaida]")
    return ";".join(partes)


def _codificar(args_entrada: list[str], saida: Path, duracao_esperada: float, cwd: Path | None = None) -> None:
    temporario = saida.with_name(saida.stem + ".tmp.mp4")
    try:
        for indice, encoder in enumerate(ENCODERS):
            try:
                executar_ffmpeg(["-y", *args_entrada, *encoder, *SAIDA_COMUM, str(temporario)], cwd)
                break
            except ErroMidia:
                if indice == len(ENCODERS) - 1:
                    raise
        real = sondar(temporario).duracao
        if abs(real - duracao_esperada) > 0.5:
            raise ErroMidia(f"Duração inesperada em {saida.name}: {real:.1f}s, esperado {duracao_esperada:.1f}s")
        temporario.replace(saida)
    finally:
        temporario.unlink(missing_ok=True)


def renderizar_sem_legenda(video: Path, faixas: list[tuple[float, float]], cartao: Path, saida: Path) -> None:
    origem, fim = sondar(video), sondar(cartao)
    deslocamento = max(0.0, faixas[0][0] - FOLGA_BUSCA)
    filtro = _filtro_completo(faixas, deslocamento, fim.tem_audio, fim.duracao)
    entrada = [
        "-ss", f"{deslocamento:.3f}", "-t", f"{faixas[-1][1] - deslocamento + FOLGA_BUSCA:.3f}", "-i", str(video),
        "-i", str(cartao), "-filter_complex", filtro, "-map", "[vsaida]", "-map", "[asaida]",
    ]
    esperado = sum(b - a for a, b in faixas) + fim.duracao
    _codificar(entrada, Path(saida), esperado)


def queimar_legenda(base: Path, ass: Path, saida: Path) -> None:
    saida = Path(saida)
    pasta = saida.parent / ".legenda_tmp"
    pasta.mkdir(exist_ok=True)
    try:
        shutil.copy(ass, pasta / "legenda.ass")
        shutil.copy(FONTES / "Montserrat-Bold.ttf", pasta / "Montserrat-Bold.ttf")
        entrada = ["-i", str(base), "-vf", "ass=.legenda_tmp/legenda.ass:fontsdir=.legenda_tmp"]
        _codificar(entrada, saida, sondar(base).duracao, cwd=saida.parent)
    finally:
        shutil.rmtree(pasta, ignore_errors=True)
