from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from esteira.caminhos import FONTES, LOGO

LARGURA = 1080
ALTURA = 1920
MARGEM = 80
LARGURA_TEXTO = LARGURA - 2 * MARGEM
ALTURA_TEXTO = 1000
TOPO_TEXTO = 620
TAMANHOS = range(96, 31, -4)
ARQUIVO_FONTE = FONTES / "Montserrat-Bold.ttf"


def linha_fonte(veiculo: str, data: str) -> str:
    return f"Fonte: {veiculo}, {data}"


def _quebrar(texto: str, fonte: ImageFont.FreeTypeFont) -> list[str]:
    linhas: list[str] = []
    atual = ""
    for palavra in texto.split():
        tentativa = f"{atual} {palavra}".strip()
        if fonte.getlength(tentativa) <= LARGURA_TEXTO:
            atual = tentativa
        else:
            linhas.append(atual)
            atual = palavra
    return linhas + [atual]


def ajustar_manchete(manchete: str) -> tuple[list[str], ImageFont.FreeTypeFont]:
    for tamanho in TAMANHOS:
        fonte = ImageFont.truetype(str(ARQUIVO_FONTE), tamanho)
        linhas = _quebrar(manchete, fonte)
        if len(linhas) * tamanho * 1.25 <= ALTURA_TEXTO and all(
            fonte.getlength(l) <= LARGURA_TEXTO for l in linhas
        ):
            return linhas, fonte
    return linhas, fonte


def gerar_cartao(manchete: str, veiculo: str, data: str, saida: Path) -> Path:
    imagem = Image.new("RGB", (LARGURA, ALTURA), "#000000")
    if LOGO.exists():
        logo = Image.open(LOGO).convert("RGBA")
        logo.thumbnail((560, 560))
        imagem.paste(logo, ((LARGURA - logo.width) // 2, 120), logo)

    desenho = ImageDraw.Draw(imagem)
    linhas, fonte = ajustar_manchete(manchete)
    y = TOPO_TEXTO
    for linha in linhas:
        desenho.text((MARGEM, y), linha, font=fonte, fill="#FFFFFF")
        y += int(fonte.size * 1.25)
    menor = ImageFont.truetype(str(ARQUIVO_FONTE), 36)
    desenho.text((MARGEM, y + 40), linha_fonte(veiculo, data), font=menor, fill="#B8C4D6")
    imagem.save(saida)
    return Path(saida)
