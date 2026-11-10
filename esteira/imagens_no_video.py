"""Qual imagem de cada momento entra no corte.mp4, e em que tempo de tela.

A chave e os nomes dos arquivos saem do tempo proposto (pedidos.json); o tempo de tela, do ajuste de 2 a 5 s
feito numa cópia. Só entram arquivos prontos: os que a própria esteira gravou e que ainda valem.
"""

import copy
from dataclasses import dataclass
from pathlib import Path

from esteira.cortar import IMAGENS_SUGERIDAS, TRABALHO
from esteira.fluxo_imagens import _arquivos, _ler_sugeridas, chave_momento, ler_creditos, ler_ia
from esteira.imagens_ia.gerar import MAXIMO_VERSOES, arquivo_de_versao
from esteira.pedidos import ARQUIVO, TIPOS, Momento, ajustar_tempos, ler_pedidos, rotulo_momento
from esteira.receita import ImagemNoVideo, duracao_principal, ler_receita

FALTA = {"foto": "foto não baixada", "noticia": "cartão não gerado", "ia": "IA ainda não gerada"}
ERROS_DE_LEITURA = (OSError, ValueError, KeyError, TypeError, AttributeError)


@dataclass
class Escolha:
    chave: str
    momento: Momento  # o do pedidos.json (tempo proposto)
    inicio_tela: float | None  # None: descartado (pelo dono ou pelo ajuste)
    fim_tela: float | None
    prontas: list[str]
    arquivo: str | None  # o que entra no vídeo; None = fora
    alerta: str | None


def _mesma_foto(m: Momento, k: int, nome: str, creditos: dict[str, dict]) -> bool:
    """O arquivo da opção k é a candidata escolhida agora? Pela procedência gravada no download;
    sem ela (corte antigo, sem creditos.json), pelo último resumo."""
    credito = creditos.get(nome)
    if credito is None:
        return k <= len(m.resumidas) and m.resumidas[k - 1] == m.escolhas[k - 1]
    escolha = m.escolhas[k - 1]
    candidata = m.candidatas[escolha - 1] if type(escolha) is int and 1 <= escolha <= len(m.candidatas) else None
    if not isinstance(candidata, dict):
        return False
    return any(credito.get(campo) and credito.get(campo) == candidata.get(campo) for campo in ("pagina", "titulo"))


def fotos_prontas(m: Momento, chave: str, imagens: Path, sugeridas: set[str], creditos: dict[str, dict]) -> list[str]:
    """Fotos (na ordem das escolhas) e cartão de notícia que a esteira gravou e que ainda valem."""
    nomes = _arquivos(m, chave)
    if m.tipo == "foto":
        return [
            nome for k, nome in enumerate(nomes, 1)
            if nome in sugeridas and (imagens / nome).is_file() and _mesma_foto(m, k, nome, creditos)
        ]
    return [nome for nome in nomes if nome in sugeridas and (imagens / nome).is_file()]


def versoes_ia(chave: str, imagens: Path, ia: list[dict]) -> list[dict]:
    """As versões de IA do momento que existem no disco, em ordem de versão (as pagas sem registro também)."""
    itens = [
        i for i in ia
        if i.get("momento") == chave and isinstance(i.get("arquivo"), str)
        and Path(i["arquivo"]).name == i["arquivo"] and (imagens / i["arquivo"]).is_file()
    ]
    saida = [
        {"arquivo": i["arquivo"], "versao": i.get("versao"), "provedor": i.get("provedor", ""), "data": i.get("data", "")}
        for i in itens
    ]
    registrados = {i["arquivo"] for i in ia if i.get("momento") == chave and isinstance(i.get("arquivo"), str)}
    for k in range(1, MAXIMO_VERSOES + 1):  # imagem paga cujo registro falhou: aparece, sem provedor e data
        nome = arquivo_de_versao(chave, k)
        if nome not in registrados and (imagens / nome).is_file():
            saida.append({"arquivo": nome, "versao": k, "provedor": "", "data": ""})
    saida.sort(key=lambda i: i["versao"] if isinstance(i["versao"], int) else 0)
    return saida


def _prontas(m, chave, imagens, sugeridas, creditos, ia) -> list[str]:
    """Em ordem de preferência: foto pela ordem das escolhas, IA da versão mais nova, notícia o cartão."""
    if m.tipo == "ia":
        return [v["arquivo"] for v in reversed(versoes_ia(chave, imagens, ia))]
    return fotos_prontas(m, chave, imagens, sugeridas, creditos)


def escolhas_do_corte(destino: Path, momentos: list[Momento], duracao: float | None) -> list[Escolha]:
    """Uma escolha por momento, na ordem do pedidos.json. `duracao` None: sem ajuste de tempo."""
    destino = Path(destino)
    imagens, trabalho = destino / IMAGENS_SUGERIDAS, destino / TRABALHO
    sugeridas, creditos, ia = set(_ler_sugeridas(trabalho)), ler_creditos(trabalho), ler_ia(trabalho)
    telas = copy.deepcopy(momentos)
    if duracao is not None:
        ajustar_tempos(telas, duracao)
    escolhas = []
    for posicao, (m, tela) in enumerate(zip(momentos, telas), 1):
        chave = chave_momento(m)
        if m.descartar:
            escolhas.append(Escolha(chave, m, None, None, [], None, None))
            continue
        prontas = _prontas(m, chave, imagens, sugeridas, creditos, ia) if m.tipo in TIPOS else []
        rotulo = rotulo_momento(posicao, m, painel=True)
        fora = None
        if tela.descartar:
            fora = tela.motivo
        elif m.tipo not in TIPOS:
            fora = "tipo inválido"
        elif tela.inicio < 0 or tela.inicio >= tela.fim or (duracao is not None and tela.fim > duracao):
            fora = "fora do corte"
        elif not prontas:
            fora = FALTA[m.tipo]
        if fora is not None:
            inicio, fim = (None, None) if tela.descartar else (tela.inicio, tela.fim)
            escolhas.append(Escolha(chave, m, inicio, fim, prontas, None, f"imagem {rotulo} fora do vídeo: {fora}"))
            continue
        arquivo = m.no_video if m.no_video in prontas else prontas[0]
        alerta = f"imagem {rotulo}: {m.no_video} não está pronta, entrou {arquivo}" if m.no_video and m.no_video != arquivo else None
        escolhas.append(Escolha(chave, m, tela.inicio, tela.fim, prontas, arquivo, alerta))
    return escolhas


def imagens_do_corte(destino: Path) -> tuple[list[ImagemNoVideo], list[str]]:
    """As imagens que entram no corte.mp4 (em ordem de tempo) e os alertas do que ficou de fora."""
    destino = Path(destino)
    trabalho = destino / TRABALHO
    if not (trabalho / ARQUIVO).exists():
        return [], []
    try:
        momentos = ler_pedidos(trabalho)
    except ERROS_DE_LEITURA as erro:
        return [], [f"imagens: pedidos.json ilegível: {erro}"]
    try:
        duracao = duracao_principal(ler_receita(trabalho))
    except ERROS_DE_LEITURA:
        duracao = None
    lista, alertas = [], []
    for e in escolhas_do_corte(destino, momentos, duracao):
        if e.alerta:
            alertas.append(e.alerta)
        if e.arquivo is None:
            continue
        caminho = destino / IMAGENS_SUGERIDAS / e.arquivo
        lista.append(ImagemNoVideo(
            e.inicio_tela, e.fim_tela, f"{IMAGENS_SUGERIDAS}/{e.arquivo}", e.momento.tipo, e.chave,
            caminho.stat().st_mtime_ns,
        ))
    return sorted(lista, key=lambda i: i.inicio), alertas
