"""Liga cada voz (diarização) a uma pessoa (reconhecimento de rosto).

A ligação usa só os planos fechados, em que aparece exatamente um rosto: quem fala
nesse plano é a pessoa que se vê. O resultado fica em `transcricao/pessoas.json`.
"""

import json
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from esteira.caminhos import FONTES
from esteira.enquadrar import Cena, Rosto, TrechoVoz
from esteira.midia import executar_ffmpeg
from esteira.transcrever import _gravar

ARQUIVO = "pessoas.json"
LARGURA_CELULA = 640
COLUNAS = 3
MARGEM_RECORTE = 1.0  # o recorte tem (1 + 2 * margem) vezes o lado maior do rosto
LARGURA_QUADRO = 1280  # largura do quadro extraído para o recorte
ALTURA_LEGENDA = 44
LIGACAO_MINIMA = 2.0  # segundos de close para uma voz poder ligar a uma pessoa
FRACAO_MINIMA = 0.10  # e fração mínima da fala total da voz


def ligar(vozes: list[TrechoVoz], cenas: list[Cena]) -> dict[str, str]:
    """Devolve {voz: pessoa}. Só cenas com exatamente 1 rosto contam.

    Soma, para cada par (voz, pessoa), o tempo em que a voz fala durante cenas em que só
    aquela pessoa aparece. Os pares são atendidos por soma decrescente; empate pela
    ordem do nome da voz e depois da pessoa. Um par só vale se a voz e a pessoa ainda
    estão livres, então duas vozes nunca ficam com a mesma pessoa: a de maior soma vence
    e a outra segue para a próxima pessoa livre, ou fica de fora do dicionário.
    Um par só pode ligar se a soma for >= LIGACAO_MINIMA segundos e >= FRACAO_MINIMA da
    fala total da voz, para um "vazamento" curto não ligar a voz à pessoa errada.
    """
    fala_total: dict[str, float] = {}
    for trecho in vozes:
        fala_total[trecho.voz] = fala_total.get(trecho.voz, 0.0) + (trecho.fim - trecho.inicio)
    somas: dict[tuple[str, str], float] = {}
    for cena in cenas:
        if len(cena.rostos) != 1:
            continue
        pessoa = cena.rostos[0].pessoa
        for trecho in vozes:
            dentro = min(cena.fim, trecho.fim) - max(cena.inicio, trecho.inicio)
            if dentro > 0:
                chave = (trecho.voz, pessoa)
                somas[chave] = somas.get(chave, 0.0) + dentro
    ligacao: dict[str, str] = {}
    usadas: set[str] = set()
    for (voz, pessoa), soma in sorted(somas.items(), key=lambda i: (-i[1], i[0][0], i[0][1])):
        if soma < LIGACAO_MINIMA - 1e-9 or soma < FRACAO_MINIMA * fala_total[voz] - 1e-9:
            continue
        if voz not in ligacao and pessoa not in usadas:
            ligacao[voz] = pessoa
            usadas.add(pessoa)
    return ligacao


def gravar_pessoas(
    pasta: Path,
    ligacao: dict[str, str],
    assinaturas: dict[str, list[float]],
    nomes: dict[str, str],
) -> None:
    (Path(pasta) / "transcricao").mkdir(parents=True, exist_ok=True)
    dados = {"ligacao": ligacao, "assinaturas": assinaturas, "nomes": nomes}
    _gravar(Path(pasta) / "transcricao" / ARQUIVO, json.dumps(dados, ensure_ascii=False, indent=1))


def ler_pessoas(
    pasta: Path,
) -> tuple[dict[str, str], dict[str, list[float]], dict[str, str]] | None:
    arquivo = Path(pasta) / "transcricao" / ARQUIVO
    if not arquivo.exists():
        return None
    dados = json.loads(arquivo.read_text("utf-8"))
    return dados["ligacao"], dados["assinaturas"], dados["nomes"]


def _recorte(imagem: Image.Image, rosto: Rosto) -> Image.Image:
    largura, altura = imagem.size
    lado = max(rosto.largura * largura, rosto.altura * altura) * (1 + 2 * MARGEM_RECORTE)
    esquerda = min(max(rosto.x * largura - lado / 2, 0), max(largura - lado, 0))
    topo = min(max(rosto.y * altura - lado / 2, 0), max(altura - lado, 0))
    caixa = (int(esquerda), int(topo), int(min(esquerda + lado, largura)), int(min(topo + lado, altura)))
    recorte = imagem.crop(caixa)
    recorte.thumbnail((LARGURA_CELULA, LARGURA_CELULA))
    return recorte


def folha_pessoas(
    video: Path,
    amostras: dict[str, tuple[float, Rosto]],
    ligacao: dict[str, str],
    tempo_de_fala: dict[str, float],
    nomes: dict[str, str],
    saida: Path,
) -> Path:
    """Uma célula por pessoa: recorte do rosto e a legenda `P2 = V1 · Nome · 312 s de fala`.

    `tempo_de_fala` é indexado por voz (ex.: {"V1": 312.0}), não por pessoa.
    """
    if not amostras:
        raise ValueError("nenhuma pessoa para a folha")
    voz_da_pessoa = {pessoa: voz for voz, pessoa in ligacao.items()}
    pessoas_ordenadas = sorted(amostras)
    linhas = max((len(pessoas_ordenadas) + COLUNAS - 1) // COLUNAS, 1)
    lado = LARGURA_CELULA
    folha = Image.new("RGB", (min(len(pessoas_ordenadas), COLUNAS) * lado, linhas * (lado + ALTURA_LEGENDA)), "#000000")
    desenho = ImageDraw.Draw(folha)
    fonte = ImageFont.truetype(str(FONTES / "Montserrat-Bold.ttf"), 26)
    with tempfile.TemporaryDirectory() as pasta:
        for i, pessoa in enumerate(pessoas_ordenadas):
            tempo, rosto = amostras[pessoa]
            quadro = Path(pasta) / f"{i}.jpg"
            executar_ffmpeg(
                ["-y", "-ss", f"{tempo:.3f}", "-i", str(video), "-frames:v", "1",
                 "-vf", f"scale={LARGURA_QUADRO}:-2", str(quadro)]
            )
            x, y = i % COLUNAS * lado, i // COLUNAS * (lado + ALTURA_LEGENDA)
            with Image.open(quadro) as imagem:
                folha.paste(_recorte(imagem.convert("RGB"), rosto), (x, y))
            voz = voz_da_pessoa.get(pessoa)
            partes = [f"{pessoa} = {voz or 'sem voz'}"]
            if nomes.get(pessoa):
                partes.append(nomes[pessoa])
            if voz:
                partes.append(f"{tempo_de_fala.get(voz, 0):.0f} s de fala")
            desenho.text((x + 8, y + lado + 6), " · ".join(partes), font=fonte, fill="#FFEE00",
                         stroke_width=2, stroke_fill="#000000")
    folha.save(saida, quality=85)
    return Path(saida)
