"""Configuração do canal: `clipline.toml` na raiz do repositório (ao lado de pyproject.toml).

Tudo o que é decisão editorial ou identidade do canal, e não lógica, mora aqui. Sem o arquivo, valem os padrões,
que são exatamente os valores com que a esteira sempre rodou. Modelo comentado em `clipline.exemplo.toml`.

Os nomes dos serviços no Gerenciador de Credenciais NÃO estão aqui de propósito: trocá-los esconderia as chaves já
guardadas.
"""

import tomllib
from dataclasses import dataclass, field, fields
from functools import lru_cache
from pathlib import Path

from esteira.caminhos import AUTOMACAO

ARQUIVO = AUTOMACAO / "clipline.toml"
ESTILOS_LEGENDA = ("fixa", "palavra")


class ErroConfig(ValueError):
    pass


@dataclass(frozen=True)
class Config:
    # Identidade
    canal: str = "Tudo é Política"
    arroba: str = "@tudoepoliticabr"
    perfil_tiktok: str = "https://www.tiktok.com/@tudoepoliticabr"
    # Cortes
    duracao_minima: float = 60.0
    duracao_maxima: float = 120.0
    # Legenda: "fixa" (bloco branco, como sempre) ou "palavra" (a palavra falada acende na cor de destaque)
    legenda_estilo: str = "fixa"
    legenda_cor_destaque: str = "&H0000E5FF"  # ASS, &HAABBGGRR: amarelo
    # Áudio: normalizar a voz para o mesmo volume percebido em todos os cortes
    normalizar_voz: bool = False
    voz_lufs: float = -14.0
    # YouTube
    youtube_categoria: str = "22"
    limite_shorts: float = 180.0
    extras: dict = field(default_factory=dict, compare=False)


_TIPOS = {f.name: f.type for f in fields(Config) if f.name != "extras"}
# [seção] chave do clipline.toml -> campo da Config. No topo do arquivo, vale o próprio nome do campo.
SECOES = {
    ("canal", "nome"): "canal", ("canal", "arroba"): "arroba", ("canal", "perfil_tiktok"): "perfil_tiktok",
    ("duracao", "minima"): "duracao_minima", ("duracao", "maxima"): "duracao_maxima",
    ("legenda", "estilo"): "legenda_estilo", ("legenda", "cor_destaque"): "legenda_cor_destaque",
    ("voz", "normalizar"): "normalizar_voz", ("voz", "lufs"): "voz_lufs",
    ("youtube", "categoria"): "youtube_categoria", ("youtube", "limite_shorts"): "limite_shorts",
}


def _converter(nome: str, valor, tipo):
    if tipo in ("float", float) and isinstance(valor, (int, float)) and not isinstance(valor, bool):
        return float(valor)
    if tipo in ("bool", bool) and isinstance(valor, bool):
        return valor
    if tipo in ("str", str) and isinstance(valor, str):
        return valor
    raise ErroConfig(f"clipline.toml: {nome} com tipo errado ({type(valor).__name__})")


def ler(caminho: Path = ARQUIVO) -> Config:
    caminho = Path(caminho)
    if not caminho.exists():
        return Config()
    try:
        dados = tomllib.loads(caminho.read_text("utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as erro:
        raise ErroConfig(f"clipline.toml ilegível: {erro}") from None
    planos = {}
    for secao, valores in dados.items():
        if isinstance(valores, dict):
            for chave, valor in valores.items():
                planos[SECOES.get((secao, chave), f"{secao}.{chave}")] = valor
        else:
            planos[secao] = valores
    conhecidos = {k: _converter(k, v, _TIPOS[k]) for k, v in planos.items() if k in _TIPOS}
    config = Config(**conhecidos, extras={k: v for k, v in planos.items() if k not in _TIPOS})
    if config.legenda_estilo not in ESTILOS_LEGENDA:
        raise ErroConfig(f"clipline.toml: legenda_estilo deve ser um destes: {', '.join(ESTILOS_LEGENDA)}")
    if not 0 < config.duracao_minima < config.duracao_maxima:
        raise ErroConfig("clipline.toml: duracao_minima precisa ser positiva e menor que duracao_maxima")
    return config


@lru_cache(maxsize=1)
def atual() -> Config:
    """A configuração do canal, lida uma vez por processo."""
    return ler()
