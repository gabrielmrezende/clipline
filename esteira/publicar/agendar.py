from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from esteira.aprovacao import imagens_aprovadas
from esteira.cortar import TRABALHO, ler_aprovados, pasta_do_corte
from esteira.fluxo_imagens import ler_creditos, ler_ia
from esteira.midia import ErroMidia, sondar
from esteira.publicar.envio import assinatura, enviar
from esteira.publicar.fila import Item, gravar_fila, ler_fila
from esteira.publicar.post import ErroPost, Textos, conferir_textos, faltando_aviso_ia, ler_post
from esteira.receita import ler_receita
from esteira.revisao import video_final_desatualizado

FUSO = timezone(timedelta(hours=-3))
REDES = ("youtube", "instagram", "tiktok")
INATIVOS = ("cancelado", "erro")
LIMITE_SHORTS = 180
VIDEO_FINAL_DESATUALIZADO = "vídeo final mais antigo que o corte.mp4: aprove de novo no painel ou refaça no CapCut"
DIAS = ("segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo")
NOMES = {"youtube": "YouTube", "instagram": "Instagram", "tiktok": "TikTok"}
MODOS_TEXTO = {
    ("youtube", "privado"): "privado: você muda para agendado no Studio",
    ("youtube", "agendado"): "agendado: o YouTube publica sozinho",
    ("tiktok", "rascunho"): "rascunho: o texto não vai junto; cole no app",
    ("tiktok", "direto"): "direto: o PC publica no horário",
}


class ErroAgendar(Exception):
    pass


@dataclass
class Pedido:
    pasta: Path
    numero: int
    titulo: str
    video: Path
    duracao: float
    textos: Textos
    data: datetime
    redes: list[str]
    imagens_ia: int = 0
    imagens_no_video: list[dict] | None = None  # do vídeo aprovado pelo painel; None = desconhecidas (CapCut)
    creditos: list[str] = field(default_factory=list)


def ler_data(texto: str, agora: datetime) -> datetime:
    try:
        data = datetime.strptime(texto.strip(), "%Y-%m-%d %H:%M").replace(tzinfo=FUSO)
    except ValueError:
        raise ErroAgendar("data inválida: use AAAA-MM-DD HH:MM") from None
    if data <= agora:
        raise ErroAgendar("data no passado")
    return data


def _minutos(segundos: float) -> str:
    total = round(segundos)
    return f"{total // 60}:{total % 60:02d}"


def _credito(pasta_corte: Path) -> str | None:
    try:
        receita = ler_receita(pasta_corte / TRABALHO)
    except FileNotFoundError:
        return None
    return receita.musica.credito if receita.musica and receita.musica.credito else None


def _creditos_das_fotos(pasta_corte: Path, imagens: list[dict]) -> list[str]:
    creditos = ler_creditos(pasta_corte / TRABALHO)
    linhas = []
    for imagem in imagens:
        if imagem.get("tipo") != "foto":
            continue
        nome = Path(str(imagem.get("arquivo", ""))).name
        # O crédito gravado na montagem é o da foto que está no vídeo; o creditos.json pode já ser de outra.
        c = imagem.get("credito") if isinstance(imagem.get("credito"), dict) else creditos.get(nome)
        if c:
            linhas.append(f"- {c.get('autor', '')}, {c.get('licenca', '')}, {c.get('pagina', '')}")
        else:
            linhas.append(f"- {nome}: crédito não encontrado (confira o guia.md)")
    return linhas


def preparar_pedido(pasta_episodio: Path, numero: int, data: str, redes: list[str], agora: datetime) -> Pedido:
    pasta_episodio = Path(pasta_episodio)
    for rede in redes:
        if rede not in REDES:
            raise ErroAgendar(f"rede desconhecida: {rede}; use {', '.join(REDES)}")
    redes = [r for r in REDES if r in redes]
    corte = next((c for c in ler_aprovados(pasta_episodio) if c.numero == numero), None)
    if corte is None:
        raise ErroAgendar(f"corte {numero} não está no aprovados.json")
    pasta_corte = pasta_do_corte(pasta_episodio, corte)
    problemas: list[str] = []

    pasta_final = pasta_corte / "video-final"
    videos = sorted(p for p in pasta_final.glob("*") if p.suffix.lower() == ".mp4") if pasta_final.exists() else []
    video, duracao = None, 0.0
    no_video: list[dict] | None = None
    if not videos:
        problemas.append("video-final/ sem vídeo")
    elif len(videos) > 1:
        problemas.append(f"video-final/ com {len(videos)} vídeos: deixe só um")
    else:
        video = videos[0]
        try:
            midia = sondar(video)
        except ErroMidia as erro:
            problemas.append(f"vídeo ilegível: {erro}")
        else:
            duracao = midia.duracao
            if (midia.largura, midia.altura) != (1080, 1920):
                problemas.append(f"vídeo {midia.largura}x{midia.altura}, esperado 1080x1920")
            if "youtube" in redes and midia.duracao > LIMITE_SHORTS:
                problemas.append(f"youtube: vídeo com {_minutos(midia.duracao)}; o Shorts aceita até 3:00")
        if video_final_desatualizado(pasta_corte, video):
            problemas.append(VIDEO_FINAL_DESATUALIZADO)
        no_video = imagens_aprovadas(pasta_corte, video)

    textos = None
    try:
        textos = ler_post(pasta_corte / "post.md")
    except ErroPost as erro:
        problemas.append(str(erro))
    else:
        problemas += conferir_textos(textos, _credito(pasta_corte), set(redes))
        if no_video and any(i.get("tipo") == "ia" for i in no_video):
            problemas += faltando_aviso_ia(textos, set(redes))

    quando = None
    try:
        quando = ler_data(data, agora)
    except ErroAgendar as erro:
        problemas.append(str(erro))

    for item in ler_fila(pasta_episodio):
        if item.numero == numero and item.rede in redes and item.estado not in INATIVOS:
            problemas.append(f"{item.rede}: corte {numero} já agendado ({item.estado})")

    if problemas:
        raise ErroAgendar("\n".join(problemas))
    return Pedido(
        pasta_episodio, numero, corte.titulo, video, duracao, textos, quando, redes, len(ler_ia(pasta_corte / TRABALHO)),
        no_video, _creditos_das_fotos(pasta_corte, no_video or []),
    )


def _data_por_extenso(data: datetime) -> str:
    return f"{DIAS[data.weekday()]}, {data:%d/%m/%Y} às {data:%H:%M} (Brasília)"


def resumo(pedido: Pedido, modos: dict) -> str:
    linhas = [
        f"Corte {pedido.numero}: {pedido.titulo}",
        f"Vídeo: {pedido.video.name} ({_minutos(pedido.duracao)}, 1080x1920)",
        f"Data: {_data_por_extenso(pedido.data)}",
    ]
    if pedido.imagens_no_video is not None:
        ia = sum(1 for i in pedido.imagens_no_video if i.get("tipo") == "ia")
        if ia:
            linhas.append(f"Imagens de IA no vídeo: {ia} (o aviso está nos textos).")
        if pedido.creditos:
            linhas += ["Créditos das fotos no vídeo:", *pedido.creditos]
    elif pedido.imagens_ia:
        n = pedido.imagens_ia
        gerada = "imagem de IA gerada" if n == 1 else "imagens de IA geradas"
        linhas.append(f"Este corte tem {n} {gerada}: confira se o vídeo final usa alguma e inclua o aviso.")
    t = pedido.textos
    corpos = {
        "youtube": f"Título: {t.youtube_titulo}\n\n{t.youtube_descricao}",
        "instagram": t.instagram,
        "tiktok": t.tiktok,
    }
    for rede in pedido.redes:
        modo = MODOS_TEXTO.get((rede, modos.get(rede)))
        cabecalho = f"{NOMES[rede]} ({modo})" if modo else NOMES[rede]
        linhas += ["", f"== {cabecalho}", corpos[rede]]
    return "\n".join(linhas)


def confirmar(pedido: Pedido, modos: dict, redes_api: dict[str, object]) -> list[Item]:
    itens = [
        i for i in ler_fila(pedido.pasta)
        if not (i.numero == pedido.numero and i.rede in pedido.redes and i.estado in INATIVOS)
    ]
    novos = [
        Item(pedido.numero, rede, pedido.data.isoformat(), assinatura=assinatura(pedido.video, pedido.textos, rede))
        for rede in pedido.redes
    ]
    itens += novos
    gravar_fila(pedido.pasta, itens)
    for item in novos:
        if item.rede == "youtube":
            enviar(pedido.pasta, itens, item, pedido.video, pedido.textos, modos["youtube"], redes_api["youtube"])
    return novos
