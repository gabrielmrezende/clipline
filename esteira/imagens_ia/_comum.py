import base64
import binascii
import json
from typing import Callable

from esteira.imagens_ia.provedor import ChaveRecusada, ConteudoRecusado, ErroImagem, ErroTemporario, SemChave
from esteira.publicar.http import ErroRede, _motivo, json_de


def limpar(texto: str, chave: str) -> str:
    """Tira a chave de qualquer texto que vá para uma mensagem de erro."""
    return texto.replace(chave, "***") if chave else texto


def decodificar_imagem(nome: str, b64: object) -> bytes:
    # Quebras de linha e espaços são só formatação: uma imagem paga não pode ser descartada por isso.
    texto = "".join(b64.split()) if isinstance(b64, str) else ""
    if not texto:
        raise ErroImagem(f"{nome} não devolveu imagem")
    try:
        return base64.b64decode(texto, validate=True)
    except (binascii.Error, ValueError):
        raise ErroImagem(f"{nome} devolveu uma imagem ilegível") from None


def chamar(
    nome: str,
    pedir: Callable,
    ler_chave: Callable[[str], str | None],
    url: str,
    cabecalho_chave: str,
    prefixo_chave: str,
    corpo: dict,
    extras: dict | None = None,
    interpretar: Callable[[dict], bytes] = lambda dados: b"",
    recusa: Callable[[ErroRede], str | None] = lambda erro: None,
    chave_invalida: Callable[[ErroRede], bool] = lambda erro: False,
) -> bytes:
    """Faz o POST autenticado e devolve os bytes da imagem, ou levanta o erro certo.

    Toda mensagem de erro levantada passa por `limpar`."""
    chave = ler_chave(nome)
    if not chave:
        raise SemChave(nome)
    cabecalhos = {"Content-Type": "application/json", **(extras or {}), cabecalho_chave: prefixo_chave + chave}
    try:
        _, _, resposta = pedir("POST", url, json.dumps(corpo).encode("utf-8"), cabecalhos)
    except ErroRede as erro:
        if erro.codigo in (401, 403) or chave_invalida(erro):
            raise ChaveRecusada(nome) from None
        if erro.codigo is None or erro.codigo == 429 or erro.codigo >= 500:
            raise ErroTemporario(nome, limpar(str(erro), chave)) from None
        motivo = recusa(erro)
        if motivo is not None:
            raise ConteudoRecusado(f"{nome} recusou o conteúdo: {limpar(motivo, chave)}") from None
        raise ErroImagem(f"{nome} recusou o pedido: {limpar(_motivo(erro.dados), chave)}") from None
    try:
        return interpretar(json_de(resposta))
    except (ConteudoRecusado, ErroImagem) as erro:
        raise type(erro)(limpar(str(erro), chave)) from None
