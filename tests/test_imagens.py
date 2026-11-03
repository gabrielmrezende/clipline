from esteira.imagens import ler_imagens
from esteira.receita import Imagem

MD = """## 1. 00:00:18 a 00:00:21 — Gripen
Tipo: foto livre
Autor e licença: FAB, CC BY 2.0

## 2. 00:00:40 a 00:00:43 — Sem arquivo
Autor e licença: ninguém
"""


def _pasta(tmp_path, md, *arquivos):
    (tmp_path / "imagens.md").write_text(md, "utf-8")
    (tmp_path / "imagens").mkdir()
    for nome in arquivos:
        (tmp_path / "imagens" / nome).write_bytes(b"x")


def test_le_imagens_com_arquivo(tmp_path):
    _pasta(tmp_path, MD, "01-gripen.jpg")
    assert ler_imagens(tmp_path) == [Imagem(18.0, 21.0, "imagens/01-gripen.jpg", "FAB, CC BY 2.0")]


def test_sem_imagens_md(tmp_path):
    assert ler_imagens(tmp_path) == []


def test_sem_pasta_imagens(tmp_path):
    (tmp_path / "imagens.md").write_text(MD, "utf-8")
    assert ler_imagens(tmp_path) == []


def test_tempo_com_milissegundos(tmp_path):
    _pasta(tmp_path, "## 1. 00:00:18,500 a 00:00:21,000 — A\n", "01-a.png")
    imagem = ler_imagens(tmp_path)[0]
    assert (imagem.inicio, imagem.fim, imagem.licenca) == (18.5, 21.0, "")


def test_travessoes_aceitos(tmp_path):
    md = "## 1. 00:00:01 a 00:00:03 – A\n\n## 2. 00:00:05 a 00:00:07 - B\n"
    _pasta(tmp_path, md, "01-a.jpg", "02-b.jpg")
    assert [i.arquivo for i in ler_imagens(tmp_path)] == ["imagens/01-a.jpg", "imagens/02-b.jpg"]


def test_extensao_sem_diferenciar_maiusculas_e_primeiro_alfabetico(tmp_path):
    _pasta(tmp_path, "## 1. 00:00:01 a 00:00:03 — A\n", "01-z.png", "01-b.JPG", "01-a.gif")
    assert ler_imagens(tmp_path)[0].arquivo == "imagens/01-b.JPG"


def test_ordem_do_numero_da_sugestao(tmp_path):
    md = "## 2. 00:00:10 a 00:00:12 — B\n\n## 1. 00:00:01 a 00:00:03 — A\n"
    _pasta(tmp_path, md, "01-a.jpg", "02-b.webp")
    assert [i.inicio for i in ler_imagens(tmp_path)] == [1.0, 10.0]


def test_numero_nao_casa_prefixo_parcial(tmp_path):
    _pasta(tmp_path, "## 1. 00:00:01 a 00:00:03 — A\n", "10-a.jpg", "1-a.jpg")
    assert ler_imagens(tmp_path) == []


def test_secoes_sem_arquivo(tmp_path):
    from esteira.imagens import secoes_sem_arquivo
    _pasta(tmp_path, MD, "01-gripen.jpg")
    assert secoes_sem_arquivo(tmp_path) == [2]


def test_secoes_sem_arquivo_sem_imagens_md(tmp_path):
    from esteira.imagens import secoes_sem_arquivo
    assert secoes_sem_arquivo(tmp_path) == []
