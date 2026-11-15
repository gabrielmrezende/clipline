"""Imprime as dependências do pyproject.toml para uma instalação só em CPU (a imagem Docker usa).

Tira as bibliotecas CUDA (nvidia-*), que ocupam mais de 1 GB e não servem sem GPU, e troca o opencv-python pelo
opencv-python-headless, que não precisa das bibliotecas gráficas do sistema. Os extras pedidos entram no fim.

    python scripts/requisitos_cpu.py painel > requisitos.txt
"""

import sys
import tomllib
from pathlib import Path

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


def nome(requisito: str) -> str:
    """O nome do pacote, sem versão, extras nem marcador ("av<18" -> "av")."""
    for separador in "<>=!~;[ ":
        requisito = requisito.split(separador, 1)[0]
    return requisito.strip().lower()


def requisitos_cpu(projeto: dict, extras: list[str]) -> list[str]:
    opcionais = projeto.get("optional-dependencies", {})
    desconhecidos = [e for e in extras if e not in opcionais]
    if desconhecidos:
        raise SystemExit(f"Extra desconhecido: {', '.join(desconhecidos)}. Use um destes: {', '.join(opcionais)}.")
    saida = []
    for requisito in projeto["dependencies"] + [r for e in extras for r in opcionais[e]]:
        if nome(requisito).startswith("nvidia-"):
            continue
        if nome(requisito) == "opencv-python":
            requisito = "opencv-python-headless" + requisito[len("opencv-python"):]
        saida.append(requisito)
    return saida


if __name__ == "__main__":
    projeto = tomllib.loads(PYPROJECT.read_text("utf-8"))["project"]
    print("\n".join(requisitos_cpu(projeto, sys.argv[1:])))
