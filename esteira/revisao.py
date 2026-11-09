import json
from dataclasses import dataclass, field
from pathlib import Path

from esteira.cortar import (
    CORTE_MP4,
    IMAGENS_SUGERIDAS,
    TRABALHO,
    VIDEO_FINAL,
    ler_aprovados,
    pasta_do_corte,
)
from esteira.modelos import Corte, Palavra
from esteira.receita import NOME_ARQUIVO, Receita, ler_receita
from esteira.transcrever import ler_palavras


NOMES_SUSPEITOS = "nomes-suspeitos.json"


@dataclass
class BlocoRevisao:
    numero: int
    titulo: str
    pasta: str
    clima: str
    instagram: bool
    redes: list[str]
    data: str
    musica: str | None = None
    antes: str = ""
    depois: str = ""
    alertas: list[str] = field(default_factory=list)
    video_final: list[str] = field(default_factory=list)
    tem_guia: bool = False
    erro: str | None = None
    video_final_desatualizado: bool = False


def contexto_do_trecho(palavras: list[Palavra], inicio: float, fim: float, n: int = 15) -> tuple[str, str]:
    antes = [p.texto for p in palavras if p.fim <= inicio]
    depois = [p.texto for p in palavras if p.inicio >= fim]
    return " ".join(antes[-n:]), " ".join(depois[:n])


def _alertas(registro: dict) -> list[str]:
    return list(registro.get("alertas", []))


def _tem_guia(destino: Path) -> bool:
    return (destino / IMAGENS_SUGERIDAS / "guia.md").exists()


def _nomes_video_final(destino: Path) -> list[str]:
    pasta = destino / VIDEO_FINAL
    if not pasta.is_dir():
        return []
    return sorted(
        (a.name for a in pasta.iterdir() if a.is_file() and a.suffix.lower() in (".mp4", ".mov")),
        key=str.lower,
    )


def _video_final_desatualizado(destino: Path) -> bool:
    pasta = destino / VIDEO_FINAL
    if not pasta.is_dir():
        return False
    datas = [
        a.stat().st_mtime for a in pasta.iterdir() if a.is_file() and a.suffix.lower() in (".mp4", ".mov")
    ]
    return bool(datas) and max(datas) < (destino / CORTE_MP4).stat().st_mtime


def ler_nomes_suspeitos(pasta: Path) -> tuple[dict[int, list[str]], str | None]:
    arquivo = Path(pasta) / NOMES_SUSPEITOS
    if not arquivo.exists():
        return {}, None
    try:
        bruto = json.loads(arquivo.read_text("utf-8"))
        nomes = {int(numero): [str(n) for n in lista] for numero, lista in bruto.items()}
    except (OSError, ValueError, AttributeError, TypeError):
        return {}, f"{NOMES_SUSPEITOS} ilegível"
    return nomes, None


def _bloco(pasta: Path, corte: Corte, palavras: list[Palavra], nomes: dict[int, list[str]], alerta_geral: str | None) -> BlocoRevisao:
    destino = pasta_do_corte(pasta, corte)
    bloco = BlocoRevisao(
        numero=corte.numero,
        titulo=corte.titulo,
        pasta=destino.name,
        clima=corte.clima,
        instagram=corte.instagram,
        redes=["youtube", "tiktok", "instagram"] if corte.instagram else ["youtube", "tiktok"],
        data=corte.data or "",
    )
    arquivo = destino / TRABALHO / "registro.json"
    try:
        registro = json.loads(arquivo.read_text("utf-8")) if arquivo.exists() else {}
    except (OSError, ValueError):
        bloco.erro = "registro ilegível"
        return bloco
    resultado = registro.get("resultado", "")
    if resultado.startswith("erro:"):
        bloco.erro = resultado[len("erro:"):].strip()
        return bloco
    if not (destino / CORTE_MP4).exists():
        bloco.erro = "corte não montado"
        return bloco

    bloco.antes, bloco.depois = contexto_do_trecho(palavras, corte.inicio, corte.fim)
    try:
        receita = ler_receita(destino / TRABALHO) if (destino / TRABALHO / NOME_ARQUIVO).exists() else None
        alertas = _alertas(registro)
        video_final = _nomes_video_final(destino)
        desatualizado = _video_final_desatualizado(destino)
    except (OSError, ValueError, KeyError, TypeError):
        bloco.erro = "montagem ilegível"
        return bloco
    musica = receita.musica if receita else None
    bloco.musica = (musica.titulo or Path(musica.arquivo).name) if musica else None
    bloco.alertas = alertas + ([alerta_geral] if alerta_geral else []) + nomes.get(corte.numero, [])
    bloco.video_final = video_final
    bloco.video_final_desatualizado = desatualizado
    bloco.tem_guia = _tem_guia(destino)
    return bloco


def dados_revisao(pasta: Path) -> list[BlocoRevisao]:
    pasta = Path(pasta)
    palavras = ler_palavras(pasta)
    nomes, alerta_geral = ler_nomes_suspeitos(pasta)
    return [_bloco(pasta, corte, palavras, nomes, alerta_geral) for corte in ler_aprovados(pasta)]


def _linhas_do_bloco(bloco: BlocoRevisao) -> list[str]:
    linhas = [f"## {bloco.numero}. {bloco.titulo}"]
    if bloco.erro:
        return linhas + [f"Erro: {bloco.erro}", ""]
    redes = "YouTube, TikTok e Instagram" if "instagram" in bloco.redes else "YouTube e TikTok"
    if bloco.tem_guia:
        linha_guia = f"Guia de imagens: [guia.md]({bloco.pasta}/{IMAGENS_SUGERIDAS}/guia.md)"
    else:
        linha_guia = "Guia de imagens: não gerado"
    if bloco.musica:
        linha_musica = f"Música: {bloco.musica}"
    else:
        linha_musica = f"Música: nenhuma (sem música para o clima {bloco.clima})"
    return linhas + [
        f"Vídeo: [{CORTE_MP4}]({bloco.pasta}/{CORTE_MP4})",
        linha_guia,
        f"Redes: {redes}",
        f"Publicação sugerida: {bloco.data or 'sem data'}",
        linha_musica,
        f'Antes: "{"... " if bloco.antes else ""}{bloco.antes}"',
        f'Depois: "{bloco.depois}{" ..." if bloco.depois else ""}"',
        f"Vídeo final: {', '.join(bloco.video_final) if bloco.video_final else 'vazio'}",
        f"Alertas: {'; '.join(bloco.alertas) if bloco.alertas else 'nenhum'}",
        "",
    ]


def escrever_revisao(pasta: Path) -> Path:
    pasta = Path(pasta)
    linhas = ["# Revisão do episódio", ""]
    for bloco in dados_revisao(pasta):
        linhas += _linhas_do_bloco(bloco)
    linhas.append("Candidatos descartados: ver [candidatos.md](candidatos.md).")
    caminho = pasta / "revisao.md"
    caminho.write_text("\n".join(linhas) + "\n", "utf-8", newline="\n")
    return caminho
