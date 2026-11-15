import json
import re
import tempfile
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from esteira.caminhos import FONTES, gravar_atomico
from esteira.midia import executar_ffmpeg, saida_ffmpeg

PROPORCAO_FAIXA = 1080 / 1036
PROPORCAO_PAINEL = 1080 / 960  # cada metade da tela dividida
LIMIAR_DE_CENA = 0.1
PLANO_MINIMO = 0.25
LARGURA_MINIATURA = 400
COLUNAS = 4
COR_SUAVE = "#00E5FF"
CORES_PAINEIS = ("#00E5FF", "#FF4FD8")  # metade de cima, metade de baixo


@dataclass
class Plano:
    inicio: float
    fim: float
    x: float = 0.5
    y: float = 0.5
    zoom: float = 1.0
    # Acompanhamento suave: [[tempo, x, y], ...] (tempo do episódio); o centro do recorte segue esses pontos.
    trajeto: list[list[float]] | None = None
    # Tela dividida: [cima, baixo], cada um {"pessoa", "x", "y", "zoom"} e, se suave, "trajeto".
    divisao: list[dict] | None = None


OPCIONAIS = ("trajeto", "divisao")


def plano_em_dict(plano: Plano) -> dict:
    """O plano como fica no JSON: sem os campos opcionais vazios (o arquivo de sempre não muda)."""
    dados = asdict(plano)
    for campo in OPCIONAIS:
        if dados[campo] is None:
            del dados[campo]
    return dados


def paineis(plano: Plano) -> list[Plano]:
    """As duas metades de um plano de tela dividida (cima, baixo), como planos comuns."""
    if not isinstance(plano.divisao, list) or len(plano.divisao) != 2:
        raise ValueError("enquadramento.json: divisao precisa de dois quadros (cima e baixo)")
    try:
        metades = [
            Plano(plano.inicio, plano.fim, float(p["x"]), float(p["y"]), float(p["zoom"]), p.get("trajeto"))
            for p in plano.divisao
        ]
    except (KeyError, TypeError, ValueError, AttributeError):
        raise ValueError("enquadramento.json: cada quadro da divisao precisa de x, y e zoom") from None
    for metade in metades:
        if not 1.0 <= metade.zoom <= 2.0:
            raise ValueError("enquadramento.json: zoom da divisao fora de 1,0 a 2,0")
        _conferir_trajeto(metade.trajeto)
    return metades


def _conferir_trajeto(trajeto) -> None:
    if trajeto is None:
        return
    bons = isinstance(trajeto, list) and trajeto and all(
        isinstance(p, list) and len(p) == 3 and all(isinstance(v, (int, float)) for v in p) for p in trajeto
    )
    if not bons or any(b[0] < a[0] for a, b in zip(trajeto, trajeto[1:])):
        raise ValueError("enquadramento.json: trajeto precisa de pontos [tempo, x, y] em ordem de tempo")


def _interpolar(trajeto: list[list[float]], tempo: float) -> tuple[float, float]:
    if tempo <= trajeto[0][0]:
        return trajeto[0][1], trajeto[0][2]
    for (t0, x0, y0), (t1, x1, y1) in zip(trajeto, trajeto[1:]):
        if tempo <= t1:
            fracao = (tempo - t0) / (t1 - t0) if t1 > t0 else 1.0
            return x0 + (x1 - x0) * fracao, y0 + (y1 - y0) * fracao
    return trajeto[-1][1], trajeto[-1][2]


def centro_em(plano: Plano, tempo: float) -> tuple[float, float]:
    """Centro do recorte no instante `tempo` (do episódio): o trajeto, se houver; senão x e y."""
    if not plano.trajeto:
        return plano.x, plano.y
    _conferir_trajeto(plano.trajeto)
    return _interpolar(plano.trajeto, tempo)


def _par(valor: float) -> int:
    return int(valor) // 2 * 2


def recorte(plano: Plano, largura: int, altura: int, proporcao: float = PROPORCAO_FAIXA) -> tuple[int, int, int, int]:
    h = min(_par(altura / plano.zoom), altura)
    w = min(_par(h * proporcao), largura)
    x = min(max(round(largura * plano.x - w / 2), 0), largura - w)
    y = min(max(round(altura * plano.y - h / 2), 0), altura - h)
    return w, h, x, y


def _expressao(pontos: list[tuple[float, int]]) -> int | str:
    """Interpolação linear entre pontos (t, valor) como expressão do ffmpeg, sem `if` aninhado:
    o valor inicial mais uma rampa `clip((t-t0)/d,0,1)` por trecho. Antes do primeiro ponto vale o
    primeiro valor; depois do último, o último."""
    termos = []
    for (t0, v0), (t1, v1) in zip(pontos, pontos[1:]):
        if v1 == v0 or t1 - t0 < 0.001:
            continue
        sinal = "+" if v1 > v0 else "-"
        termos.append(f"{sinal}{abs(v1 - v0)}*clip((t-{t0:.3f})/{t1 - t0:.3f},0,1)")
    if not termos:
        return pontos[0][1]
    return f"'{pontos[0][1]}{''.join(termos)}'"


def recorte_no_tempo(
    plano: Plano, largura: int, altura: int, de: float, ate: float, proporcao: float = PROPORCAO_FAIXA
) -> tuple[int, int, int | str, int | str]:
    """Como `recorte`, para o trecho de `de` a `ate` (tempo do episódio). Com trajeto, x e y viram expressões
    do crop do ffmpeg em `t`, o tempo do trecho (zero em `de`). Sem trajeto, é igual a `recorte`."""
    w, h, x, y = recorte(plano, largura, altura, proporcao)
    if not plano.trajeto:
        return w, h, x, y
    _conferir_trajeto(plano.trajeto)
    dentro = [(t, px, py) for t, px, py in plano.trajeto if de < t < ate]
    pontos = [(de, *_interpolar(plano.trajeto, de)), *dentro, (ate, *_interpolar(plano.trajeto, ate))]

    def pixel(valor: float, tamanho: int, total: int) -> int:
        return min(max(round(total * valor - tamanho / 2), 0), total - tamanho)

    xs = [(t - de, pixel(px, w, largura)) for t, px, _ in pontos]
    ys = [(t - de, pixel(py, h, altura)) for t, _, py in pontos]
    return w, h, _expressao(xs), _expressao(ys)


def dividir_em_segmentos(
    faixas: list[tuple[float, float]], planos: list[Plano]
) -> list[tuple[float, float, Plano]]:
    ordenados = sorted(planos, key=lambda p: p.inicio)
    segmentos: list[tuple[float, float, Plano]] = []
    for de, ate in faixas:
        cursor = de
        for plano in ordenados:
            a, b = max(cursor, plano.inicio), min(ate, plano.fim)
            if b <= a:
                continue
            if a > cursor:
                segmentos.append((cursor, a, Plano(cursor, a)))
            segmentos.append((a, b, plano))
            cursor = b
        if cursor < ate:
            segmentos.append((cursor, ate, Plano(cursor, ate)))
    return segmentos


def detectar_cortes(video: Path, inicio: float, fim: float) -> list[float]:
    log = saida_ffmpeg(
        [
            "-ss", f"{inicio:.3f}", "-t", f"{fim - inicio:.3f}", "-i", str(video), "-an",
            "-vf", f"select='gt(scene,{LIMIAR_DE_CENA})',showinfo", "-f", "null", "-",
        ]
    )
    return [inicio + float(t) for t in re.findall(r"pts_time:([\d.]+)", log)]


def limites_de_cena(video: Path, inicio: float, fim: float) -> list[float]:
    """[inicio, cortes de câmera..., fim], sem cenas menores que PLANO_MINIMO."""
    limites = [inicio]
    for corte in detectar_cortes(video, inicio, fim):
        if corte - limites[-1] >= PLANO_MINIMO and fim - corte >= PLANO_MINIMO:
            limites.append(corte)
    limites.append(fim)
    return limites


def planos_iniciais(video: Path, inicio: float, fim: float) -> list[Plano]:
    limites = limites_de_cena(video, inicio, fim)
    return [Plano(a, b) for a, b in zip(limites, limites[1:])]


def gravar_planos(pasta: Path, planos: list[Plano]) -> None:
    conteudo = {"planos": [plano_em_dict(p) for p in planos]}
    gravar_atomico(Path(pasta) / "enquadramento.json", json.dumps(conteudo, indent=2))


def ler_planos(pasta: Path) -> list[Plano]:
    arquivo = Path(pasta) / "enquadramento.json"
    if not arquivo.exists():
        return []
    return [Plano(**p) for p in json.loads(arquivo.read_text("utf-8"))["planos"]]


def marcas_do_plano(plano: Plano, largura: int, altura: int) -> tuple[str, list[tuple[str, list, str]]]:
    """O que a folha desenha num plano suave ou de tela dividida, em pixels de um quadro `largura` x `altura`:
    (etiqueta, [(tipo, pontos, cor)]). "retangulo" é o recorte no meio do plano; "linha", o trajeto do centro."""
    if plano.divisao:
        alvos = [(p, PROPORCAO_PAINEL, cor) for p, cor in zip(paineis(plano), CORES_PAINEIS)]
        etiqueta = "DIVIDIDA SUAVE" if any(p.trajeto for p, _, _ in alvos) else "DIVIDIDA"
    elif plano.trajeto:
        alvos, etiqueta = [(plano, PROPORCAO_FAIXA, COR_SUAVE)], "SUAVE"
    else:
        return "", []
    meio = (plano.inicio + plano.fim) / 2
    marcas: list[tuple[str, list, str]] = []
    for alvo, proporcao, cor in alvos:
        cx, cy = centro_em(alvo, meio)
        w, h, x, y = recorte(replace(alvo, x=cx, y=cy), largura, altura, proporcao)
        marcas.append(("retangulo", [x, y, x + w, y + h], cor))
        if alvo.trajeto:
            marcas.append(("linha", [(px * largura, py * altura) for _, px, py in alvo.trajeto], cor))
    return etiqueta, marcas


def _desenhar_marcas(desenho: ImageDraw.ImageDraw, plano: Plano, x: int, y: int, largura: int, altura: int, fonte):
    etiqueta, marcas = marcas_do_plano(plano, largura, altura)
    for tipo, pontos, cor in marcas:
        if tipo == "retangulo":
            x0, y0, x1, y1 = pontos
            desenho.rectangle((x + x0, y + y0, x + x1, y + y1), outline=cor, width=2)
        else:
            caminho = [(x + px, y + py) for px, py in pontos]
            desenho.line(caminho, fill=cor, width=3)
            fx, fy = caminho[-1]
            desenho.ellipse((fx - 4, fy - 4, fx + 4, fy + 4), fill=cor)
    if etiqueta:
        desenho.text((x + LARGURA_MINIATURA - 8, y + 8), etiqueta, font=fonte, fill=COR_SUAVE, anchor="ra",
                     stroke_width=2, stroke_fill="#000000")


def gerar_folha(
    video: Path,
    planos: list[Plano],
    saida: Path,
    rotulos: list[str] | None = None,
    caixas: list[tuple[float, float, float, float] | None] | None = None,
) -> Path:
    """Um quadro por plano. `rotulos[i]` substitui o número do plano; `caixas[i]` é o
    rosto escolhido (centro x, y, largura, altura, de 0 a 1), desenhado como caixa. Plano suave
    ou de tela dividida ganha etiqueta, recorte(s) e trajeto (`marcas_do_plano`)."""
    altura = LARGURA_MINIATURA * 9 // 16
    linhas = (len(planos) + COLUNAS - 1) // COLUNAS
    folha = Image.new("RGB", (COLUNAS * LARGURA_MINIATURA, linhas * altura), "#000000")
    desenho = ImageDraw.Draw(folha)
    fonte = ImageFont.truetype(str(FONTES / "Montserrat-Bold.ttf"), 22)
    pequena = ImageFont.truetype(str(FONTES / "Montserrat-Bold.ttf"), 16)
    with tempfile.TemporaryDirectory() as pasta:
        for i, plano in enumerate(planos):
            quadro = Path(pasta) / f"{i}.jpg"
            meio = (plano.inicio + plano.fim) / 2
            executar_ffmpeg(
                ["-y", "-ss", f"{meio:.3f}", "-i", str(video), "-frames:v", "1",
                 "-vf", f"scale={LARGURA_MINIATURA}:-2", str(quadro)]
            )
            x, y = i % COLUNAS * LARGURA_MINIATURA, i // COLUNAS * altura
            with Image.open(quadro) as imagem:
                folha.paste(imagem, (x, y))
                largura_q, altura_q = imagem.size
            caixa = caixas[i] if caixas and i < len(caixas) else None
            if caixa is not None:
                cx, cy, w, h = caixa
                desenho.rectangle(
                    (x + (cx - w / 2) * largura_q, y + (cy - h / 2) * altura_q,
                     x + (cx + w / 2) * largura_q, y + (cy + h / 2) * altura_q),
                    outline="#FFEE00", width=3,
                )
            _desenhar_marcas(desenho, plano, x, y, largura_q, altura_q, pequena)
            duracao = plano.fim - plano.inicio
            desenho.text((x + 8, y + 6), f"{i + 1} ({duracao:.1f}s)", font=fonte, fill="#FFEE00",
                         stroke_width=2, stroke_fill="#000000")
            if rotulos and i < len(rotulos):
                texto = rotulos[i]
                while len(texto) > 1 and desenho.textlength(texto, font=pequena) > LARGURA_MINIATURA - 16:
                    texto = texto[:-2].rstrip() + "…"
                desenho.text((x + 8, y + altura - 28), texto, font=pequena, fill="#FFFFFF",
                             stroke_width=2, stroke_fill="#000000")
    folha.save(saida, quality=85)
    return Path(saida)
