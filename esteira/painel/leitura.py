from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from esteira.cortar import TRABALHO
from esteira.publicar.post import ErroPost, conferir_textos, ler_post_completo
from esteira.receita import ler_receita
from esteira.revisao import BlocoRevisao, dados_revisao

FORMATO_DATA = "%Y-%m-%d %H:%M"


class CaminhoProibido(Exception):
    pass


class NaoEncontrado(Exception):
    pass


def _resolver_dentro(base: Path, nome: str) -> Path:
    if not nome or "/" in nome or "\\" in nome or ".." in nome or ":" in nome or Path(nome).is_absolute():
        raise CaminhoProibido(f"nome recusado: {nome!r}")
    base_real = Path(base).resolve()
    alvo = (base_real / nome).resolve()
    if alvo.parent != base_real:
        raise CaminhoProibido(f"fora da pasta permitida: {nome!r}")
    return alvo


def resolver_episodio(cortes: Path, nome: str) -> Path:
    alvo = _resolver_dentro(cortes, nome)
    if not alvo.is_dir():
        raise NaoEncontrado(f"episódio não encontrado: {nome}")
    return alvo


def resolver_arquivo(pasta: Path, nome: str, extensoes: set[str]) -> Path:
    alvo = _resolver_dentro(pasta, nome)
    if alvo.suffix.lower() not in extensoes:
        raise CaminhoProibido(f"extensão não permitida: {nome!r}")
    if not alvo.is_file():
        raise NaoEncontrado(f"arquivo não encontrado: {nome}")
    return alvo


def _credito(pasta_corte: Path) -> str | None:
    try:
        receita = ler_receita(Path(pasta_corte) / TRABALHO)
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return receita.musica.credito if receita.musica and receita.musica.credito else None


def mensagem_post(erro: Exception) -> str:
    """A mensagem de um erro ao ler o post.md, sem o caminho absoluto."""
    if isinstance(erro, FileNotFoundError):
        return "post.md não encontrado"
    if isinstance(erro, UnicodeDecodeError):
        return "post.md ilegível: não está em UTF-8"
    if isinstance(erro, OSError):
        return "post.md ilegível"
    return str(erro)


def avisos_post(pasta_corte: Path, redes: list[str]) -> list[str]:
    pasta_corte = Path(pasta_corte)
    try:
        textos = ler_post_completo(pasta_corte / "post.md").textos
    except (ErroPost, OSError, UnicodeDecodeError) as erro:
        return [f"post: {mensagem_post(erro)}"]
    return conferir_textos(textos, _credito(pasta_corte), set(redes))


def selo(bloco: BlocoRevisao, avisos: list[str]) -> str:
    if bloco.erro:
        return "erro"
    if bloco.alertas or avisos:
        return "com alerta"
    if not bloco.video_final:
        return "sem vídeo final"
    return "pronto"


def resumo_episodio(pasta: Path, agora: datetime) -> dict:
    pasta = Path(pasta)
    resumo = {"nome": pasta.name, "total": 0, "prontos": 0, "proxima_data": None, "aviso": None}
    if not (pasta / "aprovados.json").exists():
        resumo["aviso"] = "sem cortes aprovados"
        return resumo
    try:
        blocos = dados_revisao(pasta)
    except (OSError, ValueError, KeyError, TypeError) as erro:
        resumo["aviso"] = f"episódio ilegível: {erro}"
        return resumo
    resumo["total"] = len(blocos)
    resumo["prontos"] = sum(1 for b in blocos if b.video_final)
    datas = []
    for bloco in blocos:
        try:
            if bloco.data and datetime.strptime(bloco.data, FORMATO_DATA) >= agora:
                datas.append(bloco.data)
        except ValueError:
            continue
    resumo["proxima_data"] = min(datas) if datas else None
    return resumo


def listar_episodios(cortes: Path, agora: datetime) -> list[dict]:
    cortes = Path(cortes)
    if not cortes.is_dir():
        return []
    pastas = sorted((p for p in cortes.iterdir() if p.is_dir()), key=lambda p: p.name)
    return [resumo_episodio(p, agora) for p in pastas]


def bloco_json(bloco: BlocoRevisao, avisos: list[str]) -> dict:
    return {**asdict(bloco), "avisos_post": avisos, "selo": selo(bloco, avisos)}
