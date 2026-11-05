"""Detecção e reconhecimento de rostos: onde cada pessoa está em cada cena e
quem é quem entre cenas diferentes (YuNet detecta, SFace reconhece)."""

import math
import tempfile
from dataclasses import dataclass
from pathlib import Path

from esteira.caminhos import AUTOMACAO
from esteira.enquadrar import Cena, Rosto
from esteira.midia import executar_ffmpeg

PASSO = 0.5
SCORE_MINIMO = 0.8
ALTURA_MINIMA = 0.06  # fração da altura do quadro
LIMIAR_MESMA_PESSOA = 0.363  # cosseno SFace
PRESENCA_MINIMA = 0.5
LARGURA_QUADRO = 640
MODELOS = AUTOMACAO / "modelos"
MODELO_DETECTOR = "face_detection_yunet_2023mar.onnx"
MODELO_RECONHECEDOR = "face_recognition_sface_2021dec.onnx"


@dataclass
class Deteccao:
    tempo: float
    x: float  # centro da caixa, de 0 a 1
    y: float
    largura: float
    altura: float
    assinatura: list[float]


def _detector_opencv():
    import cv2

    yunet = cv2.FaceDetectorYN.create(str(MODELOS / MODELO_DETECTOR), "", (320, 320), SCORE_MINIMO)
    sface = cv2.FaceRecognizerSF.create(str(MODELOS / MODELO_RECONHECEDOR), "")

    def detector(quadro):  # quadro RGB (numpy)
        bgr = cv2.cvtColor(quadro, cv2.COLOR_RGB2BGR)
        altura, largura = bgr.shape[:2]
        yunet.setInputSize((largura, altura))
        _, rostos = yunet.detect(bgr)
        saida = []
        for rosto in [] if rostos is None else rostos:
            assinatura = sface.feature(sface.alignCrop(bgr, rosto)).flatten().tolist()
            x, y, w, h = (float(v) for v in rosto[:4])
            saida.append(((x, y, w, h), float(rosto[-1]), assinatura))
        return saida

    return detector


def detectar(video: Path, inicio: float, fim: float, detector=None) -> list[Deteccao]:
    """Um quadro a cada PASSO entre inicio e fim. `detector(quadro)` recebe o quadro
    RGB (numpy) e devolve [((x, y, w, h) em pixels, score, assinatura)]."""
    import numpy as np
    from PIL import Image

    if detector is None:
        detector = _detector_opencv()
    brutas = []
    largura = altura = 1
    with tempfile.TemporaryDirectory(prefix="rostos-") as pasta:
        pasta = Path(pasta)
        executar_ffmpeg([
            "-ss", f"{inicio:.3f}", "-t", f"{fim - inicio:.3f}", "-i", str(video),
            "-vf", f"fps={1 / PASSO},scale={LARGURA_QUADRO}:-2", "-q:v", "3",
            str(pasta / "q%05d.jpg"),
        ])
        for i, arquivo in enumerate(sorted(pasta.glob("q*.jpg"))):
            with Image.open(arquivo) as imagem:
                quadro = np.asarray(imagem.convert("RGB"))
            altura, largura = quadro.shape[:2]
            for caixa, score, assinatura in detector(quadro):
                brutas.append((inicio + i * PASSO, caixa, score, assinatura))
    return filtrar(brutas, largura, altura)


def filtrar(deteccoes_brutas, largura: int, altura: int) -> list[Deteccao]:
    resultado = []
    for tempo, (x, y, w, h), score, assinatura in deteccoes_brutas:
        if score < SCORE_MINIMO or h / altura < ALTURA_MINIMA:
            continue
        resultado.append(Deteccao(
            tempo, (x + w / 2) / largura, (y + h / 2) / altura,
            w / largura, h / altura, list(assinatura),
        ))
    return resultado


def _normalizar(v: list[float]) -> list[float]:
    norma = math.sqrt(sum(a * a for a in v))
    return [a / norma for a in v] if norma else [float(a) for a in v]


def _cosseno(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(_normalizar(a), _normalizar(b)))


def agrupar(deteccoes: list[Deteccao], conhecidas: dict[str, list[float]]):
    """Devolve (pessoa de cada detecção, assinaturas atualizadas). A assinatura da
    pessoa é a média das assinaturas normalizadas (a conhecida entra com peso 1)."""
    somas = {nome: ([float(a) for a in _normalizar(sig)], 1) for nome, sig in conhecidas.items()}
    atualizadas = {nome: list(sig) for nome, sig in conhecidas.items()}
    pessoas = []
    for det in deteccoes:
        escolhida, melhor = None, LIMIAR_MESMA_PESSOA
        for nome, sig in atualizadas.items():
            c = _cosseno(det.assinatura, sig)
            if c >= melhor:
                escolhida, melhor = nome, c
        if escolhida is None:
            n = 1
            while f"P{n}" in atualizadas:
                n += 1
            escolhida = f"P{n}"
            somas[escolhida] = ([0.0] * len(det.assinatura), 0)
        soma, quantidade = somas[escolhida]
        soma = [s + a for s, a in zip(soma, _normalizar(det.assinatura))]
        quantidade += 1
        somas[escolhida] = (soma, quantidade)
        atualizadas[escolhida] = [s / quantidade for s in soma]
        pessoas.append(escolhida)
    return pessoas, atualizadas


def cenas_com_rostos(deteccoes: list[Deteccao], pessoas: list[str], limites: list[float]) -> list[Cena]:
    """Por cena (entre limites consecutivos), um Rosto médio por pessoa que aparece
    em pelo menos metade das amostras (uma a cada PASSO) da cena."""
    cenas = []
    for inicio, fim in zip(limites, limites[1:]):
        dentro = [(d, p) for d, p in zip(deteccoes, pessoas) if inicio <= d.tempo < fim]
        amostras = max(1, round((fim - inicio) / PASSO))
        rostos = []
        for pessoa in dict.fromkeys(p for _, p in dentro):
            dets = [d for d, p in dentro if p == pessoa]
            if len({d.tempo for d in dets}) < PRESENCA_MINIMA * amostras:
                continue
            n = len(dets)
            rostos.append(Rosto(
                pessoa, sum(d.x for d in dets) / n, sum(d.y for d in dets) / n,
                sum(d.largura for d in dets) / n, sum(d.altura for d in dets) / n,
            ))
        cenas.append(Cena(inicio, fim, rostos))
    return cenas
