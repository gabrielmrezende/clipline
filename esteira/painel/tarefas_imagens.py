"""Pedidos de fotos e de imagens de IA: o que o trabalhador da fila executa."""

from collections.abc import Callable
from pathlib import Path

from esteira.fluxo_imagens import resumir_episodio, sugerir_episodio
from esteira.imagens_ia.config import Config
from esteira.imagens_ia.gerar import RegistroIncompleto, gerar_cortes, gerar_momento
from esteira.imagens_ia.provedor import ErroImagem, Provedor
from esteira.painel.troca_musica import Resultado

Progresso = Callable[[str], None]
Pessoas = Callable[[], list[str]]

GLOSSARIO_ILEGIVEL = "Não consegui ler o glossário (Contexto/glossario.md): nada foi aprovado nem gerado."
ERROS_DO_GLOSSARIO = (OSError, UnicodeDecodeError)


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
        fotos, _, resumos = resumir_episodio(pasta, numeros, consultar, medir, pessoas, gravar=True, painel=True)
        feitas = 0

        def contando(url: str, destino: Path) -> None:
            nonlocal feitas
            feitas += 1
            progresso(f"Baixando {feitas} de {fotos}…")
            baixar(url, destino)

        resultados = sugerir_episodio(pasta, numeros, pessoas, consultar, contando, painel=True)
        for n, texto in resumos.items():  # o motivo do resumo explica melhor que "rode imagens resumo"
            if texto.startswith("erro"):
                resultados[n] = texto
        if resultados and all(texto.startswith("erro") for texto in resultados.values()):
            return Resultado("erro", "; ".join(f"Corte {n}: {t}" for n, t in sorted(resultados.items())), [], None)
        return Resultado("pronto", f"{_plural(fotos, 'foto preparada', 'fotos preparadas')}.", avisos_dos_cortes(resultados), None)

    return executar


def _ler_pessoas(pessoas: Pessoas) -> list[str] | None:
    """O glossário lido de novo na hora de gerar (pode ter mudado com o pedido na fila); None se ilegível."""
    try:
        return pessoas()
    except ERROS_DO_GLOSSARIO:
        return None


def executar_ia(
    pastas_corte: list[Path],
    provedor: Provedor,
    config: Config,
    pessoas: Pessoas,
    base: Path,
    permitidos: set[tuple[Path, str]],
) -> Callable[[Progresso], Resultado]:
    """Gera só os pendentes que o dono confirmou (`permitidos`: pasta do corte, chave)."""

    def executar(progresso: Progresso) -> Resultado:
        lista = _ler_pessoas(pessoas)
        if lista is None:
            return Resultado("erro", GLOSSARIO_ILEGIVEL, [], None)
        arquivos, avisos = gerar_cortes(
            pastas_corte, provedor, config, lista, base=base, progresso=progresso, permitidos=permitidos
        )
        return Resultado("pronto", f"{_plural(len(arquivos), 'imagem gerada', 'imagens geradas')}.", avisos, None)

    return executar


def executar_momento_ia(
    pasta_corte: Path, chave: str, provedor: Provedor, config: Config, pessoas: Pessoas, base: Path
) -> Callable[[Progresso], Resultado]:
    def executar(progresso: Progresso) -> Resultado:
        progresso("Gerando 1 de 1…")
        lista = _ler_pessoas(pessoas)
        if lista is None:
            return Resultado("erro", GLOSSARIO_ILEGIVEL, [], None)
        try:
            arquivo = gerar_momento(pasta_corte, chave, provedor, config, lista, base)
        except RegistroIncompleto as aviso:  # a imagem foi paga e salva: não é erro
            return Resultado("pronto", aviso.arquivo, [str(aviso)], None)
        except (ErroImagem, OSError, ValueError) as erro:
            return Resultado("erro", str(erro), [], None)
        return Resultado("pronto", arquivo, [], None)

    return executar
