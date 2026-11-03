import json
import urllib.parse
import urllib.request
from pathlib import Path

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


def baixar_catalogo() -> list[dict]:
    pedido = urllib.request.Request(CATALOGO_URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(pedido, timeout=60) as resposta:
        return json.loads(resposta.read().decode("utf-8"))


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
