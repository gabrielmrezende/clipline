from dataclasses import dataclass, field


@dataclass
class Palavra:
    texto: str
    inicio: float
    fim: float


@dataclass
class Corte:
    numero: int
    titulo: str
    inicio: float
    fim: float
    clima: str
    instagram: bool = False
    data: str = ""


@dataclass
class Edicao:
    inicio: float
    fim: float
    motivo: str
    texto: str


@dataclass
class Cue:
    inicio: float
    fim: float
    linhas: list[str]
    destaque: str | None = None
    # [início, fim] de cada palavra das linhas, na ordem; usado pela legenda "palavra". Fora da comparação:
    # duas telas com o mesmo texto e tempo continuam iguais.
    palavras: list[list[float]] | None = field(default=None, compare=False)
