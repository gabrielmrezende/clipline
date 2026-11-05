import pytest

from esteira.rostos import Deteccao, agrupar, cenas_com_rostos, filtrar


def _det(tempo, x=0.5, y=0.5, h=0.2, assinatura=(1.0, 0.0)):
    return Deteccao(tempo, x, y, h, h, list(assinatura))


def test_filtrar_descarta_fraco_e_pequeno():
    brutas = [
        (0.0, (100, 100, 100, 100), 0.7, [1.0, 0.0]),  # score baixo
        (0.5, (100, 100, 40, 40), 0.95, [1.0, 0.0]),  # altura 0,04
        (1.0, (100, 100, 200, 200), 0.9, [1.0, 0.0]),  # fica
    ]
    resultado = filtrar(brutas, 1000, 1000)
    assert [d.tempo for d in resultado] == [1.0]
    assert resultado[0].altura == pytest.approx(0.2)


def test_filtrar_normaliza_centro():
    [d] = filtrar([(2.0, (100, 50, 200, 300), 0.9, [1.0])], 1000, 1000)
    assert d.x == pytest.approx(0.2)
    assert d.y == pytest.approx(0.2)
    assert d.largura == pytest.approx(0.2)
    assert d.altura == pytest.approx(0.3)


def test_agrupar_mesma_pessoa():
    dets = [_det(0.0), _det(0.5), _det(1.0, assinatura=(0.0, 1.0))]
    pessoas, conhecidas = agrupar(dets, {})
    assert pessoas[0] == pessoas[1]
    assert pessoas[2] != pessoas[0]
    assert set(conhecidas) == set(pessoas)


def test_agrupar_usa_conhecidas():
    conhecidas = {"P1": [0.0, 1.0], "P2": [1.0, 0.1]}
    pessoas, atualizadas = agrupar([_det(0.0, assinatura=(3.0, 0.2))], conhecidas)
    assert pessoas == ["P2"]
    assert set(atualizadas) == {"P1", "P2"}


def test_cenas_presenca_minima():
    dets = [_det(0.0, assinatura=(1, 0))] + [_det(t, assinatura=(0, 1)) for t in (0.0, 0.5, 1.0, 1.5)]
    pessoas = ["P1", "P2", "P2", "P2", "P2"]
    [cena] = cenas_com_rostos(dets, pessoas, [0.0, 2.0])
    assert [r.pessoa for r in cena.rostos] == ["P2"]  # P1 em 1 de 4 amostras


def test_cenas_separa_por_limites_e_faz_media():
    dets = [_det(0.0, x=0.2), _det(0.5, x=0.4)] + [_det(t, x=0.8) for t in (2.0, 2.5)]
    cenas = cenas_com_rostos(dets, ["P1"] * 4, [0.0, 2.0, 3.0])
    assert [(c.inicio, c.fim) for c in cenas] == [(0.0, 2.0), (2.0, 3.0)]
    assert cenas[0].rostos[0].x == pytest.approx(0.3)
    assert cenas[1].rostos[0].x == pytest.approx(0.8)


def test_detectar_com_detector_falso(tmp_path, monkeypatch):
    from PIL import Image

    from esteira import rostos

    pasta = tmp_path / "quadros"
    pasta.mkdir()

    def falso_ffmpeg(args, cwd=None):
        for i in range(1, 5):
            Image.new("RGB", (640, 360)).save(pasta / f"q{i:05d}.jpg")

    class FalsaPasta:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return str(pasta)

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(rostos, "executar_ffmpeg", falso_ffmpeg)
    monkeypatch.setattr(rostos.tempfile, "TemporaryDirectory", FalsaPasta)
    formatos = []

    def detector(quadro):
        formatos.append(quadro.shape)
        return [((64, 36, 128, 72), 0.9, [1.0, 0.0])]

    dets = rostos.detectar(tmp_path / "v.mp4", 10.0, 12.0, detector=detector)
    assert [d.tempo for d in dets] == [10.0, 10.5, 11.0, 11.5]
    assert dets[0].altura == pytest.approx(0.2)
    assert formatos[0] == (360, 640, 3)


def _real_disponivel():
    try:
        import cv2  # noqa: F401
    except ImportError:
        return False
    from esteira import rostos

    return all((rostos.MODELOS / n).exists() for n in (rostos.MODELO_DETECTOR, rostos.MODELO_RECONHECEDOR))


@pytest.mark.skipif(not _real_disponivel(), reason="sem opencv ou sem os modelos .onnx")
def test_detector_real_imagem_sem_rosto():
    import numpy as np

    from esteira.rostos import _detector_opencv

    assert _detector_opencv()(np.zeros((360, 640, 3), dtype=np.uint8)) == []
