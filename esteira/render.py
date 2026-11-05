import shutil
from collections.abc import Callable
from pathlib import Path

from esteira.caminhos import FONTES
from esteira.legenda import escrever_ass
from esteira.midia import ErroMidia, executar_ffmpeg, pico_de_audio, sondar
from esteira.planos import Plano, dividir_em_segmentos, recorte
from esteira.receita import Musica, Receita, duracao_principal

TRANSICAO_ENCERRAMENTO = 0.5
FADE_MUSICA_ENTRADA = 0.5
FADE_MUSICA_SAIDA = 1.5
LIMIAR_PICO = -0.5
Y_FAIXA = 442
ALTURA_FAIXA = 1036
FOLGA_BUSCA = 1.0
ENCODERS = [
    ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "19", "-b:v", "0"],
    ["-c:v", "libx264", "-preset", "medium", "-crf", "18"],
]
SAIDA_COMUM = ["-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2"]


def filtro_9x16(entrada: str, saida: str, corte: tuple[int, int, int, int]) -> str:
    w, h, x, y = corte
    return (
        f"[{entrada}]crop={w}:{h}:{x}:{y},split=2[{saida}a][{saida}b];"
        f"[{saida}a]scale=-2:1920,crop=1080:1920,gblur=sigma=40[{saida}f];"
        f"[{saida}b]scale=1080:{ALTURA_FAIXA}[{saida}c];"
        f"[{saida}f][{saida}c]overlay=0:{Y_FAIXA},fps=30,setsar=1,format=yuv420p[{saida}]"
    )


def _filtro_segmentos(
    segmentos: list[tuple[float, float, Plano]], largura: int, altura: int, deslocamento: float
) -> tuple[list[str], str]:
    partes: list[str] = []
    rotulos = ""
    for i, (de, ate, plano) in enumerate(segmentos):
        a, b = de - deslocamento, ate - deslocamento
        partes.append(f"[0:v]trim=start={a:.3f}:end={b:.3f},setpts=PTS-STARTPTS[t{i}]")
        partes.append(filtro_9x16(f"t{i}", f"v{i}", recorte(plano, largura, altura)))
        partes.append(
            f"[0:a]atrim=start={a:.3f}:end={b:.3f},asetpts=PTS-STARTPTS,"
            f"aresample=44100,aformat=channel_layouts=stereo[a{i}]"
        )
        rotulos += f"[v{i}][a{i}]"
    return partes, rotulos


def _filtro_cartao(cartao: int, logo: int | None, tem_audio: bool, duracao: float) -> list[str]:
    partes: list[str] = []
    fim = f"[{cartao}:v]scale=1080:1920,setsar=1,fps=30"
    if logo is not None:
        partes.append(f"{fim}[base]")
        partes.append(f"[{logo}:v]format=rgba,fade=t=in:st=0:d=0.4:alpha=1[logo]")
        partes.append("[base][logo]overlay=0:0:shortest=1,format=yuv420p[vfim]")
    else:
        partes.append(f"{fim},format=yuv420p[vfim]")
    if tem_audio:
        partes.append(f"[{cartao}:a]aresample=44100,aformat=channel_layouts=stereo[afim]")
    else:
        partes.append(f"anullsrc=r=44100:cl=stereo,atrim=duration={duracao:.3f}[afim]")
    return partes


def _filtro_musica(entrada: int, musica: Musica, duracao: float) -> list[str]:
    saida_fade = max(0.0, duracao - FADE_MUSICA_SAIDA)
    return [
        "[aprin]asplit=2[voz][controle]",
        f"[{entrada}:a]atrim=duration={duracao:.3f},asetpts=PTS-STARTPTS,aresample=44100,"
        f"aformat=channel_layouts=stereo,volume={musica.volume_db:.1f}dB,"
        f"afade=t=in:st=0:d={FADE_MUSICA_ENTRADA},afade=t=out:st={saida_fade:.3f}:d={FADE_MUSICA_SAIDA}[musica]",
        "[musica][controle]sidechaincompress=threshold=0.05:ratio=4:attack=20:release=300[abafada]",
        "[voz][abafada]amix=inputs=2:duration=first:normalize=0[amix]",
    ]


def _codificar(
    args_entrada: list[str],
    saida: Path,
    duracao_esperada: float,
    cwd: Path | None = None,
    verificar: Callable[[Path], None] | None = None,
) -> None:
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
        if verificar:
            verificar(temporario)
        temporario.replace(saida)
    finally:
        temporario.unlink(missing_ok=True)


def renderizar_final(
    receita: Receita, video: Path, cartao: Path, pasta: Path, saida: Path, sobreposicao: Path | None = None
) -> list[str]:
    video, saida = Path(video).resolve(), Path(saida).resolve()
    origem = sondar(video)
    fim = sondar(cartao) if receita.encerramento else None
    faixas = receita.faixas
    deslocamento = max(0.0, faixas[0][0] - FOLGA_BUSCA)
    segmentos = dividir_em_segmentos(faixas, receita.planos)
    entradas = [
        ["-ss", f"{deslocamento:.3f}", "-t", f"{faixas[-1][1] - deslocamento + FOLGA_BUSCA:.3f}", "-i", str(video)]
    ]
    partes, rotulos = _filtro_segmentos(segmentos, origem.largura, origem.altura, deslocamento)
    partes.append(f"{rotulos}concat=n={len(segmentos)}:v=1:a=1[vprin][aprin]")

    rotulo_video = "vprin"
    partes.append(f"[{rotulo_video}]ass=.legenda_tmp/legenda.ass:fontsdir=.legenda_tmp[vleg]")

    alertas: list[str] = []
    rotulo_audio = "aprin"
    if receita.musica:
        entradas.append(["-stream_loop", "-1", "-i", str(Path(receita.musica.arquivo).resolve())])
        partes += _filtro_musica(len(entradas) - 1, receita.musica, duracao_principal(receita))
        rotulo_audio = "amix"
    else:
        alertas.append("sem música")

    esperado = duracao_principal(receita)
    if fim is not None:
        entradas.append(["-i", str(Path(cartao).resolve())])
        indice_cartao = len(entradas) - 1
        indice_logo = None
        if sobreposicao is not None:
            entradas.append(["-loop", "1", "-framerate", "30", "-i", str(Path(sobreposicao).resolve())])
            indice_logo = len(entradas) - 1
        partes += _filtro_cartao(indice_cartao, indice_logo, fim.tem_audio, fim.duracao)
        partes.append(
            f"[vleg]fps=30,settb=1/30,tpad=stop_mode=clone:stop_duration={TRANSICAO_ENCERRAMENTO}[vleg30];"
            "[vfim]fps=30,settb=1/30[vfim30]"
        )
        partes.append(
            f"[vleg30][vfim30]xfade=transition=fade:duration={TRANSICAO_ENCERRAMENTO}:offset={esperado:.3f}[vsaida]"
        )
        partes.append(f"[{rotulo_audio}]apad=pad_dur={TRANSICAO_ENCERRAMENTO}[apausa]")
        partes.append(f"[apausa][afim]acrossfade=d={TRANSICAO_ENCERRAMENTO}[asaida]")
        rotulo_video, rotulo_audio = "vsaida", "asaida"
        esperado += fim.duracao
    else:
        rotulo_video = "vleg"

    args = [arg for entrada in entradas for arg in entrada]
    args += ["-filter_complex", ";".join(partes), "-map", f"[{rotulo_video}]", "-map", f"[{rotulo_audio}]"]
    temporaria = saida.parent / ".legenda_tmp"
    temporaria.mkdir(exist_ok=True)
    pico = 0.0

    def medir(arquivo: Path) -> None:
        nonlocal pico
        pico = pico_de_audio(arquivo, duracao_principal(receita))

    try:
        escrever_ass(receita.legenda, temporaria / "legenda.ass")
        shutil.copy(FONTES / "Montserrat-Bold.ttf", temporaria / "Montserrat-Bold.ttf")
        _codificar(args, saida, esperado, cwd=saida.parent, verificar=medir)
    finally:
        shutil.rmtree(temporaria, ignore_errors=True)

    if pico > LIMIAR_PICO:
        alertas.append(f"áudio perto de saturar: {pico:.1f} dB")
    return alertas
