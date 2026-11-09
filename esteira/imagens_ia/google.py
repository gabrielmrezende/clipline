from esteira.imagens_ia import _comum, chaves
from esteira.imagens_ia.provedor import ConteudoRecusado
from esteira.publicar import http

URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
REVISAO_API = "2026-05-20"
PROPORCAO = "9:16"


def _blocos(dados: dict) -> list[dict]:
    blocos = []
    for passo in dados.get("steps") or []:
        if isinstance(passo, dict) and passo.get("type") == "model_output":
            blocos += [b for b in passo.get("content") or [] if isinstance(b, dict)]
    return blocos


def _motivo_recusa(dados: dict, blocos: list[dict]) -> str | None:
    """Resposta 200 sem imagem: o que o Google disse no lugar dela."""
    erros = dados.get("errors")
    if isinstance(erros, list) and erros and isinstance(erros[0], dict) and erros[0].get("message"):
        return str(erros[0]["message"])[:200]
    if dados.get("status") in ("failed", "incomplete"):
        return f"interação {dados['status']}"
    textos = [str(b["text"]) for b in blocos if b.get("type") == "text" and b.get("text")]
    if textos:
        return textos[0][:200]
    return None


class Google:
    nome = "google"

    def __init__(self, config: dict, pedir=http.pedir, ler_chave=chaves.ler_chave):
        self.config = config
        self._pedir = pedir
        self._ler_chave = ler_chave

    def gerar(self, prompt: str, proporcao: str = "9:16") -> bytes:
        corpo = {
            "model": self.config["modelo"],
            "input": prompt,
            "response_format": {
                "type": "image",
                "mime_type": "image/jpeg",
                "aspect_ratio": PROPORCAO,
                "image_size": self.config["qualidade"],
            },
        }
        dados = _comum.chamar(
            self.nome, self._pedir, self._ler_chave, URL, "x-goog-api-key", "", corpo, extras={"Api-Revision": REVISAO_API}
        )
        blocos = _blocos(dados)
        for bloco in blocos:
            if bloco.get("type") == "image" and bloco.get("data"):
                return _comum.decodificar_imagem(self.nome, bloco["data"])
        motivo = _motivo_recusa(dados, blocos)
        if motivo is not None:
            raise ConteudoRecusado(f"google recusou o conteúdo: {motivo}")
        return _comum.decodificar_imagem(self.nome, None)
