import shutil
from pathlib import Path

from esteira.caminhos import FONTES
from esteira.legenda import escrever_ass, ocultar_durante
from esteira.midia import ErroMidia, executar_ffmpeg, pico_de_audio, sondar
from esteira.planos import Plano, dividir_em_segmentos, recorte
from esteira.receita import Imagem, Musica, Receita, duracao_principal

ZOOM_IMAGEM = 1.08
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


def _filtro_completo(
    segmentos: list[tuple[float, float, Plano]],
    largura: int,
    altura: int,
    deslocamento: float,
    cartao_tem_audio: bool,
    duracao_cartao: float,
    com_sobreposicao: bool = False,
) -> str:
    partes, rotulos = _filtro_segmentos(segmentos, largura, altura, deslocamento)
    partes += _filtro_cartao(1, 2 if com_sobreposicao else None, cartao_tem_audio, duracao_cartao)
    partes.append(f"{rotulos}[vfim][afim]concat=n={len(segmentos) + 1}:v=1:a=1[vsaida][asaida]")
    return ";".join(partes)


def _filtro_imagem(entrada: int, saida: str, ordem: int, imagem: Imagem) -> str:
    filtro = f"[{entrada}:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"
    if ZOOM_IMAGEM > 1:
        quadros = round((imagem.fim - imagem.inicio) * 30)
        passo = f"{ZOOM_IMAGEM - 1:.4f}*in/{max(quadros - 1, 1)}"
        z = f"(1+{passo})" if ordem % 2 == 0 else f"({ZOOM_IMAGEM}-{passo})"
        x0, y0, x1, y1 = f"W/2-W/2/{z}", f"H/2-H/2/{z}", f"W/2+W/2/{z}", f"H/2+H/2/{z}"
        filtro += (
            f",perspective=x0='{x0}':y0='{y0}':x1='{x1}':y1='{y0}':x2='{x0}':y2='{y1}':x3='{x1}':y3='{y1}'"
            ":interpolation=cubic:eval=frame"
        )
    return filtro + f",setsar=1,format=yuv420p,setpts=PTS-STARTPTS+{imagem.inicio:.3f}/TB[{saida}]"


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


def renderizar_sem_legenda(
    video: Path,
    faixas: list[tuple[float, float]],
    cartao: Path,
    saida: Path,
    planos: list[Plano] | None = None,
    sobreposicao: Path | None = None,
) -> None:
    origem, fim = sondar(video), sondar(cartao)
    deslocamento = max(0.0, faixas[0][0] - FOLGA_BUSCA)
    segmentos = dividir_em_segmentos(faixas, planos or [])
    filtro = _filtro_completo(
        segmentos, origem.largura, origem.altura, deslocamento, fim.tem_audio, fim.duracao,
        sobreposicao is not None,
    )
    entrada = [
        "-ss", f"{deslocamento:.3f}", "-t", f"{faixas[-1][1] - deslocamento + FOLGA_BUSCA:.3f}", "-i", str(video),
        "-i", str(cartao),
    ]
    if sobreposicao is not None:
        entrada += ["-loop", "1", "-framerate", "30", "-i", str(sobreposicao)]
    entrada += ["-filter_complex", filtro, "-map", "[vsaida]", "-map", "[asaida]"]
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
    for ordem, imagem in enumerate(receita.imagens):
        arquivo = (Path(pasta) / imagem.arquivo).resolve()
        duracao = imagem.fim - imagem.inicio
        entradas.append(["-loop", "1", "-framerate", "30", "-t", f"{duracao:.3f}", "-i", str(arquivo)])
        partes.append(_filtro_imagem(len(entradas) - 1, f"img{ordem}", ordem, imagem))
        partes.append(
            f"[{rotulo_video}][img{ordem}]overlay=enable='between(t,{imagem.inicio:.3f},{imagem.fim:.3f})'"
            f":eof_action=pass[vi{ordem}]"
        )
        rotulo_video = f"vi{ordem}"
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
        partes.append(f"[vleg][{rotulo_audio}][vfim][afim]concat=n=2:v=1:a=1[vsaida][asaida]")
        rotulo_video, rotulo_audio = "vsaida", "asaida"
        esperado += fim.duracao
    else:
        rotulo_video = "vleg"

    args = [arg for entrada in entradas for arg in entrada]
    args += ["-filter_complex", ";".join(partes), "-map", f"[{rotulo_video}]", "-map", f"[{rotulo_audio}]"]
    temporaria = saida.parent / ".legenda_tmp"
    temporaria.mkdir(exist_ok=True)
    try:
        intervalos = [(i.inicio, i.fim) for i in receita.imagens]
        escrever_ass(ocultar_durante(receita.legenda, intervalos), temporaria / "legenda.ass")
        shutil.copy(FONTES / "Montserrat-Bold.ttf", temporaria / "Montserrat-Bold.ttf")
        _codificar(args, saida, esperado, cwd=saida.parent)
    finally:
        shutil.rmtree(temporaria, ignore_errors=True)

    pico = pico_de_audio(saida)
    if pico > LIMIAR_PICO:
        alertas.append(f"áudio perto de saturar: {pico:.1f} dB")
    return alertas
