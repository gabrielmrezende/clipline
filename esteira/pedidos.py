import json
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path

from esteira.receita import TOLERANCIA

TIPOS = ("foto", "noticia", "ia")
ARQUIVO = "pedidos.json"
SECOES_DE_PESSOAS = ("Apresentadores", "Convidados", "Pessoas")
IMAGEM_MINIMA = 2.0
IMAGEM_MAXIMA = 5.0
MAXIMO_ESCOLHAS = 3


@dataclass
class Momento:
    inicio: float
    fim: float
    fala: str
    tipo: str
    nome: str
    busca: str = ""
    titulo: str = ""
    veiculo: str = ""
    data: str = ""
    prompt: str = ""
    candidatas: list[dict] = field(default_factory=list)
    escolhas: list[int] = field(default_factory=list)
    descartar: bool = False
    motivo: str = ""
    url: list[str] = field(default_factory=list)  # paralela a escolhas
    bytes: list[int | None] = field(default_factory=list)  # paralela a escolhas
    resumidas: list[int] = field(default_factory=list)  # escolhas do último resumo


def ler_pedidos(pasta: Path) -> list[Momento]:
    dados = json.loads((Path(pasta) / ARQUIVO).read_text("utf-8"))
    return [Momento(**_atualizar(item)) for item in dados["momentos"]]


def _atualizar(item: dict) -> dict:
    """Converte o formato antigo (escolha única, numero, url e bytes simples)."""
    item = dict(item)
    item.pop("numero", None)
    if "escolha" in item:
        escolha = item.pop("escolha")
        item.setdefault("escolhas", [escolha] if escolha else [])
    if not isinstance(item.get("url", []), list) or not isinstance(item.get("bytes", []), list):
        item["url"], item["bytes"] = [], []
    return item


def gravar_pedidos(pasta: Path, momentos: list[Momento]) -> None:
    texto = json.dumps({"momentos": [asdict(m) for m in momentos]}, ensure_ascii=False, indent=2)
    (Path(pasta) / ARQUIVO).write_text(texto, "utf-8")


def pessoas_do_glossario(caminho: Path) -> list[str]:
    pessoas: list[str] = []
    em_secao_de_pessoas = False
    for linha in Path(caminho).read_text("utf-8").splitlines():
        if linha.startswith("## "):
            em_secao_de_pessoas = any(p in linha for p in SECOES_DE_PESSOAS)
        elif em_secao_de_pessoas:
            texto = linha.strip().lstrip("-* ")
            if texto.endswith(".") and not re.search(r"[,;]", texto):
                continue
            for nome in re.split(r"[,;]", texto):
                nome = nome.strip().rstrip(".").strip()
                if nome:
                    pessoas.append(nome)
    return pessoas


def _normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return sem_acento.lower()


def _pessoa_citada(prompt: str, pessoas: list[str]) -> str | None:
    texto = _normalizar(prompt)
    for pessoa in pessoas:
        nome = _normalizar(pessoa)
        if nome and re.search(rf"\b{re.escape(nome)}\b", texto):
            return pessoa
    return None


def validar_pedidos(momentos: list[Momento], duracao: float, pessoas: list[str]) -> list[str]:
    erros = []
    for numero, m in enumerate(momentos, 1):
        if m.descartar:
            continue
        prefixo = f"momento {numero}"
        if m.tipo not in TIPOS:
            erros.append(f"{prefixo}: tipo inválido '{m.tipo}'")
        elif m.tipo == "foto" and not m.busca:
            erros.append(f"{prefixo}: foto sem busca")
        elif m.tipo == "noticia":
            for campo in ("titulo", "veiculo", "data"):
                if not getattr(m, campo):
                    erros.append(f"{prefixo}: notícia sem {campo}")
        elif m.tipo == "ia":
            if not m.prompt:
                erros.append(f"{prefixo}: ia sem prompt")
            else:
                pessoa = _pessoa_citada(m.prompt, pessoas)
                if pessoa:
                    erros.append(f"{prefixo}: prompt cita pessoa real ({pessoa})")
        if m.inicio < 0 or m.fim > duracao or m.inicio >= m.fim:
            erros.append(f"{prefixo}: fora do corte")
    return erros


def validar_escolhas(momentos: list[Momento]) -> list[str]:
    erros = []
    for numero, m in enumerate(momentos, 1):
        if m.descartar or m.tipo != "foto":
            continue
        e = m.escolhas
        if not (
            isinstance(e, list) and 1 <= len(e) <= MAXIMO_ESCOLHAS and len(set(e)) == len(e)
            and all(type(n) is int and 1 <= n <= len(m.candidatas) for n in e)
        ):
            erros.append(f"momento {numero}: escolhas inválidas")
    return erros


def ajustar_tempos(momentos: list[Momento], duracao: float) -> list[str]:
    mantidos = [m for m in momentos if not m.descartar]
    originais = [(m.inicio, m.fim) for m in mantidos]
    avisos: list[str] = []
    while True:
        novos = _ajustar_uma_vez(momentos, duracao)
        if not novos:
            return avisos
        avisos.extend(f"momento {i + 1} ({momentos[i].nome}) descartado: {momentos[i].motivo}" for i in novos)
        for m, (inicio, fim) in zip(mantidos, originais):
            if not m.descartar:
                m.inicio, m.fim = inicio, fim


def _ajustar_uma_vez(momentos: list[Momento], duracao: float) -> list[int]:
    descartados = []
    ordem = sorted((i for i, m in enumerate(momentos) if not m.descartar), key=lambda i: momentos[i].inicio)
    anterior_fim = 0.0
    for posicao, i in enumerate(ordem):
        m = momentos[i]
        proximo_inicio = momentos[ordem[posicao + 1]].inicio if posicao + 1 < len(ordem) else duracao
        m.fim = min(m.fim, m.inicio + IMAGEM_MAXIMA, proximo_inicio)
        if m.fim - m.inicio < IMAGEM_MINIMA:
            m.fim = max(m.fim, min(m.inicio + IMAGEM_MINIMA, proximo_inicio, duracao))
        if m.fim - m.inicio < IMAGEM_MINIMA:
            m.inicio = min(m.inicio, max(m.fim - IMAGEM_MINIMA, anterior_fim, 0))
        if m.fim - m.inicio < IMAGEM_MINIMA - TOLERANCIA:
            m.descartar = True
            m.motivo = f"não cabe em {IMAGEM_MINIMA:g} s"
            descartados.append(i)
            continue
        anterior_fim = m.fim
    return descartados
