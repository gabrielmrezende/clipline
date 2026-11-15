"""Cliente falso do SDK `anthropic` para os testes da revisão visual e do classificador (sem rede, sem chave)."""

import json
from types import SimpleNamespace


def resposta(dados: dict | str, parada: str = "end_turn", entrada: int = 1000, saida: int = 200, categoria=None):
    texto = dados if isinstance(dados, str) else json.dumps(dados, ensure_ascii=False)
    return SimpleNamespace(
        content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=texto)],
        stop_reason=parada,
        stop_details=SimpleNamespace(category=categoria) if parada == "refusal" else None,
        usage=SimpleNamespace(input_tokens=entrada, output_tokens=saida),
    )


class ClienteFalso:
    """Responde na ordem dada (uma exceção na lista é levantada) e guarda cada pedido em `pedidos`."""

    def __init__(self, *respostas) -> None:
        self.respostas = list(respostas)
        self.pedidos: list[dict] = []
        self.messages = self

    def create(self, **pedido):
        self.pedidos.append(pedido)
        proxima = self.respostas.pop(0)
        if isinstance(proxima, BaseException):
            raise proxima
        return proxima
