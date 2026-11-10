import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from esteira.legenda import _chave
from esteira.modelos import Cue
from esteira.planos import Plano

NOME_ARQUIVO = "montagem.json"
TOLERANCIA = 0.05
VOLUME_MINIMO = -30.0
VOLUME_MAXIMO = -18.0
VOLUME_PADRAO = -26.0


@dataclass(frozen=True)
class ImagemNoVideo:
    """Uma imagem sobreposta ao corte.mp4, nos tempos de tela (linha do tempo do corte)."""

    inicio: float
    fim: float
    arquivo: str  # relativo à pasta do corte: "imagens-sugeridas/<nome>"
    tipo: str = ""
    momento: str = ""  # chave do momento (MMSS-nome, pelo tempo proposto)
    modificado_ns: int = 0  # st_mtime_ns do arquivo na hora da escolha


@dataclass
class Musica:
    arquivo: str
    volume_db: float = VOLUME_PADRAO
    titulo: str = ""
    credito: str = ""


@dataclass
class Receita:
    faixas: list[tuple[float, float]]
    planos: list[Plano]
    legenda: list[Cue]
    musica: Musica | None = None
    encerramento: bool = True
    versao: int = 1


def duracao_principal(receita: Receita) -> float:
    return sum(fim - inicio for inicio, fim in receita.faixas)


def gravar_receita(pasta: Path, receita: Receita) -> None:
    texto = json.dumps(asdict(receita), ensure_ascii=False, indent=2)
    (Path(pasta) / NOME_ARQUIVO).write_text(texto, "utf-8")


def ler_receita(pasta: Path) -> Receita:
    dados = json.loads((Path(pasta) / NOME_ARQUIVO).read_text("utf-8"))
    musica = dados.get("musica")
    return Receita(
        faixas=[tuple(f) for f in dados["faixas"]],
        planos=[Plano(**p) for p in dados["planos"]],
        legenda=[Cue(**c) for c in dados["legenda"]],
        musica=Musica(**musica) if musica else None,
        encerramento=dados.get("encerramento", True),
        versao=dados.get("versao", 1),
    )


def validar_receita(receita: Receita, pasta: Path) -> list[str]:
    problemas: list[str] = []
    duracao = duracao_principal(receita)
    if receita.musica:
        if not Path(receita.musica.arquivo).exists():
            problemas.append("música não encontrada")
        if not VOLUME_MINIMO <= receita.musica.volume_db <= VOLUME_MAXIMO:
            problemas.append("volume da música fora de -30 a -18 dB")
    for n, cue in enumerate(receita.legenda, 1):
        if cue.fim > duracao + TOLERANCIA:
            problemas.append(f"tela {n} passa do fim do corte")
        if cue.destaque is None:
            continue
        palavras = {_chave(p) for linha in cue.linhas for p in linha.split()}
        if _chave(cue.destaque) not in palavras:
            problemas.append(f"destaque '{cue.destaque}' não está na tela {n}")
    return problemas
