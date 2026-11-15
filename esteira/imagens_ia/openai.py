from esteira.imagens_ia import _comum, chaves
from esteira.publicar import http

URL = "https://api.openai.com/v1/images/generations"
# Tamanhos conferidos em 15/11/2026 na documentação da OpenAI (developers.openai.com: referência de
# images/generate e guia de geração de imagens). O gpt-image-2 e os mais novos (2.5, 2.6) aceitam qualquer
# LARGURAxALTURA com lados múltiplos de 16, até 3840 px, proporção até 3:1 e de 655.360 a 8.294.400 pixels.
# Os anteriores (gpt-image-1, 1.5, mini) só aceitam 1024x1024, 1536x1024 e 1024x1536.
TAMANHO = "1024x1536"  # 2:3, o vertical dos modelos anteriores: o vídeo corta as laterais
TAMANHO_9_16 = "864x1536"  # 9:16 exato; mesma altura e menos pixels que o 1024x1536, que é o preço tabelado
MODELOS_TAMANHO_LIVRE = ("gpt-image-2",)  # prefixo: vale para gpt-image-2, gpt-image-2.5-* e gpt-image-2.6-*
CODIGOS_RECUSA = ("moderation_blocked", "content_policy_violation")


def _recusa(erro: http.ErroRede) -> str | None:
    dados = erro.dados.get("error")
    if erro.codigo == 400 and isinstance(dados, dict) and dados.get("code") in CODIGOS_RECUSA:
        return http._motivo(erro.dados)
    return None


def tamanho(modelo: str, proporcao: str = "9:16") -> str:
    """O vertical mais próximo de 9:16 que o modelo aceita."""
    if proporcao == "9:16" and modelo.startswith(MODELOS_TAMANHO_LIVRE):
        return TAMANHO_9_16
    return TAMANHO


class OpenAI:
    nome = "openai"

    def __init__(self, config: dict, pedir=http.pedir, ler_chave=chaves.ler_chave):
        self.config = config
        self._pedir = pedir
        self._ler_chave = ler_chave

    def gerar(self, prompt: str, proporcao: str = "9:16") -> bytes:
        corpo = {
            "model": self.config["modelo"],
            "prompt": prompt,
            "size": tamanho(self.config["modelo"], proporcao),
            "quality": self.config["qualidade"],
            "n": 1,
        }
        return _comum.chamar(
            self.nome, self._pedir, self._ler_chave, URL, "Authorization", "Bearer ", corpo,
            interpretar=self._imagem, recusa=_recusa,
        )

    def _imagem(self, dados: dict) -> bytes:
        lista = dados.get("data")
        primeiro = lista[0] if isinstance(lista, list) and lista and isinstance(lista[0], dict) else {}
        return _comum.decodificar_imagem(self.nome, primeiro.get("b64_json"))
