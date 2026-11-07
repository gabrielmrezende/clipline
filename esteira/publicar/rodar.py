from datetime import datetime
from pathlib import Path

from esteira.caminhos import AUTOMACAO, CORTES
from esteira.cortar import ler_aprovados, pasta_do_corte
from esteira.publicar.agendar import FUSO
from esteira.publicar.config import ler_modos
from esteira.publicar.envio import MAX_TENTATIVAS, assinatura, enviar
from esteira.publicar.fila import ARQUIVO, Item, Ocupado, gravar_fila, ler_fila, trava
from esteira.publicar.post import ErroPost, ler_post

TRAVA = AUTOMACAO / "publicar.trava"
INTERROMPIDO = "envio interrompido: confira no app e use publicar marcar"
MUDOU = "o vídeo ou o texto mudou depois da confirmação; agende de novo"

__all__ = ["MAX_TENTATIVAS", "rodar_episodio", "rodar_tudo"]


def _relato(item: Item) -> str:
    texto = f"{item.numero:02d} {item.rede}: {item.estado}"
    if item.link:
        texto += f" {item.link}"
    if item.erro and item.estado != "rascunho":
        texto += f" ({item.erro})"
    return texto


def _material(pasta: Path, numero: int):
    corte = next((c for c in ler_aprovados(pasta) if c.numero == numero), None)
    if corte is None:
        raise ErroPost(f"corte {numero} não está no aprovados.json")
    pasta_corte = pasta_do_corte(pasta, corte)
    final = pasta_corte / "video-final"
    videos = [p for p in final.glob("*") if p.suffix.lower() == ".mp4"] if final.exists() else []
    if len(videos) != 1:
        raise ErroPost(f"video-final/ com {len(videos)} vídeos: deixe exatamente um")
    return videos[0], ler_post(pasta_corte / "post.md")


def rodar_episodio(pasta: Path, agora: datetime, modos: dict, redes_api: dict) -> list[str]:
    itens = ler_fila(pasta)
    linhas: list[str] = []
    interrompidos = [i for i in itens if i.estado == "enviando"]
    for item in interrompidos:
        item.estado, item.erro = "conferir", INTERROMPIDO
        linhas.append(_relato(item))
    if interrompidos:
        gravar_fila(pasta, itens)
    def venceu(i: Item) -> bool:
        # o YouTube sobe no --confirmar; um item dele na fila é nova tentativa: vai já
        return i.rede == "youtube" or datetime.fromisoformat(i.data) <= agora

    vencidos = sorted(
        (i for i in itens if i.estado == "agendado" and venceu(i)),
        key=lambda i: datetime.fromisoformat(i.data),
    )
    for item in vencidos:
        try:
            video, textos = _material(pasta, item.numero)
        except ErroPost as erro:
            item.estado, item.erro = "erro", str(erro)
            gravar_fila(pasta, itens)
        else:
            if item.assinatura and assinatura(video, textos, item.rede) != item.assinatura:
                item.estado, item.erro = "erro", MUDOU
                gravar_fila(pasta, itens)
            else:
                enviar(pasta, itens, item, video, textos, modos.get(item.rede, ""), redes_api[item.rede])
        linhas.append(_relato(item))
    return linhas


def _redes_reais() -> dict:
    from esteira.publicar.instagram import Instagram
    from esteira.publicar.tiktok import TikTok
    from esteira.publicar.youtube import YouTube

    return {"youtube": YouTube(), "instagram": Instagram(), "tiktok": TikTok()}


def rodar_tudo(base: Path = CORTES, agora: datetime | None = None, redes_api: dict | None = None,
               caminho_trava: Path = TRAVA, modos: dict | None = None) -> list[str]:
    agora = agora or datetime.now(FUSO)
    try:
        with trava(caminho_trava):
            modos = modos or ler_modos()
            redes_api = redes_api or _redes_reais()
            linhas: list[str] = []
            for arquivo in sorted(Path(base).glob(f"*/{ARQUIVO}")):
                try:
                    linhas += rodar_episodio(arquivo.parent, agora, modos, redes_api)
                except Exception as erro:  # um episódio com problema não para os outros
                    linhas.append(f"{arquivo.parent.name}: erro: {erro}")
            return linhas
    except Ocupado:
        return ["outra execução em andamento"]
