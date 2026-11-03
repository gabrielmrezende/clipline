from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from esteira.cartao import ARQUIVO_FONTE
from esteira.render import PROPORCAO_TELA_CHEIA
from esteira.wikimedia import Candidata

COLUNAS = 3
LINHAS = 2
CELULA = 400
LEGENDA = 70
ALTURA_CABECALHO = 80
LARGURA_FOLHA = COLUNAS * CELULA
ALTURA_FOLHA = ALTURA_CABECALHO + LINHAS * (CELULA + LEGENDA)
MAXIMO_LEGENDA = 45
QUALIDADE_JPEG = 85
FUNDO = (24, 24, 24)
CINZA = (90, 90, 90)
BRANCO = (255, 255, 255)
DESTAQUE = (230, 40, 40)


def _fonte(tamanho: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(ARQUIVO_FONTE), tamanho)


def _truncar(texto: str, maximo: int) -> str:
    return texto if len(texto) <= maximo else texto[: maximo - 1].rstrip() + "…"


def _texto_ajustado(desenho: ImageDraw.ImageDraw, texto: str, tamanho: int, largura: int) -> ImageFont.FreeTypeFont:
    fonte = _fonte(tamanho)
    while tamanho > 10 and desenho.textlength(texto, font=fonte) > largura:
        tamanho -= 1
        fonte = _fonte(tamanho)
    return fonte


def _abrir_miniatura(caminho: Path | None) -> Image.Image | None:
    if caminho is None:
        return None
    try:
        with Image.open(caminho) as original:
            miniatura = original.convert("RGB")
    except (OSError, ValueError):
        return None
    miniatura.thumbnail((CELULA, CELULA))
    return miniatura


def _orientacao(candidata: Candidata) -> str:
    vertical = candidata.largura > 0 and candidata.altura / candidata.largura >= PROPORCAO_TELA_CHEIA
    return "vertical" if vertical else "horizontal"


def _desenhar_celula(folha: Image.Image, desenho: ImageDraw.ImageDraw, indice: int, candidata: Candidata, caminho: Path | None) -> None:
    x = (indice % COLUNAS) * CELULA
    y = ALTURA_CABECALHO + (indice // COLUNAS) * (CELULA + LEGENDA)
    miniatura = _abrir_miniatura(caminho)
    if miniatura is None:
        desenho.rectangle((x + 4, y + 4, x + CELULA - 5, y + CELULA - 5), fill=CINZA)
        fonte = _fonte(26)
        texto = "sem miniatura"
        desenho.text((x + CELULA / 2, y + CELULA / 2), texto, font=fonte, fill=BRANCO, anchor="mm")
    else:
        folha.paste(miniatura, (x + (CELULA - miniatura.width) // 2, y + (CELULA - miniatura.height) // 2))
    desenho.rectangle((x + 8, y + 8, x + 78, y + 78), fill=DESTAQUE)
    desenho.text((x + 43, y + 43), str(indice + 1), font=_fonte(52), fill=BRANCO, anchor="mm")
    desenho.text((x + 10, y + CELULA + 6), f"{indice + 1} · {_orientacao(candidata)}", font=_fonte(24), fill=BRANCO)
    credito = _truncar(f"{candidata.autor} · {candidata.licenca}", MAXIMO_LEGENDA)
    fonte_credito = _texto_ajustado(desenho, credito, 20, CELULA - 20)
    desenho.text((x + 10, y + CELULA + 38), credito, font=fonte_credito, fill=(200, 200, 200))


def montar_folha(titulo: str, candidatas: list[Candidata], miniaturas: list[Path | None], saida: Path) -> Path:
    folha = Image.new("RGB", (LARGURA_FOLHA, ALTURA_FOLHA), FUNDO)
    desenho = ImageDraw.Draw(folha)
    cabecalho = _texto_ajustado(desenho, titulo, 34, LARGURA_FOLHA - 40)
    desenho.text((20, ALTURA_CABECALHO / 2), titulo, font=cabecalho, fill=BRANCO, anchor="lm")
    if not candidatas:
        desenho.text((LARGURA_FOLHA / 2, ALTURA_FOLHA / 2), "nenhuma", font=_fonte(60), fill=BRANCO, anchor="mm")
    for indice, candidata in enumerate(candidatas[: COLUNAS * LINHAS]):
        caminho = miniaturas[indice] if indice < len(miniaturas) else None
        _desenhar_celula(folha, desenho, indice, candidata, caminho)
    saida.parent.mkdir(parents=True, exist_ok=True)
    folha.save(saida, "JPEG", quality=QUALIDADE_JPEG)
    return saida
