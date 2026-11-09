from esteira.imagens_ia import _comum, chaves
from esteira.publicar import http

URL = "https://api.openai.com/v1/images/generations"
TAMANHO = "1024x1536"  # vertical padrão do gpt-image-2; a Task 4 ajusta para 1080x1920
CODIGOS_RECUSA = ("moderation_blocked", "content_policy_violation")


def _recusa(erro: http.ErroRede) -> str | None:
    dados = erro.dados.get("error")
    if erro.codigo == 400 and isinstance(dados, dict) and dados.get("code") in CODIGOS_RECUSA:
        return http._motivo(erro.dados)
    return None


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
            "size": TAMANHO,
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
