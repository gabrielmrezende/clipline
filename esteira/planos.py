import json
import re
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from esteira.caminhos import FONTES
from esteira.midia import executar_ffmpeg, saida_ffmpeg

PROPORCAO_FAIXA = 1080 / 1036
LIMIAR_DE_CENA = 0.1
PLANO_MINIMO = 0.25
LARGURA_MINIATURA = 400
COLUNAS = 4


@dataclass
class Plano:
    inicio: float
    fim: float
    x: float = 0.5
    y: float = 0.5
    zoom: float = 1.0


def _par(valor: float) -> int:
    return int(valor) // 2 * 2


def recorte(plano: Plano, largura: int, altura: int) -> tuple[int, int, int, int]:
    h = min(_par(altura / plano.zoom), altura)
    w = min(_par(h * PROPORCAO_FAIXA), largura)
    x = min(max(round(largura * plano.x - w / 2), 0), largura - w)
    y = min(max(round(altura * plano.y - h / 2), 0), altura - h)
    return w, h, x, y


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


def planos_iniciais(video: Path, inicio: float, fim: float) -> list[Plano]:
    limites = [inicio]
    for corte in detectar_cortes(video, inicio, fim):
        if corte - limites[-1] >= PLANO_MINIMO and fim - corte >= PLANO_MINIMO:
            limites.append(corte)
    limites.append(fim)
    return [Plano(a, b) for a, b in zip(limites, limites[1:])]


def gravar_planos(pasta: Path, planos: list[Plano]) -> None:
    conteudo = {"planos": [asdict(p) for p in planos]}
    (Path(pasta) / "enquadramento.json").write_text(json.dumps(conteudo, indent=2), "utf-8")


def ler_planos(pasta: Path) -> list[Plano]:
    arquivo = Path(pasta) / "enquadramento.json"
    if not arquivo.exists():
        return []
    return [Plano(**p) for p in json.loads(arquivo.read_text("utf-8"))["planos"]]


def gerar_folha(video: Path, planos: list[Plano], saida: Path) -> Path:
    altura = LARGURA_MINIATURA * 9 // 16
    linhas = (len(planos) + COLUNAS - 1) // COLUNAS
    folha = Image.new("RGB", (COLUNAS * LARGURA_MINIATURA, linhas * altura), "#000000")
    desenho = ImageDraw.Draw(folha)
    fonte = ImageFont.truetype(str(FONTES / "Montserrat-Bold.ttf"), 22)
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
            duracao = plano.fim - plano.inicio
            desenho.text((x + 8, y + 6), f"{i + 1} ({duracao:.1f}s)", font=fonte, fill="#FFEE00",
                         stroke_width=2, stroke_fill="#000000")
    folha.save(saida, quality=85)
    return Path(saida)
