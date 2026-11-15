import json
import os
import tempfile
from collections.abc import Callable
from pathlib import Path

from esteira.enquadrar import TrechoVoz
from esteira.midia import executar_ffmpeg
from esteira.transcrever import _gravar, _registrar_dlls_nvidia

MODELO = "pyannote/speaker-diarization-3.1"
MENSAGEM_SEM_TOKEN = (
    f"HF_TOKEN não definido: crie o token no Hugging Face, aceite os termos de {MODELO} "
    "e defina a variável de ambiente."
)


class ErroVozes(Exception):
    pass


def _sem_token(texto: str) -> str:
    token = os.environ.get("HF_TOKEN")
    return texto.replace(token, "***") if token else texto


def _erro_da_pipeline(acao: str, erro: Exception) -> ErroVozes:
    return ErroVozes(_sem_token(f"{acao}: {type(erro).__name__}: {erro}"))


DISPOSITIVOS = ("auto", "cuda", "cpu")
AVISO_CPU = "Separação de vozes na CPU, sem GPU NVIDIA: funciona, mas um episódio longo pode levar bem mais tempo."


def escolher_dispositivo(pedido: str, cuda_disponivel: bool) -> str:
    """`auto`: a GPU se houver (como sempre), senão a CPU. `cuda` sem GPU é erro, para não demorar sem avisar."""
    if pedido not in DISPOSITIVOS:
        raise ErroVozes(f"dispositivo deve ser um destes: {', '.join(DISPOSITIVOS)}")
    if pedido == "cuda" and not cuda_disponivel:
        raise ErroVozes("GPU NVIDIA não encontrada pelo torch: use --dispositivo cpu ou auto.")
    if pedido == "cpu" or not cuda_disponivel:
        return "cpu"
    return "cuda"


def criar_pipeline(
    dispositivo: str = "auto", avisar: Callable[[str], None] = print
) -> Callable[[Path, int], list[tuple[float, float, str]]]:
    token = os.environ.get("HF_TOKEN")
    if not token:
        raise ErroVozes(MENSAGEM_SEM_TOKEN)
    _registrar_dlls_nvidia()
    try:
        import torch
        from pyannote.audio import Pipeline
    except ImportError as erro:
        raise ErroVozes(
            'instale o extra vozes: python -m pip install -e ".[vozes]"'
        ) from erro
    alvo = escolher_dispositivo(dispositivo, torch.cuda.is_available())  # antes de baixar o modelo

    try:
        pipeline = Pipeline.from_pretrained(MODELO, use_auth_token=token)
    except Exception as erro:  # HTTP, rede, arquivo do modelo corrompido
        raise _erro_da_pipeline(f"não foi possível carregar {MODELO}", erro) from None
    if pipeline is None:
        raise ErroVozes(
            f"não foi possível carregar {MODELO}: aceite os termos de {MODELO} e de "
            "pyannote/segmentation-3.0 no Hugging Face e confira o HF_TOKEN."
        )
    if alvo == "cuda":
        pipeline.to(torch.device("cuda"))
    else:
        avisar(AVISO_CPU)

    def diarizar(wav: Path, pessoas: int) -> list[tuple[float, float, str]]:
        resultado = pipeline(str(wav), num_speakers=pessoas)
        return [(turno.start, turno.end, rotulo) for turno, _, rotulo in resultado.itertracks(yield_label=True)]

    return diarizar


def _arquivo(pasta: Path) -> Path:
    return Path(pasta) / "transcricao" / "vozes.json"


def separar_vozes(
    video: Path, pasta: Path, pessoas: int, criar=criar_pipeline, forcar: bool = False
) -> list[TrechoVoz]:
    arquivo = _arquivo(pasta)
    if arquivo.exists() and not forcar:
        raise FileExistsError(f"Vozes já existem: {arquivo}")
    diarizar = criar()
    with tempfile.TemporaryDirectory() as temporaria:
        wav = Path(temporaria) / "audio.wav"
        executar_ffmpeg(["-y", "-i", str(video), "-vn", "-ac", "1", "-ar", "16000", str(wav)])
        try:
            brutos = diarizar(wav, pessoas)
        except ErroVozes:
            raise
        except Exception as erro:  # falta de memória, erro do modelo
            raise _erro_da_pipeline("falha ao separar as vozes", erro) from None
    nomes: dict[str, str] = {}
    trechos = []
    for inicio, fim, rotulo in sorted(brutos, key=lambda t: t[0]):
        voz = nomes.setdefault(rotulo, f"V{len(nomes) + 1}")
        trechos.append(TrechoVoz(float(inicio), float(fim), voz))
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    dados = {"trechos": [{"inicio": t.inicio, "fim": t.fim, "voz": t.voz} for t in trechos]}
    _gravar(arquivo, json.dumps(dados, ensure_ascii=False, indent=2))
    return trechos


def ler_vozes(pasta: Path) -> list[TrechoVoz]:
    arquivo = _arquivo(pasta)
    if not arquivo.exists():
        raise ErroVozes(f"vozes.json não encontrado em {arquivo.parent}, rode o comando vozes")
    dados = json.loads(arquivo.read_text("utf-8"))
    return [TrechoVoz(t["inicio"], t["fim"], t["voz"]) for t in dados["trechos"]]
