import copy
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from esteira.caminhos import AUTOMACAO, garantir_escrita
from esteira.imagens_ia.provedor import ErroImagem, Provedor

PROVEDORES = ("openai", "google")
ARQUIVO = AUTOMACAO / "imagens-ia.json"

_PADRAO = {
    "provedor": "openai",
    "provedores": {
        "openai": {"modelo": "gpt-image-2", "qualidade": "medium", "preco_usd": 0.041},
        "google": {"modelo": "gemini-nano-banana-2.1", "qualidade": "1K", "preco_usd": 0.0336},
    },
}


@dataclass
class Config:
    provedor: str
    provedores: dict[str, dict]


def padrao() -> Config:
    dados = copy.deepcopy(_PADRAO)
    return Config(dados["provedor"], dados["provedores"])


def ler_config(caminho: Path = ARQUIVO) -> Config:
    caminho = Path(caminho)
    if not caminho.exists():
        return padrao()
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
        provedor = dados["provedor"]
        lidos = dados["provedores"]
        if not isinstance(provedor, str) or not isinstance(lidos, dict):
            raise TypeError
        cfg = padrao()
        for nome, valores in lidos.items():
            if not isinstance(valores, dict):
                raise TypeError
            cfg.provedores[nome] = {**cfg.provedores.get(nome, {}), **valores}
        cfg.provedor = provedor
        return cfg
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        raise ErroImagem("imagens-ia.json ilegível") from None


def _validar(config: Config) -> None:
    if config.provedor not in PROVEDORES:
        raise ErroImagem(f"Provedor desconhecido: {config.provedor}")
    for nome, dados in config.provedores.items():
        if nome not in PROVEDORES:
            raise ErroImagem(f"Provedor desconhecido: {nome}")
        preco = dados.get("preco_usd")
        if isinstance(preco, bool) or not isinstance(preco, (int, float)):
            raise ErroImagem(f"Preço de {nome} deve ser um número")
        if preco < 0:
            raise ErroImagem(f"Preço de {nome} não pode ser negativo")


def gravar_config(config: Config, caminho: Path = ARQUIVO, base: Path | None = None) -> None:
    _validar(config)
    destino = garantir_escrita(Path(caminho), base_extra=base)
    texto = json.dumps({"provedor": config.provedor, "provedores": config.provedores}, ensure_ascii=False, indent=2)
    temporario = destino.with_name(destino.name + ".tmp")
    temporario.write_text(texto + "\n", encoding="utf-8")
    os.replace(temporario, destino)


def provedor_atual(config: Config, fabricas: dict[str, Callable[[dict], Provedor]] | None = None) -> Provedor:
    if fabricas is None:
        from esteira.imagens_ia.google import Google
        from esteira.imagens_ia.openai import OpenAI

        fabricas = {"openai": OpenAI, "google": Google}
    return fabricas[config.provedor](config.provedores[config.provedor])
