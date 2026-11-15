"""Abre o painel dentro do contêiner Docker (o CMD da imagem usa).

O `esteira painel` escuta só em 127.0.0.1, e o Docker não alcança esse endereço dentro do contêiner. Aqui o
servidor escuta em todas as interfaces do contêiner; quem limita o acesso é o compose.yaml, que publica a porta
só em 127.0.0.1 do computador. Fora de um contêiner este script se recusa a rodar: use `python -m esteira painel`.
Os argumentos vão para o `esteira painel` (por exemplo `--porta 8765`).
"""

import os
import sys
from pathlib import Path

TODAS_AS_INTERFACES = "0.0.0.0"


def dentro_de_conteiner() -> bool:
    return (
        os.environ.get("CLIPLINE_CONTEINER") == "1"
        or Path("/.dockerenv").exists()
        or Path("/run/.containerenv").exists()  # Podman
    )


def escutar_em_todas_as_interfaces() -> None:
    """Troca o endereço de qualquer servidor do uvicorn criado depois daqui (uvicorn.run cria um Config)."""
    import uvicorn

    iniciar = uvicorn.Config.__init__

    def iniciar_em_todas(self, app, *args, **opcoes):
        opcoes["host"] = TODAS_AS_INTERFACES
        iniciar(self, app, *args, **opcoes)

    uvicorn.Config.__init__ = iniciar_em_todas


def principal(argv: list[str]) -> int:
    if not dentro_de_conteiner():
        print("Este script é só para o contêiner. Fora dele, rode: python -m esteira painel", file=sys.stderr)
        return 2
    escutar_em_todas_as_interfaces()
    from esteira.cli import principal as esteira

    return esteira(["painel", *argv])


if __name__ == "__main__":
    sys.exit(principal(sys.argv[1:]))
