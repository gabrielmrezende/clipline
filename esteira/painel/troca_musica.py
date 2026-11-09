import os
import time
from collections.abc import Callable
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass, field
from pathlib import Path

from esteira.caminhos import garantir_escrita
from esteira.cortar import TRABALHO, ler_aprovados, pasta_do_corte
from esteira.musica import MUSICAS, Faixa, registrar_uso
from esteira.publicar.post import ErroPost, trocar_credito
from esteira.receita import NOME_ARQUIVO, Musica, ler_receita, gravar_receita

VIDEO_ABERTO = "O vídeo do corte está aberto num player (talvez em outro aparelho). Feche o vídeo e tente de novo."
INTERVALO_VIDEO_ABERTO = 0.25
TENTATIVAS_VIDEO_ABERTO = 20  # 20 x 0,25 s = 5 s de espera


@dataclass
class Resultado:
    estado: str
    mensagem: str
    avisos: list[str] = field(default_factory=list)
    anterior: Musica | None = None


def trocar_musica(
    pasta_episodio: Path,
    numero: int,
    faixa: Faixa,
    volume_db: float,
    montar: Callable[[Path, int], str],
    base: Path | None = None,
    pasta_musicas: Path = MUSICAS,
    trava: AbstractContextManager | None = None,
    substituir: Callable[[Path, Path], None] = os.replace,
    dormir: Callable[[float], None] = time.sleep,
) -> Resultado:
    pasta_episodio = Path(pasta_episodio)
    corte = next((c for c in ler_aprovados(pasta_episodio) if c.numero == numero), None)
    if corte is None:
        return Resultado("erro", f"corte {numero} não encontrado", [], None)
    pasta_corte = pasta_do_corte(pasta_episodio, corte)
    trabalho = pasta_corte / TRABALHO
    montagem = trabalho / NOME_ARQUIVO
    garantir_escrita(montagem, base_extra=base)
    guardado = montagem.read_bytes()
    receita = ler_receita(trabalho)
    anterior = receita.musica
    nova = Musica(str(pasta_musicas / faixa.arquivo), volume_db, faixa.titulo, faixa.credito)
    receita.musica = nova

    video = pasta_corte / "corte.mp4"
    anterior_video = trabalho / "corte-anterior.mp4"
    registro = trabalho / "registro.json"
    registro_guardado = registro.read_bytes() if registro.exists() else None
    if video.exists():
        garantir_escrita(video, base_extra=base)
        garantir_escrita(anterior_video, base_extra=base)
        if not _substituir_com_espera(video, anterior_video, substituir, dormir):
            return Resultado("erro", VIDEO_ABERTO, [], anterior)
    resultado = "erro: a montagem não terminou"
    try:
        gravar_receita(trabalho, receita)
        retorno = montar(pasta_episodio, numero)
        resultado = retorno if isinstance(retorno, str) else f"erro: resultado inesperado ({retorno!r})"
    except Exception as erro:
        resultado = f"erro: {erro}"
    finally:
        if not resultado.startswith("ok"):
            _restaurar(montagem, guardado, video, anterior_video, registro, registro_guardado, substituir, dormir)
    if not resultado.startswith("ok"):
        return Resultado("erro", resultado, [], anterior)
    try:
        anterior_video.unlink(missing_ok=True)
    except OSError:
        pass

    avisos: list[str] = []
    post = pasta_corte / "post.md"
    if not post.exists():
        avisos.append("post.md não encontrado: crédito não atualizado")
    else:
        try:
            with trava if trava is not None else nullcontext():
                avisos += trocar_credito(post, anterior, nova, base=base)
        except Exception as erro:
            avisos.append(f"crédito não atualizado: {erro}")
    if anterior is None or anterior.arquivo != nova.arquivo:
        try:
            garantir_escrita(Path(pasta_musicas) / "uso.json", base_extra=base)
            registrar_uso(f"{pasta_episodio.name}/{pasta_corte.name}", faixa, pasta_musicas)
        except Exception as erro:
            avisos.append(f"uso da música não registrado: {erro}")
    return Resultado("pronto", resultado, avisos, anterior)


def _substituir_com_espera(origem: Path, destino: Path, substituir, dormir) -> bool:
    """os.replace que espera até 5 s se o Windows disser que o arquivo está aberto (WinError 32)."""
    for tentativa in range(TENTATIVAS_VIDEO_ABERTO + 1):
        try:
            substituir(origem, destino)
            return True
        except PermissionError:
            if tentativa == TENTATIVAS_VIDEO_ABERTO:
                return False
            dormir(INTERVALO_VIDEO_ABERTO)
    return False


def _restaurar(montagem, guardado, video, anterior_video, registro, registro_guardado, substituir, dormir) -> None:
    montagem.write_bytes(guardado)
    if anterior_video.exists() and not _substituir_com_espera(anterior_video, video, substituir, dormir):
        raise PermissionError(f"não consegui devolver o corte.mp4: {VIDEO_ABERTO}")
    if registro_guardado is not None:
        registro.write_bytes(registro_guardado)
