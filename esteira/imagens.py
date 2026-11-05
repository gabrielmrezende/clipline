from pathlib import Path

from PIL import Image, ImageFilter, ImageOps

PROPORCAO_TELA_CHEIA = 1.5
LARGURA = 1080
ALTURA = 1920
DESFOQUE = 40
QUALIDADE_JPEG = 90


def preparar_foto(origem: Path, saida: Path) -> Path:
    """Foto vertical cobre a tela; horizontal ou quadrada fica inteira sobre ela mesma desfocada."""
    with Image.open(origem) as aberta:
        foto = ImageOps.exif_transpose(aberta).convert("RGB")
    tela = (LARGURA, ALTURA)
    if foto.height / foto.width >= PROPORCAO_TELA_CHEIA:
        final = ImageOps.fit(foto, tela, Image.Resampling.LANCZOS)
    else:
        final = ImageOps.fit(foto, tela, Image.Resampling.LANCZOS).filter(ImageFilter.GaussianBlur(DESFOQUE))
        altura = round(LARGURA * foto.height / foto.width)
        frente = foto.resize((LARGURA, altura), Image.Resampling.LANCZOS)
        final.paste(frente, (0, (ALTURA - altura) // 2))
    final.save(saida, "JPEG", quality=QUALIDADE_JPEG)
    return Path(saida)


def prefixo_tempo(segundos: float) -> str:
    """72.4 -> "0112" (minutos e segundos do início no corte.mp4)."""
    minutos, resto = divmod(int(segundos), 60)
    return f"{minutos:02d}{resto:02d}"
