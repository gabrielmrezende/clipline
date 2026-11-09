"""Pedidos de fotos e de imagens de IA: o que o trabalhador da fila executa."""

from collections.abc import Callable
from pathlib import Path

from esteira.fluxo_imagens import resumir_episodio, sugerir_episodio
from esteira.imagens_ia.config import Config
from esteira.imagens_ia.gerar import gerar_cortes, gerar_momento
from esteira.imagens_ia.provedor import ErroImagem, Provedor
from esteira.painel.troca_musica import Resultado

Progresso = Callable[[str], None]


def avisos_dos_cortes(resultados: dict[int, str]) -> list[str]:
    return [f"Corte {n}: {texto}" for n, texto in sorted(resultados.items()) if texto != "ok"]


def _plural(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


def executar_fotos(
    pasta: Path,
    numeros: set[int],
    pessoas: list[str],
    consultar: Callable,
    medir: Callable,
    baixar: Callable[[str, Path], None],
) -> Callable[[Progresso], Resultado]:
    """Resume (grava os links e tamanhos) e baixa as fotos; o `sugerir` recusa sem o resumo."""

    def executar(progresso: Progresso) -> Resultado:
        fotos, _, resumos = resumir_episodio(pasta, numeros, consultar, medir, pessoas, gravar=True)
        feitas = 0

        def contando(url: str, destino: Path) -> None:
            nonlocal feitas
            feitas += 1
            progresso(f"Baixando {feitas} de {fotos}…")
            baixar(url, destino)

        resultados = sugerir_episodio(pasta, numeros, pessoas, consultar, contando)
        for n, texto in resumos.items():  # o motivo do resumo explica melhor que "rode imagens resumo"
            if texto.startswith("erro"):
                resultados[n] = texto
        if resultados and all(texto.startswith("erro") for texto in resultados.values()):
            return Resultado("erro", "; ".join(f"Corte {n}: {t}" for n, t in sorted(resultados.items())), [], None)
        return Resultado("pronto", f"{_plural(fotos, 'foto preparada', 'fotos preparadas')}.", avisos_dos_cortes(resultados), None)

    return executar


def executar_ia(
    pastas_corte: list[Path], provedor: Provedor, config: Config, pessoas: list[str], base: Path
) -> Callable[[Progresso], Resultado]:
    def executar(progresso: Progresso) -> Resultado:
        arquivos, avisos = gerar_cortes(pastas_corte, provedor, config, pessoas, base=base, progresso=progresso)
        return Resultado("pronto", f"{_plural(len(arquivos), 'imagem gerada', 'imagens geradas')}.", avisos, None)

    return executar


def executar_momento_ia(
    pasta_corte: Path, chave: str, provedor: Provedor, config: Config, pessoas: list[str], base: Path
) -> Callable[[Progresso], Resultado]:
    def executar(progresso: Progresso) -> Resultado:
        progresso("Gerando 1 de 1…")
        try:
            arquivo = gerar_momento(pasta_corte, chave, provedor, config, pessoas, base)
        except (ErroImagem, OSError, ValueError) as erro:
            return Resultado("erro", str(erro), [], None)
        return Resultado("pronto", arquivo, [], None)

    return executar
