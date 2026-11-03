import json
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

from esteira.midia import duracao_audio, executar_ffmpeg

CATALOGO_URL = "https://incompetech.com/music/royalty-free/pieces.json"
ARQUIVOS_URL = "https://incompetech.com/music/royalty-free/mp3-royaltyfree/"
USER_AGENT = "TudoEPoliticaEsteira/1.0"

CLIMAS = {
    "leve": {"bright", "bouncy", "humorous"},
    "tenso": {"suspenseful", "driving", "intense"},
    "inspirador": {"uplifting", "epic"},
    "reflexivo": {"calming", "relaxed", "somber"},
}
CLIMAS_VALIDOS = tuple(CLIMAS)

MARCACOES_EXCLUIDAS = {"eerie", "unnerving", "dark", "aggressive", "action"}
INSTRUMENTOS_EXCLUIDOS = ("voice", "vocal", "choir")
DURACAO_MINIMA = 90
DURACAO_MAXIMA = 360
TERMOS_LEVES = ("piano", "strings", "guitar", "synth", "pad")
TERMOS_PESADOS = ("drums", "brass", "percussion")


def _abrir(url: str):
    pedido = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    return urllib.request.urlopen(pedido, timeout=60)


def baixar_catalogo() -> list[dict]:
    with _abrir(CATALOGO_URL) as resposta:
        return json.loads(resposta.read().decode("utf-8"))


def baixar_url(url: str, destino: Path) -> None:
    with _abrir(url) as resposta:
        destino.write_bytes(resposta.read())


def _segundos(duracao: str) -> int:
    horas, minutos, segundos = (int(parte) for parte in duracao.split(":"))
    return horas * 3600 + minutos * 60 + segundos


def _marcacoes(peca: dict) -> set[str]:
    return {m.strip().lower() for m in (peca.get("feel") or "").split(",") if m.strip()}


def clima_da_faixa(peca: dict) -> str | None:
    if not DURACAO_MINIMA <= _segundos(peca["length"]) <= DURACAO_MAXIMA:
        return None
    marcacoes = _marcacoes(peca)
    if marcacoes & MARCACOES_EXCLUIDAS:
        return None
    instrumentos = (peca.get("instruments") or "").lower()
    if any(termo in instrumentos for termo in INSTRUMENTOS_EXCLUIDOS):
        return None
    return next((clima for clima, aceitas in CLIMAS.items() if marcacoes & aceitas), None)


def _pontos(peca: dict) -> int:
    instrumentos = (peca.get("instruments") or "").lower()
    return sum(t in instrumentos for t in TERMOS_LEVES) - sum(t in instrumentos for t in TERMOS_PESADOS)


def propor(pecas: list[dict], por_clima: int = 10) -> dict[str, list[dict]]:
    grupos: dict[str, list[dict]] = {clima: [] for clima in CLIMAS_VALIDOS}
    for peca in pecas:
        clima = clima_da_faixa(peca)
        if clima:
            grupos[clima].append(peca)
    return {
        clima: sorted(grupo, key=lambda p: (-_pontos(p), p["title"]))[:por_clima]
        for clima, grupo in grupos.items()
    }


def escrever_proposta(selecao: dict[str, list[dict]], pasta: Path) -> None:
    pasta.mkdir(parents=True, exist_ok=True)
    linhas = ["# Proposta de músicas", ""]
    for clima, pecas in selecao.items():
        linhas += [f"## {clima}", ""]
        for peca in pecas:
            link = ARQUIVOS_URL + urllib.parse.quote(peca["filename"])
            linhas += [
                f"- **{peca['title']}** ({peca['length']})",
                f"  - Instrumentos: {peca.get('instruments') or ''}",
                f"  - Ouvir: {link}",
                f"  - {peca.get('description') or ''}",
            ]
        linhas.append("")
    (pasta / "proposta.md").write_text("\n".join(linhas), "utf-8", newline="\n")
    aprovadas = {clima: [p["filename"] for p in pecas] for clima, pecas in selecao.items()}
    (pasta / "aprovadas.json").write_text(
        json.dumps(aprovadas, ensure_ascii=False, indent=2) + "\n", "utf-8", newline="\n"
    )


@dataclass
class Faixa:
    titulo: str
    clima: str
    duracao: float
    arquivo: str
    credito: str


def credito(titulo: str) -> str:
    return f"Música: {titulo} — Kevin MacLeod (incompetech.com), licença CC BY 4.0"


def ler_catalogo(pasta: Path) -> list[Faixa]:
    arquivo = pasta / "catalogo.json"
    if not arquivo.exists():
        return []
    return [Faixa(**item) for item in json.loads(arquivo.read_text("utf-8"))]


def gravar_catalogo(pasta: Path, faixas: list[Faixa]) -> None:
    pasta.mkdir(parents=True, exist_ok=True)
    texto = json.dumps([asdict(f) for f in faixas], ensure_ascii=False, indent=2) + "\n"
    (pasta / "catalogo.json").write_text(texto, "utf-8", newline="\n")


def _processar(pasta: Path, clima: str, peca: dict, baixar: Callable[[str, Path], None]) -> Faixa:
    nome = peca["filename"]
    destino = pasta / clima / nome
    destino.parent.mkdir(parents=True, exist_ok=True)
    bruto = destino.with_name(nome + ".tmp")
    normalizado = destino.with_name(nome + ".norm.tmp")
    try:
        baixar(ARQUIVOS_URL + urllib.parse.quote(nome), bruto)
        executar_ffmpeg([
            "-y", "-i", str(bruto), "-vn", "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
            "-c:a", "libmp3lame", "-b:a", "192k", "-f", "mp3", str(normalizado),
        ])
        duracao = round(duracao_audio(normalizado), 1)
        normalizado.replace(destino)
    finally:
        bruto.unlink(missing_ok=True)
        normalizado.unlink(missing_ok=True)
    return Faixa(peca["title"], clima, duracao, f"{clima}/{nome}", credito(peca["title"]))


def baixar_musicas(
    pasta: Path, pecas: list[dict], baixar: Callable[[str, Path], None] = baixar_url
) -> list[str]:
    aprovadas = json.loads((pasta / "aprovadas.json").read_text("utf-8"))
    por_arquivo = {p["filename"]: p for p in pecas}
    catalogo = {f.arquivo: f for f in ler_catalogo(pasta)}
    erros = []
    for clima in CLIMAS_VALIDOS:
        for nome in aprovadas.get(clima, []):
            if f"{clima}/{nome}" in catalogo:
                continue
            try:
                if nome not in por_arquivo:
                    raise KeyError("não está no catálogo do Incompetech")
                faixa = _processar(pasta, clima, por_arquivo[nome], baixar)
            except Exception as erro:
                erros.append(f"falha em {nome}: {erro}")
                continue
            catalogo[faixa.arquivo] = faixa
    ordem = [f"{clima}/{nome}" for clima in CLIMAS_VALIDOS for nome in aprovadas.get(clima, [])]
    ordenadas = [catalogo[a] for a in ordem if a in catalogo]
    ordenadas += [f for a, f in catalogo.items() if a not in ordem]
    gravar_catalogo(pasta, ordenadas)
    return erros
