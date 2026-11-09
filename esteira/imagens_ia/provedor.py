from typing import Protocol


class ErroImagem(Exception):
    """Falha ao configurar ou usar um provedor de imagem de IA."""


class SemChave(ErroImagem):
    def __init__(self, provedor: str):
        super().__init__(mensagem_sem_chave(provedor))


class ChaveRecusada(ErroImagem):
    def __init__(self, provedor: str):
        super().__init__(mensagem_chave_recusada(provedor))


class ErroTemporario(ErroImagem):
    def __init__(self, provedor: str, motivo: str):
        super().__init__(mensagem_temporario(provedor, motivo))


class ConteudoRecusado(ErroImagem):
    """O provedor recusou o pedido por conteúdo (política de segurança)."""


def mensagem_sem_chave(provedor: str) -> str:
    return f"Rode python -m esteira imagens conectar {provedor}"


def mensagem_chave_recusada(provedor: str) -> str:
    return f"Chave recusada pelo {provedor}: conecte de novo."


def mensagem_temporario(provedor: str, motivo: str) -> str:
    return f"{provedor} indisponível agora: {motivo}. Tente de novo."


class Provedor(Protocol):
    nome: str

    def gerar(self, prompt: str, proporcao: str = "9:16") -> bytes: ...
