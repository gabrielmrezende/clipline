import json
from pathlib import Path

from esteira.caminhos import AUTOMACAO

ARQUIVO = AUTOMACAO / "publicacao.json"
PADRAO = {"youtube": "privado", "tiktok": "rascunho"}
VALIDOS = {"youtube": ("privado", "agendado"), "tiktok": ("rascunho", "direto")}


def ler_modos(caminho: Path = ARQUIVO) -> dict[str, str]:
    modos = dict(PADRAO)
    if Path(caminho).exists():
        modos.update(json.loads(Path(caminho).read_text("utf-8")))
    for rede, validos in VALIDOS.items():
        if modos[rede] not in validos:
            raise ValueError(f"publicacao.json: modo '{modos[rede]}' inválido para {rede}; use {' ou '.join(validos)}")
    return modos
