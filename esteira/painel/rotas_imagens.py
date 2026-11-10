import os
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, StrictInt

from esteira.caminhos import garantir_escrita
from esteira.cortar import IMAGENS_SUGERIDAS, TRABALHO
from esteira.fluxo_imagens import (
    _arquivos, _ler_sugeridas, chave_momento, cortes_com_pedidos, ler_creditos, ler_ia, resumir_episodio,
)
from esteira.imagens_ia.config import PROVEDORES, Config, gravar_config, ler_config, provedor_atual
from esteira.imagens_ia.gerar import MAXIMO_VERSOES, arquivo_de_versao, orcamento_com_itens, pendentes
from esteira.imagens_ia.provedor import ErroImagem
from esteira.painel.fila import PedidoAtivo
from esteira.painel.leitura import NaoEncontrado, resolver_episodio
from esteira.painel.rotas import _TRAVA_GRAVACAO, _pasta_do_corte
from esteira.painel.tarefas_imagens import (
    ERROS_DO_GLOSSARIO, GLOSSARIO_ILEGIVEL, avisos_dos_cortes, executar_fotos, executar_ia, executar_momento_ia,
)
from esteira.pedidos import ARQUIVO, MAXIMO_ESCOLHAS, Momento, _pessoa_citada, pedidos_dos_bytes, texto_dos_pedidos
from esteira.publicar.post import versao_dos_bytes
from esteira.wikimedia import LARGURA_MINIATURA

roteador = APIRouter(prefix="/api")

LARGURA_MAXIMA_MINIATURA = 640  # limite do CLAUDE.md para miniaturas sem confirmação
FOTOS_EM_ANDAMENTO = "Espere o download das fotos terminar."
SEM_CORTES = "Nenhum corte com momentos de imagem."
SEM_PENDENTES = "Nenhuma imagem aprovada para gerar."
FOTOS_REPETIDAS = "Já há um pedido de fotos em andamento para este corte."
IA_REPETIDA = "Já há um pedido de imagens em andamento para este corte."
ORIGEM_FOTOS = "Wikimedia Commons"
PEDIDOS_MUDOU = "O pedidos.json mudou desde que você abriu."
TIPOS_TROCAVEIS = ("foto", "ia")
_MINIATURA = re.compile(r"/((?:lossy-)?page\d+-)?(\d+)px-([^/]*)$")  # com o prefixo das páginas de PDF


class AlteracaoMomento(BaseModel):
    versao: str
    tipo: str | None = None
    escolhas: list[StrictInt] | None = None
    prompt: str | None = None
    aprovado: bool | None = None
    descartar: bool | None = None


class PedidoBusca(BaseModel):
    versao: str
    busca: str


class Confirmacao(BaseModel):
    """Corpo JSON obrigatório dos POSTs que baixam ou custam dinheiro.

    O FastAPI só lê corpo JSON com `Content-Type: application/json`, que o navegador só manda de outra
    origem depois de um preflight: assim uma página qualquer aberta no navegador do dono não dispara
    o pedido (CSRF), nem no modo sem login."""

    confirmado: Literal[True]


class ItemConfirmado(BaseModel):
    corte: StrictInt
    chave: str


class ImagensConfirmadas(BaseModel):
    """Os itens do orçamento que o dono viu e confirmou: só eles são gerados."""

    itens: list[ItemConfirmado]


class DadosProvedor(BaseModel):
    """Só os campos conhecidos: qualquer outro (uma chave, por exemplo) é descartado antes de gravar.

    Os tipos são conferidos pelo `gravar_config`, que dá a mensagem certa para cada campo."""

    modelo: Any = None
    qualidade: Any = None
    preco_usd: Any = None


class ConfigIa(BaseModel):
    provedor: str
    provedores: dict[str, DadosProvedor]


def _miniatura(url: str) -> str:
    """Acima de 640 px, a largura padrão do Wikimedia (500): ele recusa as outras (HTTP 400)."""
    achado = _MINIATURA.search(url)
    if achado and int(achado.group(2)) > LARGURA_MAXIMA_MINIATURA:
        return f"{url[: achado.start()]}/{achado.group(1) or ''}{LARGURA_MINIATURA}px-{achado.group(3)}"
    return url


def _candidata(c) -> dict:
    if not isinstance(c, dict):  # entrada ruim no arquivo: mantém a posição, sem derrubar a tela
        c = {}
    campos = ("titulo", "miniatura", "autor", "licenca", "pagina", "largura", "altura")
    saida = {campo: c.get(campo) for campo in campos}
    saida["miniatura"] = _miniatura(str(c.get("miniatura") or ""))
    return saida


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


def _fotos_prontas(m: Momento, imagens: Path, sugeridas: set[str], creditos: dict[str, dict]) -> list[str]:
    nomes = _arquivos(m)
    if m.tipo == "foto":
        return [
            nome for k, nome in enumerate(nomes, 1)
            if nome in sugeridas and (imagens / nome).is_file() and _mesma_foto(m, k, nome, creditos)
        ]
    return [nome for nome in nomes if nome in sugeridas and (imagens / nome).is_file()]


def _ia_do_momento(m: Momento, imagens: Path, ia: list[dict]) -> list[dict]:
    chave = chave_momento(m)
    itens = [
        i for i in ia
        if i.get("momento") == chave and isinstance(i.get("arquivo"), str)
        and Path(i["arquivo"]).name == i["arquivo"] and (imagens / i["arquivo"]).is_file()
    ]
    saida = [
        {"arquivo": i["arquivo"], "versao": i.get("versao"), "provedor": i.get("provedor", ""), "data": i.get("data", "")}
        for i in itens
    ]
    registrados = {i["arquivo"] for i in ia if i.get("momento") == chave}
    for k in range(1, MAXIMO_VERSOES + 1):  # imagem paga cujo registro falhou: aparece, sem provedor e data
        nome = arquivo_de_versao(chave, k)
        if nome not in registrados and (imagens / nome).is_file():
            saida.append({"arquivo": nome, "versao": k, "provedor": "", "data": ""})
    saida.sort(key=lambda i: i["versao"] if isinstance(i["versao"], int) else 0)
    return saida


def _json_do_momento(m: Momento, destino: Path, pessoas: list[str] | None) -> dict:
    """`pessoas` None: glossário ilegível, a pessoa citada fica desconhecida (null)."""
    imagens = destino / IMAGENS_SUGERIDAS
    sugeridas = set(_ler_sugeridas(destino / TRABALHO))
    return {
        "chave": chave_momento(m),
        "inicio": m.inicio, "fim": m.fim, "fala": m.fala, "tipo": m.tipo, "nome": m.nome,
        "busca": m.busca, "titulo": m.titulo, "veiculo": m.veiculo, "data": m.data,
        "prompt": m.prompt, "aprovado": m.aprovado, "descartar": m.descartar, "motivo": m.motivo,
        "candidatas": [_candidata(c) for c in m.candidatas],
        "escolhas": list(m.escolhas),
        "fotos_prontas": _fotos_prontas(m, imagens, sugeridas, ler_creditos(destino / TRABALHO)),
        "ia": _ia_do_momento(m, imagens, ler_ia(destino / TRABALHO)),
        "pessoa_citada": _pessoa_citada(m.prompt, pessoas) if m.prompt and pessoas is not None else None,
    }


def _pessoas(requisicao: Request) -> list[str]:
    """As pessoas reais do glossário; ilegível vira 422: a regra de pessoa real não falha aberta."""
    try:
        return requisicao.app.state.pessoas()
    except ERROS_DO_GLOSSARIO as erro:
        raise HTTPException(422, GLOSSARIO_ILEGIVEL) from erro


def _pessoas_ou_nada(requisicao: Request) -> list[str] | None:
    """Para só mostrar: com o glossário ilegível a tela abre, sem pessoa citada e com o aviso."""
    try:
        return requisicao.app.state.pessoas()
    except ERROS_DO_GLOSSARIO:
        return None


def _contexto(requisicao: Request, ep: str, n: int) -> tuple[str, Path, Path]:
    """(nome do episódio, pasta do corte, caminho do pedidos.json)."""
    pasta, bloco = _pasta_do_corte(requisicao, ep, n)
    destino = pasta / bloco.pasta
    return pasta.name, destino, destino / TRABALHO / ARQUIVO


def _ler(caminho: Path) -> tuple[str, list[Momento]] | None:
    """(versão, momentos) dos mesmos bytes; None se não existe; 422 se ilegível."""
    try:
        conteudo = caminho.read_bytes()
    except FileNotFoundError:
        return None
    except OSError as erro:
        raise HTTPException(422, f"pedidos.json ilegível: {erro}") from erro
    try:
        return versao_dos_bytes(conteudo), pedidos_dos_bytes(conteudo)
    except (ValueError, KeyError, TypeError, AttributeError) as erro:  # inclui JSON e UTF-8 inválidos
        raise HTTPException(422, f"pedidos.json ilegível: {erro}") from erro


def _achar(momentos: list[Momento], chave: str) -> Momento:
    """O primeiro momento com a chave (se duas entradas repetem a chave, vale a primeira)."""
    for m in momentos:
        if chave_momento(m) == chave:
            return m
    raise NaoEncontrado("momento não encontrado")


def _gravar(requisicao: Request, caminho: Path, momentos: list[Momento]) -> str:
    destino = garantir_escrita(caminho, base_extra=requisicao.app.state.cortes)
    conteudo = texto_dos_pedidos(momentos).encode("utf-8")
    temporario = destino.with_name(destino.name + ".tmp")
    try:
        temporario.write_bytes(conteudo)
        os.replace(temporario, destino)
    except OSError as erro:  # arquivo travado no Windows, disco cheio…
        temporario.unlink(missing_ok=True)
        raise HTTPException(422, f"Não consegui gravar o pedidos.json: {erro}") from erro
    return versao_dos_bytes(conteudo)


def _fotos_ativas(requisicao: Request, episodio: str, n: int) -> bool:
    return requisicao.app.state.fila.ativo(episodio, n, "fotos") is not None


def _bloqueio_das_fotos() -> JSONResponse:
    return JSONResponse({"detail": FOTOS_EM_ANDAMENTO}, status_code=409)


def _conflito(versao_atual: str) -> JSONResponse:
    return JSONResponse({"detail": PEDIDOS_MUDOU, "versao_atual": versao_atual}, status_code=409)


def _resposta(requisicao: Request, destino: Path, m: Momento, versao: str) -> dict:
    return {"momento": _json_do_momento(m, destino, _pessoas_ou_nada(requisicao)), "versao": versao}


@roteador.get("/episodios/{ep}/cortes/{n}/momentos")
def momentos(ep: str, n: int, requisicao: Request) -> dict:
    _, destino, caminho = _contexto(requisicao, ep, n)
    pessoas = _pessoas_ou_nada(requisicao)
    aviso = None if pessoas is not None else GLOSSARIO_ILEGIVEL
    lido = _ler(caminho)
    if lido is None:
        return {"versao": "", "momentos": [], "aviso_glossario": aviso}
    versao, lista = lido
    return {
        "versao": versao,
        "momentos": [_json_do_momento(m, destino, pessoas) for m in lista],
        "aviso_glossario": aviso,
    }


def _aplicar_tipo(m: Momento, tipo: str) -> None:
    if tipo not in TIPOS_TROCAVEIS:
        raise HTTPException(422, "Tipo inválido.")
    if m.tipo == "noticia":
        raise HTTPException(422, "Notícia não troca de tipo pelo painel.")
    if tipo == m.tipo:
        return
    m.tipo = tipo
    m.aprovado = False
    if tipo == "foto" and not m.busca.strip():
        m.busca = m.nome


def _validar_escolhas(m: Momento, escolhas: list[int]) -> None:
    if len(escolhas) > MAXIMO_ESCOLHAS:
        raise HTTPException(422, f"No máximo {MAXIMO_ESCOLHAS} escolhas.")
    if any(not 1 <= e <= len(m.candidatas) for e in escolhas):
        raise HTTPException(422, "Escolha fora da faixa.")
    if len(set(escolhas)) != len(escolhas):
        raise HTTPException(422, "Escolha repetida.")


def _aprovar(m: Momento, pessoas: list[str]) -> None:
    if m.tipo != "ia":
        raise HTTPException(422, "Só momentos de IA têm aprovação.")
    if not m.prompt.strip():
        raise HTTPException(422, "Escreva o prompt antes de aprovar.")
    pessoa = _pessoa_citada(m.prompt, pessoas)
    if pessoa:
        raise HTTPException(422, f"Cita pessoa real ({pessoa}): não pode gerar")
    m.aprovado = True


def _aplicar(m: Momento, corpo: AlteracaoMomento, pessoas: list[str] | None) -> None:
    """`pessoas` só é usado (e só chega lido) quando o corpo aprova."""
    if corpo.tipo is not None:
        _aplicar_tipo(m, corpo.tipo)
    if corpo.escolhas is not None:
        _validar_escolhas(m, corpo.escolhas)
        m.escolhas = list(corpo.escolhas)
    if corpo.prompt is not None and corpo.prompt != m.prompt:
        m.prompt = corpo.prompt
        m.aprovado = False
    if corpo.aprovado is True:
        _aprovar(m, pessoas)
    elif corpo.aprovado is False:
        m.aprovado = False
    if corpo.descartar is not None:
        m.descartar = corpo.descartar


@roteador.put("/episodios/{ep}/cortes/{n}/momentos/{chave}")
def alterar_momento(ep: str, n: int, chave: str, corpo: AlteracaoMomento, requisicao: Request):
    episodio, destino, caminho = _contexto(requisicao, ep, n)
    pessoas = _pessoas(requisicao) if corpo.aprovado is True else None  # aprovar com glossário ilegível: 422
    with _TRAVA_GRAVACAO:  # o trabalhador de fotos e o Claude regravam o mesmo arquivo
        if _fotos_ativas(requisicao, episodio, n):
            return _bloqueio_das_fotos()
        lido = _ler(caminho)
        if lido is None:
            raise NaoEncontrado("pedidos.json não encontrado")
        versao, lista = lido
        if corpo.versao != versao:
            return _conflito(versao)
        m = _achar(lista, chave)
        _aplicar(m, corpo, pessoas)
        nova = _gravar(requisicao, caminho, lista)
    return _resposta(requisicao, destino, m, nova)


@roteador.post("/episodios/{ep}/cortes/{n}/momentos/{chave}/buscar")
def buscar(ep: str, n: int, chave: str, corpo: PedidoBusca, requisicao: Request):
    episodio, destino, caminho = _contexto(requisicao, ep, n)
    busca = corpo.busca.strip()
    if not busca:
        raise HTTPException(422, "Escreva o que buscar.")
    if _fotos_ativas(requisicao, episodio, n):
        return _bloqueio_das_fotos()
    lido = _ler(caminho)
    if lido is None:
        raise NaoEncontrado("pedidos.json não encontrado")
    if lido[0] != corpo.versao:  # já mudou: nem vai à rede
        return _conflito(lido[0])
    if _achar(lido[1], chave).tipo != "foto":
        raise HTTPException(422, "Só momentos de foto buscam no Wikimedia.")
    try:
        candidatas = requisicao.app.state.buscar_candidatas(busca)  # rede: fora da trava
    except (OSError, ValueError) as erro:
        raise HTTPException(422, f"Não consegui buscar no Wikimedia: {erro}") from erro
    with _TRAVA_GRAVACAO:
        if _fotos_ativas(requisicao, episodio, n):
            return _bloqueio_das_fotos()
        lido = _ler(caminho)  # releitura: o arquivo pode ter mudado durante a busca
        if lido is None:
            raise NaoEncontrado("pedidos.json não encontrado")
        versao, lista = lido
        if versao != corpo.versao:  # o Claude regravou durante a busca: as candidatas buscadas são descartadas
            return _conflito(versao)
        m = _achar(lista, chave)
        m.busca = busca
        m.candidatas = [asdict(c) for c in candidatas]
        m.escolhas, m.url, m.bytes, m.resumidas, m.motivo = [], [], [], [], ""
        nova = _gravar(requisicao, caminho, lista)
    return _resposta(requisicao, destino, m, nova)


# --- fotos -----------------------------------------------------------------


def _alvo(requisicao: Request, ep: str, n: int | None) -> tuple[Path, set[int] | None]:
    """(pasta do episódio, números dos cortes; None = todos)."""
    if n is None:
        return resolver_episodio(requisicao.app.state.cortes, ep), None
    pasta, _ = _pasta_do_corte(requisicao, ep, n)
    return pasta, {n}


def _resumo_de_fotos(requisicao: Request, ep: str, n: int | None) -> dict:
    pasta, numeros = _alvo(requisicao, ep, n)
    estado = requisicao.app.state
    fotos, total, resultados = resumir_episodio(
        pasta, numeros, estado.consultar, estado.medir, _pessoas(requisicao), gravar=False, painel=True
    )  # gravar=False: a versão do pedidos.json que a tela tem aberta não pode mudar
    return {
        "fotos": fotos,
        "megabytes": round(total / 1_048_576, 1),
        "origem": ORIGEM_FOTOS,
        "avisos": avisos_dos_cortes(resultados),
    }


@roteador.get("/episodios/{ep}/cortes/{n}/fotos/resumo")
def resumo_de_fotos_do_corte(ep: str, n: int, requisicao: Request) -> dict:
    return _resumo_de_fotos(requisicao, ep, n)


@roteador.get("/episodios/{ep}/fotos/resumo")
def resumo_de_fotos_do_episodio(ep: str, requisicao: Request) -> dict:
    return _resumo_de_fotos(requisicao, ep, None)


def _pedir_fotos(requisicao: Request, ep: str, n: int | None):
    pasta, numeros = _alvo(requisicao, ep, n)
    cortes = sorted(corte.numero for corte, _ in cortes_com_pedidos(pasta, numeros))
    if not cortes:
        raise HTTPException(422, SEM_CORTES)
    estado = requisicao.app.state
    executar = executar_fotos(pasta, set(cortes), _pessoas(requisicao), estado.consultar, estado.medir, estado.baixar)
    with _TRAVA_GRAVACAO:  # um PUT que chega depois sempre recebe 409; um que chegou antes já gravou
        try:
            pedido = estado.fila.pedir_tarefa("fotos", pasta, cortes, executar)
        except PedidoAtivo:
            return JSONResponse({"detail": FOTOS_REPETIDAS}, status_code=409)
    return pedido.como_dict()


@roteador.post("/episodios/{ep}/cortes/{n}/fotos", status_code=202)
def baixar_fotos_do_corte(ep: str, n: int, corpo: Confirmacao, requisicao: Request):
    return _pedir_fotos(requisicao, ep, n)


@roteador.post("/episodios/{ep}/fotos", status_code=202)
def baixar_fotos_do_episodio(ep: str, corpo: Confirmacao, requisicao: Request):
    return _pedir_fotos(requisicao, ep, None)


# --- imagens de IA ---------------------------------------------------------


def _config(requisicao: Request) -> Config:
    try:
        config = ler_config(requisicao.app.state.config_ia)
    except ErroImagem as erro:
        raise HTTPException(422, str(erro)) from erro
    if config.provedor not in PROVEDORES:
        raise HTTPException(422, f"Provedor desconhecido: {config.provedor}")
    return config


def _destinos(requisicao: Request, ep: str, n: int | None) -> list[tuple[int, Path]]:
    pasta, numeros = _alvo(requisicao, ep, n)
    return [(corte.numero, destino) for corte, destino in cortes_com_pedidos(pasta, numeros)]


def _orcamento(requisicao: Request, ep: str, n: int | None) -> dict:
    config = _config(requisicao)
    try:
        return orcamento_com_itens(_destinos(requisicao, ep, n), config)
    except (KeyError, TypeError) as erro:
        raise HTTPException(422, "Configuração de imagens inválida: confira o preço.") from erro


@roteador.get("/episodios/{ep}/cortes/{n}/ia/orcamento")
def orcamento_do_corte(ep: str, n: int, requisicao: Request) -> dict:
    return _orcamento(requisicao, ep, n)


@roteador.get("/episodios/{ep}/ia/orcamento")
def orcamento_do_episodio(ep: str, requisicao: Request) -> dict:
    return _orcamento(requisicao, ep, None)


def _pedir_ia(requisicao: Request, pasta: Path, cortes: list[int], montar):
    """`montar(provedor, config)` devolve o executar; PedidoAtivo vira 409."""
    estado = requisicao.app.state
    config = _config(requisicao)
    try:
        provedor = provedor_atual(config, fabricas=estado.provedores)
    except (ErroImagem, KeyError) as erro:
        raise HTTPException(422, f"Provedor indisponível: {erro}") from erro
    try:
        pedido = estado.fila.pedir_tarefa("ia", pasta, cortes, montar(provedor, config))
    except PedidoAtivo:
        return JSONResponse({"detail": IA_REPETIDA}, status_code=409)
    return pedido.como_dict()


def _gerar_aprovadas(requisicao: Request, ep: str, n: int | None, corpo: ImagensConfirmadas):
    """Gera só os pendentes que estão na lista confirmada; o `_conferir` vale de novo na hora de gerar."""
    _pessoas(requisicao)  # glossário ilegível: nada vai para a fila
    pasta, _ = _alvo(requisicao, ep, n)
    confirmados = {(item.corte, item.chave) for item in corpo.itens}
    cortes: list[int] = []
    pastas: list[Path] = []
    permitidos: set[tuple[Path, str]] = set()
    for numero, destino in _destinos(requisicao, ep, n):
        chaves = {chave_momento(m) for m in pendentes(destino) if (numero, chave_momento(m)) in confirmados}
        if chaves:
            cortes.append(numero)
            pastas.append(destino)
            permitidos |= {(destino, chave) for chave in chaves}
    if not permitidos:
        raise HTTPException(422, SEM_PENDENTES)
    estado = requisicao.app.state
    return _pedir_ia(
        requisicao, pasta, cortes,
        lambda provedor, config: executar_ia(pastas, provedor, config, estado.pessoas, estado.cortes, permitidos),
    )


@roteador.post("/episodios/{ep}/cortes/{n}/ia", status_code=202)
def gerar_ia_do_corte(ep: str, n: int, corpo: ImagensConfirmadas, requisicao: Request):
    return _gerar_aprovadas(requisicao, ep, n, corpo)


@roteador.post("/episodios/{ep}/ia", status_code=202)
def gerar_ia_do_episodio(ep: str, corpo: ImagensConfirmadas, requisicao: Request):
    return _gerar_aprovadas(requisicao, ep, None, corpo)


@roteador.post("/episodios/{ep}/cortes/{n}/momentos/{chave}/ia", status_code=202)
def gerar_de_novo(ep: str, n: int, chave: str, corpo: Confirmacao, requisicao: Request):
    _pessoas(requisicao)  # glossário ilegível: nada vai para a fila
    pasta, bloco = _pasta_do_corte(requisicao, ep, n)
    destino = pasta / bloco.pasta
    lido = _ler(destino / TRABALHO / ARQUIVO)
    if lido is None:
        raise NaoEncontrado("pedidos.json não encontrado")
    _achar(lido[1], chave)
    estado = requisicao.app.state
    return _pedir_ia(
        requisicao, pasta, [n],
        lambda provedor, config: executar_momento_ia(destino, chave, provedor, config, estado.pessoas, estado.cortes),
    )


# --- configurações ---------------------------------------------------------


def _tem_chave(requisicao: Request, provedor: str) -> bool:
    try:
        return bool(requisicao.app.state.tem_chave(provedor))
    except Exception:  # sem keyring instalado ou cofre travado: apenas "sem chave"
        return False


def _configuracao(requisicao: Request, config: Config) -> dict:
    return {
        "provedor": config.provedor,
        "provedores": config.provedores,
        "chaves": {nome: _tem_chave(requisicao, nome) for nome in PROVEDORES},  # nunca a chave em si
    }


@roteador.get("/configuracoes/imagens")
def configuracao_de_imagens(requisicao: Request) -> dict:
    return _configuracao(requisicao, _config(requisicao))


@roteador.put("/configuracoes/imagens")
def gravar_configuracao_de_imagens(corpo: ConfigIa, requisicao: Request) -> dict:
    config = Config(corpo.provedor, {nome: d.model_dump(exclude_unset=True) for nome, d in corpo.provedores.items()})
    try:
        gravar_config(config, caminho=requisicao.app.state.config_ia, base=requisicao.app.state.cortes)
    except ErroImagem as erro:
        raise HTTPException(422, str(erro)) from erro
    except OSError as erro:
        raise HTTPException(422, f"Não consegui gravar a configuração: {erro}") from erro
    return _configuracao(requisicao, config)
