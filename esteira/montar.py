import json
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
from esteira.midia import ErroMidia
from esteira.receita import NOME_ARQUIVO, Receita, ler_receita, validar_receita
from esteira.render import renderizar_final

ERROS_DA_RECEITA = (ErroMidia, OSError, ValueError, KeyError, TypeError)


def _renderizar(receita: Receita, destino: Path, video: Path, numero: int, cartao: Path | None) -> list[str]:
    problemas = validar_receita(receita, destino)
    if problemas:
        raise ErroMidia("; ".join(problemas))
    if not SOBREPOSICAO.exists():
        gerar_sobreposicao(SOBREPOSICAO)
    return renderizar_final(
        receita, video, cartao or escolher_encerramento(numero), destino, destino / CORTE_MP4, SOBREPOSICAO
    )


def montar_episodio(
    pasta: Path,
    numeros: set[int] | None = None,
    forcar: bool = False,
    cartao: Path | None = None,
) -> dict[int, str]:
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
        alertas: list[str] = []
        try:
            corte_mp4.unlink(missing_ok=True)
            receita = ler_receita(destino / TRABALHO)
            faixas = receita.faixas
            alertas = _renderizar(receita, destino, video, corte.numero, cartao)
            (destino / IMAGENS_SUGERIDAS).mkdir(exist_ok=True)
            (destino / VIDEO_FINAL).mkdir(exist_ok=True)
            resultado = f"ok com alertas: {'; '.join(alertas)}" if alertas else "ok"
        except ERROS_DA_RECEITA as erro:
            resultado = f"erro: {erro}"
        registrar(destino, video, corte, faixas, resultado, alertas)
        resultados[corte.numero] = resultado
    return resultados
