from pathlib import Path

AUTOMACAO = Path(__file__).resolve().parent.parent
RAIZ = AUTOMACAO.parent
CONTEXTO = RAIZ / "Contexto"
CORTES = RAIZ / "Cortes"
BIN = AUTOMACAO / "bin"
MUSICAS = AUTOMACAO / "musicas"
FONTES = AUTOMACAO / "assets" / "fonts"
ENCERRAMENTOS = [
    RAIZ / f"Final Corte ({nome}).mp4"
    for nome in ("Gabriel 1", "Tigas 1", "Gabriel 2", "Tigas 2")
]
SOBREPOSICAO = AUTOMACAO / "assets" / "encerramento.png"
LOGO = RAIZ / "Logos" / "Logo sem Fundo.png"


class EscritaProibida(Exception):
    pass


def garantir_escrita(caminho: Path, base_extra: Path | None = None) -> Path:
    resolvido = Path(caminho).resolve()
    bases = [CORTES.resolve(), AUTOMACAO.resolve()]
    if base_extra is not None:
        bases.append(Path(base_extra).resolve())
    if not any(resolvido.is_relative_to(base) for base in bases):
        raise EscritaProibida(f"Escrita fora de Cortes/ e Automacao/: {resolvido}")
    return resolvido
