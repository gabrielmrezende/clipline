import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from esteira.legenda import _chave
from esteira.modelos import Cue
from esteira.planos import Plano

NOME_ARQUIVO = "montagem.json"
TOLERANCIA = 0.05
IMAGEM_MINIMA = 2.0
IMAGEM_MAXIMA = 5.0
VOLUME_MINIMO = -22.0
VOLUME_MAXIMO = -18.0


@dataclass
class Imagem:
    inicio: float
    fim: float
    arquivo: str
    licenca: str = ""


@dataclass
class Musica:
    arquivo: str
    volume_db: float = -20.0


@dataclass
class Receita:
    faixas: list[tuple[float, float]]
    planos: list[Plano]
    legenda: list[Cue]
    imagens: list[Imagem] = field(default_factory=list)
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
        imagens=[Imagem(**i) for i in dados.get("imagens", [])],
        musica=Musica(**musica) if musica else None,
        encerramento=dados.get("encerramento", True),
        versao=dados.get("versao", 1),
    )


def validar_receita(receita: Receita, pasta: Path) -> list[str]:
    problemas: list[str] = []
    duracao = duracao_principal(receita)
    numeradas = list(enumerate(receita.imagens, 1))
    for n, imagem in numeradas:
        if imagem.fim > duracao + TOLERANCIA:
            problemas.append(f"imagem {n} passa do fim do corte")
        if not IMAGEM_MINIMA - TOLERANCIA <= imagem.fim - imagem.inicio <= IMAGEM_MAXIMA + TOLERANCIA:
            problemas.append(f"imagem {n} fora de 2 a 5 segundos")
        if not (Path(pasta) / imagem.arquivo).exists():
            problemas.append(f"imagem {n} não encontrada: {imagem.arquivo}")
    ordenadas = sorted(numeradas, key=lambda par: par[1].inicio)
    for (n, a), (m, b) in zip(ordenadas, ordenadas[1:]):
        if b.inicio < a.fim - TOLERANCIA:
            problemas.append(f"imagens {n} e {m} se sobrepõem")
    if receita.musica:
        if not Path(receita.musica.arquivo).exists():
            problemas.append("música não encontrada")
        if not VOLUME_MINIMO <= receita.musica.volume_db <= VOLUME_MAXIMO:
            problemas.append("volume da música fora de -22 a -18 dB")
    for n, cue in enumerate(receita.legenda, 1):
        if cue.destaque is None:
            continue
        palavras = {_chave(p) for linha in cue.linhas for p in linha.split()}
        if _chave(cue.destaque) not in palavras:
            problemas.append(f"destaque '{cue.destaque}' não está na tela {n}")
    return problemas
