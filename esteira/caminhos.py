from pathlib import Path

AUTOMACAO = Path(__file__).resolve().parent.parent
RAIZ = AUTOMACAO.parent
CONTEXTO = RAIZ / "Contexto"
PROGRAMAS = RAIZ / "1 - Programas"
CORTES = RAIZ / "2 - Cortes"
IDENTIDADE = RAIZ / "3 - Identidade"
BIN = AUTOMACAO / "bin"
MUSICAS = AUTOMACAO / "musicas"
FONTES = AUTOMACAO / "assets" / "fonts"
ENCERRAMENTOS = [
    IDENTIDADE / "Encerramentos" / f"Final Corte ({nome}).mp4"
    for nome in ("Gabriel 1", "Tigas 1", "Gabriel 2", "Tigas 2")
]
SOBREPOSICAO = AUTOMACAO / "assets" / "encerramento.png"
LOGO = IDENTIDADE / "Logos" / "Logo sem Fundo.png"


def gravar_atomico(caminho: Path, texto: str, newline: str | None = None) -> None:
    """Grava num .tmp ao lado e troca de uma vez: uma queda no meio nunca deixa o arquivo pela metade."""
    caminho = Path(caminho)
    temporario = caminho.with_name(caminho.name + ".tmp")
    try:
        temporario.write_text(texto, "utf-8", newline=newline)
        temporario.replace(caminho)
    finally:
        temporario.unlink(missing_ok=True)


class EscritaProibida(Exception):
    pass


def garantir_escrita(caminho: Path, base_extra: Path | None = None) -> Path:
    resolvido = Path(caminho).resolve()
    bases = [CORTES.resolve(), AUTOMACAO.resolve()]
    if base_extra is not None:
        bases.append(Path(base_extra).resolve())
    if not any(resolvido.is_relative_to(base) for base in bases):
        raise EscritaProibida(f"Escrita fora de 2 - Cortes/ e Automacao/: {resolvido}")
    return resolvido
