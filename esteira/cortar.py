import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from esteira.caminhos import CONTEXTO, ENCERRAMENTOS, MUSICAS
from esteira.episodio import slug
from esteira.legenda import corrigir_palavras, escrever_srt, montar_cues
from esteira.limpeza import planejar_limpeza
from esteira.midia import ErroMidia, versao_ffmpeg
from esteira.modelos import Corte, Edicao, Palavra
from esteira.musica import atualizar_musica
from esteira.planos import ler_planos
from esteira.receita import NOME_ARQUIVO, Receita, gravar_receita, ler_receita
from esteira.transcrever import carregar_glossario, ler_palavras
from esteira.validar import validar_trecho


TRABALHO = "trabalho"
IMAGENS_SUGERIDAS = "imagens-sugeridas"
VIDEO_FINAL = "video-final"
CORTE_MP4 = "corte.mp4"


def pasta_de_trabalho(destino: Path) -> Path:
    pasta = Path(destino) / TRABALHO
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def ler_aprovados(pasta: Path) -> list[Corte]:
    dados = json.loads((Path(pasta) / "aprovados.json").read_text("utf-8"))
    return [Corte(**c) for c in dados["cortes"]]


def escolher_encerramento(numero: int) -> Path:
    return ENCERRAMENTOS[(numero - 1) % len(ENCERRAMENTOS)]


def pasta_do_corte(pasta: Path, corte: Corte) -> Path:
    return Path(pasta) / f"{corte.numero:02d}-{slug(corte.titulo)}"


def _escrever_edicoes(edicoes: list[Edicao], caminho: Path) -> None:
    linhas = ["# Edições automáticas", "", "Confira se nenhuma remoção mudou o sentido da fala.", ""]
    linhas += [f"- {e.inicio:.2f}s a {e.fim:.2f}s: {e.motivo} {e.texto}".rstrip() for e in edicoes]
    if not edicoes:
        linhas.append("- Nenhuma remoção.")
    caminho.write_text("\n".join(linhas) + "\n", "utf-8")


def registrar(
    destino: Path, video: Path, corte: Corte, faixas: list, resultado: str, alertas: list[str] | None = None
) -> None:
    (pasta_de_trabalho(destino) / "registro.json").write_text(
        json.dumps(
            {
                "video": str(video),
                "corte": asdict(corte),
                "faixas": faixas,
                "ffmpeg": versao_ffmpeg(),
                "data": datetime.now().isoformat(timespec="seconds"),
                "resultado": resultado,
                "alertas": alertas or [],
            },
            ensure_ascii=False,
            indent=2,
        ),
        "utf-8",
    )


def _preparar_um(destino: Path, corte: Corte, palavras: list[Palavra], nomes: list[str]) -> list:
    faixas, edicoes = planejar_limpeza(palavras, corte.inicio, corte.fim)
    trecho = [p for p in palavras if p.fim > corte.inicio and p.inicio < corte.fim]
    cues = montar_cues(corrigir_palavras(trecho, nomes), faixas, nomes)
    trabalho = pasta_de_trabalho(destino)
    escrever_srt(cues, trabalho / "legenda.srt")
    _escrever_edicoes(edicoes, trabalho / "edicoes.md")
    gravar_receita(trabalho, Receita(faixas, ler_planos(trabalho), cues))
    return faixas


def preparar_episodio(
    pasta: Path,
    numeros: set[int] | None = None,
    forcar: bool = False,
    nomes: list[str] | None = None,
    pasta_musicas: Path = MUSICAS,
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
        if (destino / TRABALHO / NOME_ARQUIVO).exists() and not forcar:
            resultados[corte.numero] = f"erro: {NOME_ARQUIVO} já existe, use --forcar"
            continue
        destino.mkdir(exist_ok=True)
        problemas = validar_trecho(palavras, corte, episodio["duracao"])
        faixas: list = []
        alertas: list[str] = []
        try:
            if problemas:
                raise ErroMidia("; ".join(problemas))
            faixas = _preparar_um(destino, corte, palavras, nomes)
            try:
                if atualizar_musica(pasta_de_trabalho(destino), corte, f"{pasta.name}/{destino.name}", pasta_musicas) is None:
                    alertas.append(f"sem música para o clima {corte.clima}")
            except (OSError, ValueError, KeyError, TypeError) as erro:
                alertas.append(f"música: erro {erro}")
            resultado = f"ok com alertas: {'; '.join(alertas)}" if alertas else "ok"
        except (ErroMidia, OSError, ValueError) as erro:
            resultado = f"erro: {erro}"
        if resultado.startswith("erro") and forcar:
            (destino / TRABALHO / NOME_ARQUIVO).unlink(missing_ok=True)
        registrar(destino, video, corte, faixas, resultado, alertas)
        resultados[corte.numero] = resultado
    return resultados
