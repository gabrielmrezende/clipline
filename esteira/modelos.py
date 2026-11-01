from dataclasses import dataclass


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
