"""Provedor de mentira para os testes de ponta a ponta (ESTEIRA_PAINEL_IMAGEM_FALSA=1). Não usa rede nem chave."""

import io

from PIL import Image


class Falso:
    def __init__(self, nome: str) -> None:
        self.nome = nome

    def gerar(self, prompt: str, proporcao: str = "9:16") -> bytes:
        buffer = io.BytesIO()
        Image.new("RGB", (1024, 1536), (128, 128, 128)).save(buffer, "PNG")
        return buffer.getvalue()


def fabricas() -> dict:
    return {"openai": lambda _dados: Falso("openai"), "google": lambda _dados: Falso("google")}


def tem_chave(_provedor: str) -> bool:
    return True
