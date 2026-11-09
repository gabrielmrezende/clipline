import base64
import json

import pytest

from esteira.imagens_ia import config
from esteira.imagens_ia.google import Google
from esteira.imagens_ia.openai import OpenAI
from esteira.imagens_ia.provedor import (
    ChaveRecusada,
    ConteudoRecusado,
    ErroImagem,
    ErroTemporario,
    SemChave,
)
from esteira.publicar.http import ErroRede

CHAVE = "chave-secreta-123"
IMAGEM = b"\x89PNG-bytes-da-imagem"
B64 = base64.b64encode(IMAGEM).decode()


class PedirFalso:
    def __init__(self, resposta=None, erro=None):
        self.resposta = resposta
        self.erro = erro
        self.pedidos = []

    def __call__(self, metodo, url, corpo=None, cabecalhos=None):
        self.pedidos.append({"metodo": metodo, "url": url, "corpo": json.loads(corpo), "cabecalhos": cabecalhos})
        if self.erro:
            raise self.erro
        return 200, {}, json.dumps(self.resposta).encode()


def erro_http(codigo, dados=None):
    mensagem = (dados or {}).get("error", {}).get("message", "sem detalhe")
    return ErroRede(f"HTTP {codigo}: {mensagem}", codigo == 429 or codigo >= 500, codigo, dados)


def ler(chave):
    return lambda provedor: chave


CFG_OPENAI = {"modelo": "gpt-image-2", "qualidade": "medium", "preco_usd": 0.041}
CFG_GOOGLE = {"modelo": "gemini-nano-banana-2.1", "qualidade": "1K", "preco_usd": 0.0336}

OK_OPENAI = {"created": 1, "data": [{"b64_json": B64}]}
OK_GOOGLE = {
    "id": "i1",
    "status": "completed",
    "steps": [{"type": "model_output", "content": [{"type": "text", "text": "ok"}, {"type": "image", "data": B64}]}],
}
RECUSA_OPENAI = {
    "error": {
        "code": "moderation_blocked",
        "message": "Seu pedido foi rejeitado pelo sistema de segurança.",
        "type": "image_generation_user_error",
    }
}

FABRICAS = {
    "openai": lambda pedir, chave=CHAVE: OpenAI(CFG_OPENAI, pedir, ler(chave)),
    "google": lambda pedir, chave=CHAVE: Google(CFG_GOOGLE, pedir, ler(chave)),
}
SUCESSO = {"openai": OK_OPENAI, "google": OK_GOOGLE}


def test_openai_sucesso_pedido_conforme_documentacao():
    pedir = PedirFalso(OK_OPENAI)
    imagem = OpenAI(CFG_OPENAI, pedir, ler(CHAVE)).gerar("um gato")
    assert imagem == IMAGEM
    (p,) = pedir.pedidos
    assert p["metodo"] == "POST"
    assert p["url"] == "https://api.openai.com/v1/images/generations"
    assert p["corpo"] == {"model": "gpt-image-2", "prompt": "um gato", "size": "1024x1536", "quality": "medium", "n": 1}
    assert p["cabecalhos"]["Authorization"] == f"Bearer {CHAVE}"
    assert CHAVE not in p["url"] and CHAVE not in json.dumps(p["corpo"])


def test_google_sucesso_pedido_conforme_documentacao():
    pedir = PedirFalso(OK_GOOGLE)
    imagem = Google(CFG_GOOGLE, pedir, ler(CHAVE)).gerar("um gato")
    assert imagem == IMAGEM
    (p,) = pedir.pedidos
    assert p["metodo"] == "POST"
    assert p["url"] == "https://generativelanguage.googleapis.com/v1beta/interactions"
    assert p["corpo"] == {
        "model": "gemini-nano-banana-2.1",
        "input": "um gato",
        "response_format": {"type": "image", "mime_type": "image/jpeg", "aspect_ratio": "9:16", "image_size": "1K"},
    }
    assert p["cabecalhos"]["x-goog-api-key"] == CHAVE
    assert CHAVE not in p["url"] and CHAVE not in json.dumps(p["corpo"])


@pytest.mark.parametrize("nome", ["openai", "google"])
def test_sem_chave_nao_chama_a_rede(nome):
    pedir = PedirFalso(SUCESSO[nome])
    for chave in (None, ""):
        with pytest.raises(SemChave):
            FABRICAS[nome](pedir, chave).gerar("x")
    assert pedir.pedidos == []


@pytest.mark.parametrize("nome", ["openai", "google"])
def test_construir_sem_chave_nao_falha(nome):
    FABRICAS[nome](PedirFalso(), None)


@pytest.mark.parametrize("nome", ["openai", "google"])
@pytest.mark.parametrize("codigo", [401, 403])
def test_chave_recusada(nome, codigo):
    pedir = PedirFalso(erro=erro_http(codigo, {"error": {"message": f"Incorrect API key provided: {CHAVE}"}}))
    with pytest.raises(ChaveRecusada) as e:
        FABRICAS[nome](pedir).gerar("x")
    assert CHAVE not in str(e.value)


@pytest.mark.parametrize("nome", ["openai", "google"])
@pytest.mark.parametrize("codigo", [429, 500, 503])
def test_erros_temporarios(nome, codigo):
    pedir = PedirFalso(erro=erro_http(codigo, {"error": {"message": f"sobrecarga {CHAVE}"}}))
    with pytest.raises(ErroTemporario) as e:
        FABRICAS[nome](pedir).gerar("x")
    assert "sobrecarga" in str(e.value)
    assert CHAVE not in str(e.value)


@pytest.mark.parametrize("nome", ["openai", "google"])
def test_falha_de_conexao_e_temporaria(nome):
    pedir = PedirFalso(erro=ErroRede("falha de conexão: timed out", True))
    with pytest.raises(ErroTemporario, match="timed out"):
        FABRICAS[nome](pedir).gerar("x")


def test_openai_conteudo_recusado_traz_motivo_do_provedor():
    pedir = PedirFalso(erro=erro_http(400, RECUSA_OPENAI))
    with pytest.raises(ConteudoRecusado, match="sistema de segurança"):
        FABRICAS["openai"](pedir).gerar("x")


def test_openai_conteudo_recusado_codigo_antigo():
    dados = {"error": {"code": "content_policy_violation", "message": "Pedido bloqueado pela política."}}
    with pytest.raises(ConteudoRecusado, match="política"):
        FABRICAS["openai"](PedirFalso(erro=erro_http(400, dados))).gerar("x")


@pytest.mark.parametrize("nome", ["openai", "google"])
def test_outro_4xx_vira_erro_imagem_com_motivo(nome):
    dados = {"error": {"code": "invalid_value", "message": f"Tamanho inválido {CHAVE}"}}
    with pytest.raises(ErroImagem) as e:
        FABRICAS[nome](PedirFalso(erro=erro_http(400, dados))).gerar("x")
    assert not isinstance(e.value, (ConteudoRecusado, ChaveRecusada, ErroTemporario, SemChave))
    assert "Tamanho inválido" in str(e.value)
    assert CHAVE not in str(e.value)


def test_google_recusa_em_200_com_erro_da_interacao():
    resposta = {"status": "failed", "steps": [], "errors": [{"code": "x", "message": "Conteúdo bloqueado por segurança."}]}
    with pytest.raises(ConteudoRecusado, match="bloqueado por segurança"):
        FABRICAS["google"](PedirFalso(resposta)).gerar("x")


def test_google_so_texto_em_200_vira_erro_imagem_com_o_texto_limpo():
    resposta = {
        "status": "completed",
        "steps": [{"type": "model_output", "content": [{"type": "text", "text": f"Não consegui gerar. {CHAVE}"}]}],
    }
    with pytest.raises(ErroImagem, match="texto em vez de imagem") as e:
        FABRICAS["google"](PedirFalso(resposta)).gerar("x")
    assert not isinstance(e.value, ConteudoRecusado)
    assert "Não consegui gerar" in str(e.value)
    assert CHAVE not in str(e.value)


def test_google_recusa_em_200_nao_vaza_a_chave():
    resposta = {"status": "failed", "steps": [], "errors": [{"message": f"bloqueado {CHAVE}"}]}
    with pytest.raises(ConteudoRecusado) as e:
        FABRICAS["google"](PedirFalso(resposta)).gerar("x")
    assert CHAVE not in str(e.value)


def test_google_chave_invalida_vem_como_400():
    dados = {
        "error": {
            "code": 400,
            "message": "API key not valid. Please pass a valid API key.",
            "status": "INVALID_ARGUMENT",
            "details": [{"@type": "type.googleapis.com/google.rpc.ErrorInfo", "reason": "API_KEY_INVALID", "domain": "googleapis.com"}],
        }
    }
    with pytest.raises(ChaveRecusada):
        FABRICAS["google"](PedirFalso(erro=erro_http(400, dados))).gerar("x")


def test_google_chave_invalida_so_pela_mensagem():
    dados = {"error": {"code": 400, "message": "API key not valid. Please pass a valid API key.", "status": "INVALID_ARGUMENT"}}
    with pytest.raises(ChaveRecusada):
        FABRICAS["google"](PedirFalso(erro=erro_http(400, dados))).gerar("x")


@pytest.mark.parametrize(
    "nome,resposta",
    [("openai", {"data": []}), ("openai", {}), ("google", {"status": "completed", "steps": []}), ("google", {})],
)
def test_200_sem_imagem(nome, resposta):
    with pytest.raises(ErroImagem, match=f"{nome} não devolveu imagem") as e:
        FABRICAS[nome](PedirFalso(resposta)).gerar("x")
    assert not isinstance(e.value, ConteudoRecusado)


@pytest.mark.parametrize("nome", ["openai", "google"])
def test_base64_invalido(nome):
    resposta = {
        "openai": {"data": [{"b64_json": "@@@"}]},
        "google": {"steps": [{"type": "model_output", "content": [{"type": "image", "data": "@@@"}]}]},
    }[nome]
    with pytest.raises(ErroImagem, match="ilegível"):
        FABRICAS[nome](PedirFalso(resposta)).gerar("x")


def test_provedor_atual_sem_fabricas_devolve_os_adaptadores():
    cfg = config.padrao()
    assert isinstance(config.provedor_atual(cfg), OpenAI)
    cfg.provedor = "google"
    atual = config.provedor_atual(cfg)
    assert isinstance(atual, Google)
    assert atual.nome == "google"
