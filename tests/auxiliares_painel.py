import json
import shutil
from pathlib import Path

from esteira.cortar import pasta_do_corte
from esteira.modelos import Corte
from esteira.receita import Musica, Receita, gravar_receita

PALAVRAS = [{"texto": f"p{i}", "inicio": i - 0.4, "fim": i + 0.4} for i in range(30)]
POST = Path(__file__).parent / "dados_post_corte1.md"


def criar_episodio(
    cortes: Path,
    nome: str,
    cortes_aprovados: list[Corte],
    montados: set[int],
    post: bool = True,
    credito: str = "",
    musica: Musica | None = None,
) -> Path:
    pasta = Path(cortes) / nome
    (pasta / "transcricao").mkdir(parents=True)
    (pasta / "transcricao" / "palavras.json").write_text(json.dumps(PALAVRAS), "utf-8")
    (pasta / "aprovados.json").write_text(
        json.dumps({"cortes": [c.__dict__ for c in cortes_aprovados]}), "utf-8"
    )
    for corte in cortes_aprovados:
        if corte.numero not in montados:
            continue
        destino = pasta_do_corte(pasta, corte)
        (destino / "trabalho").mkdir(parents=True)
        (destino / "corte.mp4").write_bytes(b"")
        if musica is None and credito:
            musica = Musica("m.mp3", credito=credito)
        gravar_receita(destino / "trabalho", Receita([(corte.inicio, corte.fim)], [], [], musica=musica))
        (destino / "trabalho" / "registro.json").write_text(
            json.dumps({"resultado": "ok", "alertas": []}), "utf-8"
        )
        if post:
            shutil.copy(POST, destino / "post.md")
    return pasta
