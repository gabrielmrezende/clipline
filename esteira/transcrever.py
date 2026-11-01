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

    for indice, modo in enumerate(MODOS):
        try:
            modelo = criar_modelo(modo)
            segmentos, _ = modelo.transcribe(
                str(video),
                language="pt",
                word_timestamps=True,
                vad_filter=True,
                initial_prompt=", ".join(nomes)[:200] or None,
            )
            blocos = [
                [Palavra(p.word.strip(), p.start, p.end) for p in s.words] for s in segmentos
            ]
            break
        except RuntimeError as erro:
            if "out of memory" not in str(erro).lower() or indice == len(MODOS) - 1:
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
