from PIL import Image, ImageDraw

from esteira.imagens import PROPORCAO_TELA_CHEIA, prefixo_tempo, preparar_foto


def test_proporcao():
    assert PROPORCAO_TELA_CHEIA == 1.5


def test_preparar_foto_vertical(tmp_path):
    Image.new("RGB", (600, 1200), (10, 200, 10)).save(tmp_path / "v.png")
    saida = preparar_foto(tmp_path / "v.png", tmp_path / "v.jpg")
    with Image.open(saida) as foto:
        assert foto.size == (1080, 1920) and foto.format == "JPEG" and foto.mode == "RGB"


def test_preparar_foto_horizontal_sem_cortar(tmp_path):
    original = Image.new("RGB", (1600, 900), (255, 255, 255))
    ImageDraw.Draw(original).rectangle((0, 0, 1599, 899), outline=(255, 0, 0), width=12)
    original.save(tmp_path / "h.png")
    with Image.open(preparar_foto(tmp_path / "h.png", tmp_path / "h.jpg")) as foto:
        assert foto.size == (1080, 1920)
        topo = (1920 - 607) // 2
        for y in range(topo + 10, topo + 597, 50):
            for x in (0, 1079):
                r, g, b = foto.getpixel((x, y))
                assert r > 180 and g < 90 and b < 90, (x, y, (r, g, b))


def test_preparar_foto_paleta_vira_rgb(tmp_path):
    Image.new("P", (900, 900)).save(tmp_path / "p.png")
    with Image.open(preparar_foto(tmp_path / "p.png", tmp_path / "p.jpg")) as foto:
        assert foto.mode == "RGB" and foto.size == (1080, 1920)


def test_prefixo_tempo():
    assert prefixo_tempo(72.4) == "0112"
    assert prefixo_tempo(5) == "0005"
