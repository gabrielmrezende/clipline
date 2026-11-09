import base64
import json
import os
import sys
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
MARCADOR = "troca-em-andamento.json"
CORTE_ANTERIOR = "corte-anterior.mp4"
LIMITE_MENSAGEM = 300


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
    try:
        _desfazer_troca_interrompida(pasta_corte, base, substituir, dormir)
    except Exception as erro:
        return Resultado("erro", f"não consegui desfazer a troca interrompida antes: {erro}", [], None)
    trabalho = pasta_corte / TRABALHO
    montagem = trabalho / NOME_ARQUIVO
    garantir_escrita(montagem, base_extra=base)
    guardado = montagem.read_bytes()
    receita = ler_receita(trabalho)
    anterior = receita.musica
    nova = Musica(str(pasta_musicas / faixa.arquivo), volume_db, faixa.titulo, faixa.credito)
    receita.musica = nova

    video = pasta_corte / "corte.mp4"
    anterior_video = trabalho / CORTE_ANTERIOR
    registro = trabalho / "registro.json"
    registro_guardado = registro.read_bytes() if registro.exists() else None
    havia_video = video.exists()
    for caminho in (video, anterior_video, registro):
        garantir_escrita(caminho, base_extra=base)
    marcador = _gravar_marcador(trabalho, guardado, registro_guardado, havia_video, base)
    if havia_video and not _substituir_com_espera(video, anterior_video, substituir, dormir):
        marcador.unlink(missing_ok=True)
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
            _restaurar(
                montagem, guardado, video, anterior_video, registro, registro_guardado, havia_video, substituir, dormir
            )
            marcador.unlink(missing_ok=True)
    if not resultado.startswith("ok"):
        return Resultado("erro", resumir_erro(resultado), [], anterior)

    avisos: list[str] = _alertas_da_montagem(resultado)
    post = pasta_corte / "post.md"
    if not post.exists():
        avisos.append("post.md não encontrado: crédito não atualizado")
    else:
        try:
            with trava if trava is not None else nullcontext():
                avisos += trocar_credito(post, anterior, nova, base=base)
        except Exception as erro:
            avisos.append(f"crédito não atualizado: {erro}")
    marcador.unlink(missing_ok=True)  # corte.mp4, montagem.json e post.md já falam da música nova
    try:
        anterior_video.unlink(missing_ok=True)
    except OSError:
        pass
    if anterior is None or anterior.arquivo != nova.arquivo:
        try:
            garantir_escrita(Path(pasta_musicas) / "uso.json", base_extra=base)
            registrar_uso(f"{pasta_episodio.name}/{pasta_corte.name}", faixa, pasta_musicas)
        except Exception as erro:
            avisos.append(f"uso da música não registrado: {erro}")
    return Resultado("pronto", resultado, avisos, anterior)


def resumir_erro(texto: str) -> str:
    """Mensagem de erro para a tela: sem o prefixo "erro:" (a tela já diz "Erro:") e com até 300 caracteres."""
    texto = str(texto).strip()
    if texto.lower().startswith("erro:"):
        texto = texto[len("erro:"):].strip()
    texto = texto or "erro desconhecido"
    return texto if len(texto) <= LIMITE_MENSAGEM else texto[: LIMITE_MENSAGEM - 1] + "…"


def _alertas_da_montagem(resultado: str) -> list[str]:
    prefixo = "ok com alertas:"
    if not resultado.startswith(prefixo):
        return []
    return [a.strip() for a in resultado[len(prefixo):].split("; ") if a.strip()]  # o montar junta com "; "


def recuperar_trocas_interrompidas(
    cortes: Path,
    substituir: Callable[[Path, Path], None] = os.replace,
    dormir: Callable[[float], None] = time.sleep,
) -> list[str]:
    """Desfaz as trocas de música que o painel deixou pela metade (queda, Ctrl+C). Devolve "<episódio>/<corte>"."""
    recuperados: list[str] = []
    for marcador in sorted(Path(cortes).glob(f"*/*/{TRABALHO}/{MARCADOR}")):
        pasta_corte = marcador.parent.parent
        nome = f"{pasta_corte.parent.name}/{pasta_corte.name}"
        try:
            if _desfazer_troca_interrompida(pasta_corte, cortes, substituir, dormir):
                recuperados.append(nome)
        except Exception as erro:
            print(f"Não consegui desfazer a troca de música interrompida em {nome}: {erro}", file=sys.stderr)
    return recuperados


def _gravar_marcador(trabalho: Path, montagem: bytes, registro: bytes | None, havia_video: bool, base) -> Path:
    marcador = garantir_escrita(trabalho / MARCADOR, base_extra=base)
    dados = {
        "montagem": base64.b64encode(montagem).decode("ascii"),
        "registro": base64.b64encode(registro).decode("ascii") if registro is not None else None,
        "havia_video": havia_video,
    }
    temporario = marcador.with_name(MARCADOR + ".tmp")
    temporario.write_text(json.dumps(dados), "utf-8")
    os.replace(temporario, marcador)
    return marcador


def _desfazer_troca_interrompida(pasta_corte: Path, base, substituir, dormir) -> bool:
    trabalho = Path(pasta_corte) / TRABALHO
    marcador = trabalho / MARCADOR
    if not marcador.exists():
        return False
    dados = json.loads(marcador.read_text("utf-8"))
    montagem = base64.b64decode(dados["montagem"])
    registro = base64.b64decode(dados["registro"]) if dados.get("registro") is not None else None
    caminhos = (trabalho / NOME_ARQUIVO, Path(pasta_corte) / "corte.mp4", trabalho / CORTE_ANTERIOR, trabalho / "registro.json")
    for caminho in (*caminhos, marcador):
        garantir_escrita(caminho, base_extra=base)
    _restaurar(caminhos[0], montagem, caminhos[1], caminhos[2], caminhos[3], registro, bool(dados["havia_video"]), substituir, dormir)
    marcador.unlink()
    return True


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


def _restaurar(
    montagem, guardado, video, anterior_video, registro, registro_guardado, havia_video, substituir, dormir
) -> None:
    """Volta montagem.json, registro.json e (se havia) o corte.mp4 de antes, por cima de um novo."""
    montagem.write_bytes(guardado)
    if havia_video and anterior_video.exists():
        if not _substituir_com_espera(anterior_video, video, substituir, dormir):
            raise PermissionError(f"não consegui devolver o corte.mp4: {VIDEO_ABERTO}")
    if registro_guardado is not None:
        registro.write_bytes(registro_guardado)
