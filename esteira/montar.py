import json
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path

from esteira.caminhos import SOBREPOSICAO
from esteira.cartao import gerar_sobreposicao
from esteira.cortar import (
    CORTE_MP4,
    IMAGENS_SUGERIDAS,
    TRABALHO,
    VIDEO_FINAL,
    escolher_encerramento,
    ler_aprovados,
    pasta_do_corte,
    registrar,
)
from esteira.imagens_no_video import imagens_do_corte
from esteira.midia import ErroMidia
from esteira.planos import Plano, ler_planos
from esteira.receita import NOME_ARQUIVO, ImagemNoVideo, Receita, ler_receita, validar_receita
from esteira.render import renderizar_final

ERROS_DA_RECEITA = (ErroMidia, OSError, ValueError, KeyError, TypeError)
ZOOM_MINIMO = 1.0
ZOOM_MAXIMO = 2.0


def _planos_do_corte(destino: Path, receita: Receita) -> list[Plano]:
    """O enquadramento.json manda quando existe: editá-lo depois do preparar vale no montar."""
    planos = ler_planos(destino / TRABALHO) if (destino / TRABALHO / "enquadramento.json").exists() else receita.planos
    for numero, plano in enumerate(planos, 1):
        if not ZOOM_MINIMO <= plano.zoom <= ZOOM_MAXIMO:
            raise ErroMidia(f"enquadramento.json: zoom fora de 1,0 a 2,0 no plano {numero}")
    return planos


def _renderizar(
    receita: Receita, destino: Path, video: Path, numero: int, cartao: Path | None, imagens: Sequence[ImagemNoVideo]
) -> list[str]:
    problemas = validar_receita(receita, destino)
    if problemas:
        raise ErroMidia("; ".join(problemas))
    if not SOBREPOSICAO.exists():
        gerar_sobreposicao(SOBREPOSICAO)
    return renderizar_final(
        receita, video, cartao or escolher_encerramento(numero), destino, destino / CORTE_MP4, SOBREPOSICAO,
        imagens=imagens,
    )


def _alertas_gravados(destino: Path) -> tuple[list[str], list[str] | None]:
    """Alertas do preparar (ou todos, em registro antigo) e a lista própria do preparar, se houver."""
    try:
        registro = json.loads((destino / TRABALHO / "registro.json").read_text("utf-8"))
        proprios = registro.get("alertas_preparar")
        if isinstance(proprios, list):
            proprios = [a for a in proprios if isinstance(a, str)]
            return proprios, proprios
        return [a for a in registro.get("alertas", []) if isinstance(a, str)], None
    except (OSError, ValueError, AttributeError):
        return [], None


def montar_episodio(
    pasta: Path,
    numeros: set[int] | None = None,
    forcar: bool = False,
    cartao: Path | None = None,
    sem_imagens: bool = False,
) -> dict[int, str]:
    """Monta o corte.mp4 de cada corte, com as imagens prontas de cada momento (nenhuma com `sem_imagens`)."""
    pasta = Path(pasta)
    video = Path(json.loads((pasta / "episodio.json").read_text("utf-8"))["video"])
    resultados: dict[int, str] = {}
    for corte in ler_aprovados(pasta):
        if numeros is not None and corte.numero not in numeros:
            continue
        destino = pasta_do_corte(pasta, corte)
        if not (destino / TRABALHO / NOME_ARQUIVO).exists():
            resultados[corte.numero] = f"erro: {NOME_ARQUIVO} não encontrado, rode preparar"
            continue
        corte_mp4 = destino / CORTE_MP4
        if corte_mp4.exists() and not forcar:
            resultados[corte.numero] = f"erro: {CORTE_MP4} já existe, use --forcar"
            continue
        faixas: list = []
        anteriores, do_preparar = _alertas_gravados(destino)
        alertas: list[str] = anteriores
        imagens: list[ImagemNoVideo] | None = None
        try:
            corte_mp4.unlink(missing_ok=True)
            receita = ler_receita(destino / TRABALHO)
            faixas = receita.faixas
            receita.planos = _planos_do_corte(destino, receita)
            escolhidas, das_imagens = ([], []) if sem_imagens else imagens_do_corte(destino)
            do_render = _renderizar(receita, destino, video, corte.numero, cartao, escolhidas)
            if any(a.startswith("sem música") for a in anteriores):
                do_render = [a for a in do_render if not a.startswith("sem música")]
            alertas = anteriores + [a for a in do_render + das_imagens if a not in anteriores]
            imagens = escolhidas
            (destino / IMAGENS_SUGERIDAS).mkdir(exist_ok=True)
            (destino / VIDEO_FINAL).mkdir(exist_ok=True)
            resultado = f"ok com alertas: {'; '.join(alertas)}" if alertas else "ok"
        except ERROS_DA_RECEITA as erro:
            resultado = f"erro: {erro}"
        registrar(
            destino, video, corte, faixas, resultado, alertas, alertas_preparar=do_preparar,
            imagens=[asdict(i) for i in imagens] if imagens is not None and resultado.startswith("ok") else None,
        )
        resultados[corte.numero] = resultado
    return resultados
