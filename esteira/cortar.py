import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from esteira.caminhos import CARTAO_FINAL, CONTEXTO
from esteira.episodio import slug
from esteira.legenda import corrigir_palavras, escrever_ass, escrever_srt, montar_cues
from esteira.limpeza import planejar_limpeza
from esteira.midia import ErroMidia, versao_ffmpeg
from esteira.modelos import Corte, Edicao, Palavra
from esteira.planos import ler_planos
from esteira.render import queimar_legenda, renderizar_sem_legenda
from esteira.transcrever import carregar_glossario, ler_palavras
from esteira.validar import validar_trecho


def ler_aprovados(pasta: Path) -> list[Corte]:
    dados = json.loads((Path(pasta) / "aprovados.json").read_text("utf-8"))
    return [Corte(**c) for c in dados["cortes"]]


def pasta_do_corte(pasta: Path, corte: Corte) -> Path:
    return Path(pasta) / f"{corte.numero:02d}-{slug(corte.titulo)}"


def _escrever_edicoes(edicoes: list[Edicao], caminho: Path) -> None:
    linhas = ["# Edições automáticas", "", "Confira se nenhuma remoção mudou o sentido da fala.", ""]
    linhas += [f"- {e.inicio:.2f}s a {e.fim:.2f}s: {e.motivo} {e.texto}".rstrip() for e in edicoes]
    if not edicoes:
        linhas.append("- Nenhuma remoção.")
    caminho.write_text("\n".join(linhas) + "\n", "utf-8")


def _registrar(destino: Path, video: Path, corte: Corte, faixas: list, resultado: str) -> None:
    (destino / "registro.json").write_text(
        json.dumps(
            {
                "video": str(video),
                "corte": asdict(corte),
                "faixas": faixas,
                "ffmpeg": versao_ffmpeg(),
                "data": datetime.now().isoformat(timespec="seconds"),
                "resultado": resultado,
            },
            ensure_ascii=False,
            indent=2,
        ),
        "utf-8",
    )


def _cortar_um(
    video: Path, destino: Path, corte: Corte, palavras: list[Palavra], nomes: list[str], cartao: Path
) -> list:
    faixas, edicoes = planejar_limpeza(palavras, corte.inicio, corte.fim)
    trecho = [p for p in palavras if p.fim > corte.inicio and p.inicio < corte.fim]
    cues = montar_cues(corrigir_palavras(trecho, nomes), faixas, nomes)
    (destino / "imagens").mkdir(exist_ok=True)
    escrever_srt(cues, destino / "legenda.srt")
    _escrever_edicoes(edicoes, destino / "edicoes.md")
    base = destino / "corte-sem-legenda.mp4"
    renderizar_sem_legenda(video, faixas, cartao, base, ler_planos(destino))
    ass = destino / "legenda.ass"
    escrever_ass(cues, ass)
    try:
        queimar_legenda(base, ass, destino / "corte.mp4")
    finally:
        ass.unlink(missing_ok=True)
    return faixas


def cortar_episodio(
    pasta: Path,
    numeros: set[int] | None = None,
    forcar: bool = False,
    cartao: Path = CARTAO_FINAL,
    nomes: list[str] | None = None,
) -> dict[int, str]:
    pasta = Path(pasta)
    episodio = json.loads((pasta / "episodio.json").read_text("utf-8"))
    video = Path(episodio["video"])
    palavras = ler_palavras(pasta)
    if nomes is None:
        nomes = carregar_glossario(CONTEXTO / "glossario.md")

    resultados: dict[int, str] = {}
    for corte in ler_aprovados(pasta):
        if numeros is not None and corte.numero not in numeros:
            continue
        destino = pasta_do_corte(pasta, corte)
        if (destino / "corte.mp4").exists() and not forcar:
            resultados[corte.numero] = "erro: corte já existe, use --forcar"
            continue
        destino.mkdir(exist_ok=True)
        problemas = validar_trecho(palavras, corte, episodio["duracao"])
        faixas: list = []
        try:
            if problemas:
                raise ErroMidia("; ".join(problemas))
            for nome in ("corte.mp4", "corte-sem-legenda.mp4"):
                (destino / nome).unlink(missing_ok=True)
            faixas = _cortar_um(video, destino, corte, palavras, nomes, cartao)
            resultado = "ok"
        except (ErroMidia, OSError) as erro:
            resultado = f"erro: {erro}"
        _registrar(destino, video, corte, faixas, resultado)
        resultados[corte.numero] = resultado
    return resultados
