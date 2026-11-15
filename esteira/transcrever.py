import gc
import inspect
import json
import os
import sys
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path

from esteira.modelos import Palavra

MODOS = [
    ("large-v3", "cuda", "float16"),
    ("large-v3", "cuda", "int8_float16"),
    ("medium", "cuda", "int8_float16"),
]
# Sem GPU NVIDIA: int8 na CPU, com o medium (cabe em poucos GB de RAM) e o small se faltar memória.
MODOS_CPU = [
    ("medium", "cpu", "int8"),
    ("small", "cpu", "int8"),
]
DISPOSITIVOS = ("auto", "cuda", "cpu")
FALTA_DE_MEMORIA = ("out of memory", "alloc_failed", "status_not_initialized", "bad_alloc", "cannot allocate memory")
# A GPU aparece, mas falta a biblioteca do CUDA (cuBLAS/cuDNN) que o CTranslate2 carrega na hora de rodar: quem
# instalou só o pacote base, ou o driver sem o toolkit. No modo auto, isso recua para a CPU em vez de parar.
FALTA_DE_BIBLIOTECA = ("cublas", "cudnn", "cannot be loaded", "is not found", "cuda driver", "no cuda-capable")
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


def _cublas_carrega() -> bool:
    """O CTranslate2 só usa a GPU com o cuBLAS do CUDA 12. Ver a placa não basta: sem a biblioteca, ele quebra depois
    de baixar o modelo grande."""
    import ctypes

    nomes = ("cublas64_12.dll",) if os.name == "nt" else ("libcublas.so.12", "libcublas.so")
    for nome in nomes:
        try:
            ctypes.CDLL(nome)
            return True
        except OSError:
            continue
    return False


def cuda_disponivel() -> bool:
    """Há GPU NVIDIA que o faster-whisper (CTranslate2) consegue usar? Pergunta ao driver e confere o cuBLAS, sem
    carregar modelo."""
    _registrar_dlls_nvidia()
    try:
        import ctranslate2

        return ctranslate2.get_cuda_device_count() > 0 and _cublas_carrega()
    except Exception:  # sem o pacote, sem driver ou com DLL quebrada: trata como sem GPU
        return False


def escolher_modos(dispositivo: str, tem_cuda: Callable[[], bool] = cuda_disponivel) -> list[tuple[str, str, str]]:
    """Os modos a tentar, do mais pesado ao mais leve. `cuda` é o de sempre; `auto` recua para a CPU sem GPU."""
    if dispositivo not in DISPOSITIVOS:
        raise ValueError(f"dispositivo deve ser um destes: {', '.join(DISPOSITIVOS)}")
    if dispositivo == "cuda":
        return list(MODOS)
    if dispositivo == "auto" and tem_cuda():
        return list(MODOS) + list(MODOS_CPU)  # a CPU fica de reserva se a biblioteca do CUDA falhar na hora
    return list(MODOS_CPU)


def aviso_de_dispositivo(modos: list[tuple[str, str, str]]) -> str | None:
    nome, dispositivo, calculo = modos[0]
    if dispositivo != "cpu":
        return None
    return (f"Transcrição na CPU (modelo {nome}, {calculo}), sem GPU NVIDIA. É bem mais lenta que na GPU: "
            "um episódio longo pode levar horas.")


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
    video: Path, pasta: Path, nomes: list[str], criar_modelo=criar_whisper, forcar: bool = False,
    modos: list[tuple[str, str, str]] | None = None, idioma: str = "pt",
) -> list[Palavra]:
    """`modos`: o que `escolher_modos` devolve (sem ele, os de CUDA, como sempre); `idioma`: o código do Whisper."""
    modos = modos or MODOS
    saida = Path(pasta) / "transcricao"
    arquivo = saida / "palavras.json"
    if arquivo.exists() and not forcar:
        raise FileExistsError(f"Transcrição já existe: {arquivo}")

    modelo = segmentos = None
    indice = 0
    while indice < len(modos):
        modo = modos[indice]
        modelo = segmentos = None
        gc.collect()
        try:
            modelo = criar_modelo(modo)
            segmentos, _ = modelo.transcribe(
                str(video),
                language=idioma,
                word_timestamps=True,
                vad_filter=True,
                **opcoes_de_nomes(modelo.transcribe, nomes),
            )
            blocos = [
                [Palavra(p.word.strip(), p.start, p.end) for p in s.words] for s in segmentos
            ]
            break
        except (RuntimeError, MemoryError) as erro:
            mensagem = str(erro).lower()
            cpu = next((i for i in range(indice + 1, len(modos)) if modos[i][1] == "cpu"), None)
            if modo[1] == "cuda" and cpu is not None and any(m in mensagem for m in FALTA_DE_BIBLIOTECA):
                print(f"Aviso: a GPU não pôde ser usada ({str(erro).strip()[:120]}). Seguindo na CPU, bem mais "
                      "lenta; para usar a GPU, instale as bibliotecas do CUDA 12 (nvidia-cublas-cu12 e "
                      "nvidia-cudnn-cu12).", file=sys.stderr)
                indice = cpu
                continue
            memoria = isinstance(erro, MemoryError) or any(m in mensagem for m in FALTA_DE_MEMORIA)
            if not memoria or indice == len(modos) - 1:
                raise
            indice += 1

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
