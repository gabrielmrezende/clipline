import io
from datetime import datetime

import pytest
from PIL import Image

from esteira.fluxo_imagens import chave_momento, ler_ia
from esteira.imagens_ia.config import padrao
from esteira.imagens_ia.gerar import ErroPrompt, gerar_cortes, gerar_momento, orcamento, pendentes
from esteira.imagens_ia.provedor import ConteudoRecusado, ErroImagem, SemChave
from esteira.pedidos import Momento, gravar_pedidos
from esteira.planos import Plano
from esteira.receita import Receita, gravar_receita

CHAVE = "0052-turistas"


def _png(tamanho=(1024, 1536), cor=(200, 30, 30)):
    buffer = io.BytesIO()
    Image.new("RGB", tamanho, cor).save(buffer, "PNG")
    return buffer.getvalue()


class Falso:
    nome = "openai"

    def __init__(self, conteudo=None, erros=None):
        self.conteudo = conteudo if conteudo is not None else _png()
        self.erros = list(erros or [])
        self.chamadas = []

    def gerar(self, prompt, proporcao="9:16"):
        self.chamadas.append(prompt)
        if self.erros:
            erro = self.erros.pop(0)
            if erro:
                raise erro
        return self.conteudo


def _ia(inicio=52.0, nome="Turistas", **extra):
    dados = {"prompt": "turistas numa praia", "aprovado": True, **extra}
    return Momento(inicio, inicio + 3, "fala", "ia", nome, **dados)


def _corte(tmp_path, momentos, nome="01-corte"):
    corte = tmp_path / nome
    (corte / "trabalho").mkdir(parents=True)
    gravar_pedidos(corte / "trabalho", momentos)
    return corte


def _gerar(corte, tmp_path, provedor=None, chave=CHAVE, pessoas=()):
    return gerar_momento(corte, chave, provedor or Falso(), padrao(), list(pessoas), base=tmp_path)


def test_chave_do_teste():
    assert chave_momento(_ia()) == CHAVE


def test_gera_arquivo_registra_e_guia(tmp_path):
    corte = _corte(tmp_path, [_ia()])
    provedor = Falso()
    nome = gerar_momento(
        corte, CHAVE, provedor, padrao(), [], base=tmp_path, agora=lambda: datetime(2026, 11, 9, 10, 0, 5))
    assert nome == "0052-turistas-ia-1.jpg"
    with Image.open(corte / "imagens-sugeridas" / nome) as imagem:
        assert imagem.size == (1080, 1920)
    item = ler_ia(corte / "trabalho")[0]
    assert item == {
        "arquivo": nome, "momento": CHAVE, "versao": 1, "provedor": "openai", "modelo": "gpt-image-2",
        "prompt": "turistas numa praia", "data": "2026-11-09T10:00:05",
    }
    assert nome in (corte / "imagens-sugeridas" / "guia.md").read_text("utf-8")
    assert provedor.chamadas == ["turistas numa praia"]


def test_segunda_vira_ia_2_e_quarta_trava(tmp_path):
    corte = _corte(tmp_path, [_ia()])
    assert _gerar(corte, tmp_path) == "0052-turistas-ia-1.jpg"
    assert _gerar(corte, tmp_path) == "0052-turistas-ia-2.jpg"
    assert _gerar(corte, tmp_path) == "0052-turistas-ia-3.jpg"
    provedor = Falso()
    with pytest.raises(ErroPrompt, match="^Este momento já tem 3 versões$"):
        _gerar(corte, tmp_path, provedor)
    assert provedor.chamadas == []


def test_nao_sobrescreve_arquivo_se_ia_json_se_perdeu(tmp_path):
    corte = _corte(tmp_path, [_ia()])
    _gerar(corte, tmp_path)
    (corte / "trabalho" / "ia.json").unlink()
    assert _gerar(corte, tmp_path) == "0052-turistas-ia-2.jpg"


def test_pessoa_sem_acento_e_minuscula(tmp_path):
    corte = _corte(tmp_path, [_ia(prompt="foto do felipe massa na pista")])
    provedor = Falso()
    with pytest.raises(ErroPrompt, match=r"^Cita pessoa real \(Felipe Massa\): não pode gerar$"):
        _gerar(corte, tmp_path, provedor, pessoas=["Felipe Massa"])
    assert provedor.chamadas == []


@pytest.mark.parametrize("extra,mensagem", [
    ({"aprovado": False}, "Prompt não aprovado"),
    ({"descartar": True}, "Momento descartado"),
    ({"prompt": ""}, "Momento sem prompt"),
])
def test_recusas(tmp_path, extra, mensagem):
    corte = _corte(tmp_path, [_ia(**extra)])
    provedor = Falso()
    with pytest.raises(ErroPrompt, match=f"^{mensagem}$"):
        _gerar(corte, tmp_path, provedor)
    assert provedor.chamadas == []
    assert not (corte / "trabalho" / "ia.json").exists()


def test_nao_e_ia_e_nao_encontrado(tmp_path):
    corte = _corte(tmp_path, [Momento(52.0, 55.0, "f", "foto", "Turistas", busca="x")])
    with pytest.raises(ErroPrompt, match="^Momento não é de IA$"):
        _gerar(corte, tmp_path)
    with pytest.raises(ErroPrompt, match="^Momento não encontrado$"):
        _gerar(corte, tmp_path, chave="9999-x")


def _perto(pixel, alvo, tolerancia=40):
    return all(abs(a - b) <= tolerancia for a, b in zip(pixel, alvo))


def test_imagem_horizontal_fica_na_faixa_central(tmp_path):
    azul, amarelo, verde = (0, 0, 250), (250, 250, 0), (0, 200, 0)
    horizontal = Image.new("RGB", (1536, 1024), verde)
    horizontal.paste(Image.new("RGB", (60, 1024), azul), (0, 0))
    horizontal.paste(Image.new("RGB", (60, 1024), amarelo), (1476, 0))
    buffer = io.BytesIO()
    horizontal.save(buffer, "PNG")
    corte = _corte(tmp_path, [_ia()])
    nome = _gerar(corte, tmp_path, Falso(buffer.getvalue()))
    with Image.open(corte / "imagens-sugeridas" / nome) as imagem:
        assert imagem.size == (1080, 1920)
        # a imagem inteira cabe na largura: as bordas continuam visíveis (um recorte as perderia)
        assert _perto(imagem.getpixel((2, 960)), azul)
        assert _perto(imagem.getpixel((1077, 960)), amarelo)
        assert _perto(imagem.getpixel((540, 960)), verde)
        # a faixa tem 720 px de altura (y 600 a 1320)
        assert _perto(imagem.getpixel((2, 620)), azul) and _perto(imagem.getpixel((2, 1300)), azul)
        # fora da faixa é o fundo desfocado, sem as bordas
        for y in (560, 1360, 20, 1900):
            assert not _perto(imagem.getpixel((2, y)), azul, 80)
            assert not _perto(imagem.getpixel((1077, y)), amarelo, 80)


def test_bytes_que_nao_sao_imagem(tmp_path):
    corte = _corte(tmp_path, [_ia()])
    with pytest.raises(ErroImagem, match="não é uma imagem"):
        _gerar(corte, tmp_path, Falso(b"isto nao e imagem"))
    assert not list((corte / "imagens-sugeridas").glob("*.jpg"))
    assert not (corte / "trabalho" / "ia.json").exists()


def test_pendentes_e_orcamento(tmp_path):
    corte = _corte(tmp_path, [
        _ia(52.0, "Turistas"), _ia(70.0, "Praia"), _ia(80.0, "Sem aprovar", aprovado=False),
        _ia(90.0, "Descartada", descartar=True), _ia(95.0, "Sem prompt", prompt=""),
    ])
    assert [m.nome for m in pendentes(corte)] == ["Turistas", "Praia"]
    _gerar(corte, tmp_path)
    assert [m.nome for m in pendentes(corte)] == ["Praia"]
    assert pendentes(tmp_path / "nao-existe") == []
    dados = orcamento([corte], padrao())
    assert dados == {"imagens": 1, "provedor": "openai", "modelo": "gpt-image-2", "custo_usd": 0.041}


def test_pedidos_ilegivel_nao_tem_pendentes(tmp_path):
    corte = _corte(tmp_path, [_ia()])
    (corte / "trabalho" / "pedidos.json").write_text("{quebrado", "utf-8")
    assert pendentes(corte) == []


def test_guia_usa_tempos_ajustados_da_receita(tmp_path):
    corte = _corte(tmp_path, [Momento(52.0, 52.5, "f", "ia", "Turistas", prompt="p", aprovado=True)])
    gravar_receita(corte / "trabalho", Receita([(0.0, 90.0)], [Plano(0.0, 90.0)], []))
    _gerar(corte, tmp_path)
    assert "0:52 a 0:54" in (corte / "imagens-sugeridas" / "guia.md").read_text("utf-8")


def test_sem_chave_nao_cobra(tmp_path):
    corte = _corte(tmp_path, [_ia(52.0, "Turistas"), _ia(70.0, "Praia")])
    provedor = Falso(erros=[SemChave("openai"), SemChave("openai")])
    arquivos, avisos = gerar_cortes([corte], provedor, padrao(), [], base=tmp_path)
    assert arquivos == []
    assert len(avisos) == 2
    assert all("Rode python -m esteira imagens conectar openai" in a for a in avisos)
    assert avisos[0].startswith("01-corte 0052-turistas: ")
    assert not (corte / "trabalho" / "ia.json").exists()
    assert not (corte / "imagens-sugeridas").exists() or not list((corte / "imagens-sugeridas").glob("*"))


def test_gerar_cortes_segue_depois_de_recusa_e_informa_progresso(tmp_path):
    corte = _corte(tmp_path, [_ia(52.0, "Turistas"), _ia(70.0, "Praia")])
    provedor = Falso(erros=[ConteudoRecusado("política de segurança"), None])
    mensagens = []
    arquivos, avisos = gerar_cortes([corte], provedor, padrao(), [], base=tmp_path, progresso=mensagens.append)
    assert mensagens == ["Gerando 1 de 2…", "Gerando 2 de 2…"]
    assert arquivos == ["0110-praia-ia-1.jpg"]
    assert avisos == ["01-corte 0052-turistas: política de segurança"]


def test_gerar_cortes_conta_todos_os_cortes(tmp_path):
    a = _corte(tmp_path, [_ia()], "01-a")
    b = _corte(tmp_path, [_ia(70.0, "Praia")], "02-b")
    mensagens = []
    arquivos, avisos = gerar_cortes([a, b], Falso(), padrao(), [], base=tmp_path, progresso=mensagens.append)
    assert mensagens == ["Gerando 1 de 2…", "Gerando 2 de 2…"]
    assert len(arquivos) == 2 and avisos == []
