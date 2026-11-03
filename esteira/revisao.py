import json
from pathlib import Path

from esteira.cortar import ler_aprovados, pasta_do_corte
from esteira.modelos import Corte, Palavra
from esteira.receita import NOME_ARQUIVO, Receita, ler_receita
from esteira.transcrever import ler_palavras


def contexto_do_trecho(palavras: list[Palavra], inicio: float, fim: float, n: int = 15) -> tuple[str, str]:
    antes = [p.texto for p in palavras if p.fim <= inicio]
    depois = [p.texto for p in palavras if p.inicio >= fim]
    return " ".join(antes[-n:]), " ".join(depois[:n])


def _alertas(registro: dict, receita: Receita | None) -> list[str]:
    alertas = list(registro.get("alertas", []))
    if receita:
        for n, imagem in enumerate(receita.imagens, 1):
            if not imagem.licenca:
                alertas.append(f"imagem {n} sem licença registrada")
    return alertas


def _linha_musica(receita: Receita | None) -> str:
    musica = receita.musica if receita else None
    return f"Música: {musica.titulo or Path(musica.arquivo).name}" if musica else "Música: nenhuma"


def _bloco(pasta: Path, corte: Corte, palavras: list[Palavra]) -> list[str]:
    destino = pasta_do_corte(pasta, corte)
    linhas = [f"## {corte.numero}. {corte.titulo}"]
    arquivo = destino / "registro.json"
    try:
        registro = json.loads(arquivo.read_text("utf-8")) if arquivo.exists() else {}
    except (OSError, ValueError):
        return linhas + ["Erro: registro ilegível", ""]
    resultado = registro.get("resultado", "")
    if resultado.startswith("erro:"):
        return linhas + [f"Erro: {resultado[len('erro:'):].strip()}", ""]
    if not (destino / "final.mp4").exists():
        return linhas + ["Erro: corte não montado", ""]

    antes, depois = contexto_do_trecho(palavras, corte.inicio, corte.fim)
    redes = "YouTube, TikTok e Instagram" if corte.instagram else "YouTube e TikTok"
    try:
        receita = ler_receita(destino) if (destino / NOME_ARQUIVO).exists() else None
        alertas = _alertas(registro, receita)
    except (OSError, ValueError, KeyError, TypeError):
        return linhas + ["Erro: montagem ilegível", ""]
    return linhas + [
        f"Vídeo: [final.mp4]({destino.name}/final.mp4)",
        f"Redes: {redes}",
        f"Publicação sugerida: {corte.data or 'sem data'}",
        _linha_musica(receita),
        f'Antes: "{"... " if antes else ""}{antes}"',
        f'Depois: "{depois}{" ..." if depois else ""}"',
        f"Alertas: {'; '.join(alertas) if alertas else 'nenhum'}",
        "",
    ]


def escrever_revisao(pasta: Path) -> Path:
    pasta = Path(pasta)
    palavras = ler_palavras(pasta)
    linhas = ["# Revisão do episódio", ""]
    for corte in ler_aprovados(pasta):
        linhas += _bloco(pasta, corte, palavras)
    linhas.append("Candidatos descartados: ver [candidatos.md](candidatos.md).")
    caminho = pasta / "revisao.md"
    caminho.write_text("\n".join(linhas) + "\n", "utf-8", newline="\n")
    return caminho
