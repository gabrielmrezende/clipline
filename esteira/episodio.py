import json
import re
import unicodedata
from pathlib import Path

from esteira.caminhos import CORTES, garantir_escrita
from esteira.midia import ErroMidia, sondar


def slug(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", sem_acento.lower()).strip("-")


def criar_episodio(video: Path, quadro: str, numero: int, convidado: str, base: Path = CORTES) -> Path:
    midia = sondar(video)
    if midia.largura < midia.altura:
        raise ErroMidia(f"O episódio precisa ser horizontal: {video}")
    if not midia.tem_audio:
        raise ErroMidia(f"O episódio não tem áudio: {video}")

    pasta = garantir_escrita(Path(base) / f"{quadro} {numero:02d} - {convidado}", base_extra=base)
    arquivo = pasta / "episodio.json"
    origem = str(Path(video).resolve())
    if arquivo.exists():
        if json.loads(arquivo.read_text("utf-8"))["video"] != origem:
            raise ErroMidia(f"Esta pasta já pertence a outro vídeo: {pasta}")
        return pasta

    pasta.mkdir(parents=True, exist_ok=True)
    info = Path(video).stat()
    arquivo.write_text(
        json.dumps(
            {
                "video": origem,
                "quadro": quadro,
                "numero": numero,
                "convidado": convidado,
                "duracao": midia.duracao,
                "tamanho": info.st_size,
                "modificado": info.st_mtime,
            },
            ensure_ascii=False,
            indent=2,
        ),
        "utf-8",
    )
    return pasta
