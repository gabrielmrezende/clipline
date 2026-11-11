import gc
import inspect
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

from esteira.modelos import Palavra

MODOS = [
    ("large-v3", "cuda", "float16"),
    ("large-v3", "cuda", "int8_float16"),
    ("medium", "cuda", "int8_float16"),
]
FALTA_DE_MEMORIA = ("out of memory", "alloc_failed", "status_not_initialized")
LIMITE_PROMPT = 200  # caracteres do initial_prompt (o Whisper usa só o fim de um prompt longo)


def opcoes_de_nomes(transcribe, nomes: list[str]) -> dict:
    """O glossário inteiro vai em `hotwords` (faster-whisper >= 1.0.2); o `initial_prompt` leva o que couber.

    Antes, `", ".join(nomes)[:200]` cortava o glossário no meio de um nome e descartava o resto."""
    opcoes: dict = {}
    prompt, usados = "", 0
    for nome in nomes:
        candidato = f"{prompt}, {nome}" if prompt else nome
        if len(candidato) > LIMITE_PROMPT:
            break
        prompt, usados = candidato, usados + 1
    opcoes["initial_prompt"] = prompt or None
    try:
        aceita = "hotwords" in inspect.signature(transcribe).parameters
    except (TypeError, ValueError):
        aceita = False
    if aceita and nomes:
        opcoes["hotwords"] = ", ".join(nomes)
    return opcoes


def carregar_glossario(caminho: Path) -> list[str]:
    nomes: list[str] = []
    em_secao = False
    for linha in Path(caminho).read_text("utf-8").splitlines():
        linha = linha.strip()
        if linha.startswith("#"):
            em_secao = linha.startswith("## ")
        elif em_secao and linha and not linha.endswith("."):
            nomes += [n.strip() for n in linha.split(",") if n.strip()]
    return nomes


def _registrar_dlls_nvidia() -> None:
    """Só no Windows: lá as DLLs do CUDA instaladas pelo pip não entram sozinhas no caminho de busca."""
    if not hasattr(os, "add_dll_directory"):
        return
    raiz = Path(sys.prefix) / "Lib" / "site-packages"
    for pasta in ("nvidia/cublas/lib", "nvidia/cudnn/lib", "nvidia/cudnn/bin", "nvidia/cublas/bin"):
        caminho = raiz / pasta
        if caminho.exists():
            os.add_dll_directory(str(caminho))
            os.environ["PATH"] = f"{caminho}{os.pathsep}{os.environ['PATH']}"


def criar_whisper(modo: tuple[str, str, str]):
    _registrar_dlls_nvidia()
    from faster_whisper import WhisperModel

    nome, dispositivo, calculo = modo
    return WhisperModel(nome, device=dispositivo, compute_type=calculo)


def _tempo(segundos: float) -> str:
    s = int(segundos)
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def _gravar(caminho: Path, conteudo: str) -> None:
    temporario = caminho.with_suffix(caminho.suffix + ".tmp")
    temporario.write_text(conteudo, "utf-8")
    temporario.replace(caminho)


def transcrever(
    video: Path, pasta: Path, nomes: list[str], criar_modelo=criar_whisper, forcar: bool = False
) -> list[Palavra]:
    saida = Path(pasta) / "transcricao"
    arquivo = saida / "palavras.json"
    if arquivo.exists() and not forcar:
        raise FileExistsError(f"Transcrição já existe: {arquivo}")

    modelo = segmentos = None
    for indice, modo in enumerate(MODOS):
        modelo = segmentos = None
        gc.collect()
        try:
            modelo = criar_modelo(modo)
            segmentos, _ = modelo.transcribe(
                str(video),
                language="pt",
                word_timestamps=True,
                vad_filter=True,
                **opcoes_de_nomes(modelo.transcribe, nomes),
            )
            blocos = [
                [Palavra(p.word.strip(), p.start, p.end) for p in s.words] for s in segmentos
            ]
            break
        except RuntimeError as erro:
            mensagem = str(erro).lower()
            if not any(m in mensagem for m in FALTA_DE_MEMORIA) or indice == len(MODOS) - 1:
                raise

    saida.mkdir(parents=True, exist_ok=True)
    palavras = [p for bloco in blocos for p in bloco]
    linhas = [
        f"[{_tempo(b[0].inicio)}] " + " ".join(p.texto for p in b) for b in blocos if b
    ]
    _gravar(saida / "texto.md", "\n".join(linhas) + "\n")
    _gravar(arquivo, json.dumps([asdict(p) for p in palavras], ensure_ascii=False, indent=0))
    return palavras


def ler_palavras(pasta: Path) -> list[Palavra]:
    dados = json.loads((Path(pasta) / "transcricao" / "palavras.json").read_text("utf-8"))
    return [Palavra(**p) for p in dados]
