import json

import pytest
from PIL import Image

from esteira.fluxo_imagens import (
    ErroBusca, buscar_episodio, chave_momento, escrever_guia, ler_ia, registrar_ia, resumir_episodio, sugerir_episodio)
from esteira.pedidos import Momento, gravar_pedidos, ler_pedidos
from esteira.planos import Plano
from esteira.receita import Receita, gravar_receita

CORTE = {"numero": 1, "titulo": "Bom corte", "inicio": 0.0, "fim": 60.0, "clima": "leve"}


def _pagina(i, ordem):
    return {
        "title": f"File:A{i}.jpg", "index": ordem,
        "imageinfo": [{
            "thumburl": f"https://u/640px-A{i}.jpg", "mime": "image/jpeg", "width": 2000, "height": 1000,
            "extmetadata": {"LicenseShortName": {"value": "CC BY-SA 4.0"}, "Artist": {"value": "<a href='x'>Fulano</a>"}},
        }],
    }


def falso(params):
    if "gsrsearch" in params:
        return {"query": {"pages": [_pagina(1, 1), _pagina(2, 2)]}}
    titulo = params["titles"].removeprefix("File:")
    return {"query": {"pages": [{"title": params["titles"], "imageinfo": [{"thumburl": f"https://u/1920px-{titulo}"}]}]}}


def sem_thumb(params):
    if "gsrsearch" in params:
        return falso(params)
    return {"query": {"pages": [{"title": params["titles"], "imageinfo": [{}]}]}}


def quebra(params):
    raise OSError("sem rede")


def baixar(url, destino):
    Image.new("RGB", (64, 40), (200, 50, 50)).save(destino, "JPEG")


def _episodio(tmp_path, momentos):
    ep = tmp_path / "Quadro 03 - Fulano"
    ep.mkdir()
    (ep / "episodio.json").write_text(json.dumps({"video": "v.mp4", "quadro": "Entre Assuntos", "numero": 3}), "utf-8")
    (ep / "aprovados.json").write_text(json.dumps({"cortes": [CORTE]}), "utf-8")
    corte = ep / "01-bom-corte"
    (corte / "trabalho").mkdir(parents=True)
    gravar_receita(corte / "trabalho", Receita([(0.0, 60.0)], [Plano(0.0, 60.0)], []))
    gravar_pedidos(corte / "trabalho", momentos)
    return ep, corte


def _foto(inicio=10.0, fim=11.0, **extra):
    return Momento(inicio, fim, "fala um", "foto", "Gripen", busca="gripen", **extra)


def test_buscar_grava_candidatas_e_folha(tmp_path):
    ep, corte = _episodio(tmp_path, [_foto(escolhas=[2], url=['u'], bytes=[1], resumidas=[2])])
    assert buscar_episodio(ep, None, [], falso, baixar) == {1: "ok"}
    momento = ler_pedidos(corte / "trabalho")[0]
    assert len(momento.candidatas) == 2 and momento.escolhas == momento.url == momento.bytes == momento.resumidas == []
    assert (corte / "trabalho" / "candidatas" / "01-1.jpg").exists()


def test_buscar_grava_candidatas_em_trabalho(tmp_path):
    ep, corte = _episodio(tmp_path, [_foto(escolhas=[2], url=['u'], bytes=[1], resumidas=[2])])
    assert buscar_episodio(ep, None, [], falso, baixar) == {1: "ok"}
    assert (corte / "trabalho" / "candidatas" / "01-1.jpg").exists()
    assert (corte / "trabalho" / "pedidos.json").exists()
    assert not (corte / "candidatas").exists() and not (corte / "pedidos.json").exists()


def test_buscar_api_fora_nao_grava(tmp_path):
    ep, corte = _episodio(tmp_path, [_foto()])
    with pytest.raises(ErroBusca):
        buscar_episodio(ep, None, [], quebra, baixar)
    assert ler_pedidos(corte / "trabalho")[0].candidatas == [] and not (corte / "trabalho" / "candidatas").exists()


def test_buscar_recusa_prompt_com_pessoa(tmp_path):
    ep, corte = _episodio(tmp_path, [_foto(), Momento(20.0, 23.0, "f", "ia", "X", prompt="retrato de Ayrton Senna")])
    assert buscar_episodio(ep, None, ["Ayrton Senna"], falso, baixar)[1].startswith("erro: momento 2: prompt cita pessoa real")
    assert ler_pedidos(corte / "trabalho")[0].candidatas == []


def test_buscar_sem_candidata_alerta(tmp_path):
    ep, _ = _episodio(tmp_path, [_foto()])
    assert buscar_episodio(ep, None, [], lambda p: {}, baixar) == {1: "ok com alertas: momento 1 sem candidata"}


def test_buscar_sem_montagem_e_sem_pedidos(tmp_path):
    ep, corte = _episodio(tmp_path, [_foto()])
    (corte / "trabalho" / "montagem.json").unlink()
    assert buscar_episodio(ep, None, [], falso, baixar) == {1: "erro: montagem.json não encontrado, rode preparar"}
    (corte / "trabalho" / "pedidos.json").unlink()
    assert buscar_episodio(ep, None, [], falso, baixar) == {}


# --- resumo e sugerir ---

AZUL, VERDE = (20, 40, 220), (20, 200, 40)


def _candidata(i, autor):
    return {"titulo": f"File:A{i}.jpg", "pagina": f"https://c/A{i}", "miniatura": "m",
            "largura": 2000, "altura": 1000, "autor": autor, "licenca": "CC BY-SA 4.0"}


def _sugeridos(tmp_path):
    ep, corte = _episodio(tmp_path, [
        Momento(12.4, 15.0, "quando a corrida foi para Abu Dhabi", "foto", "Yas Marina", busca="yas marina",
                candidatas=[_candidata(1, "Fulano"), _candidata(2, "Beltrana")], escolhas=[2, 1]),
        Momento(30.0, 33.0, "fala da notícia", "noticia", "Manchete", titulo="Titulo", veiculo="Folha", data="2026-01-02"),
        Momento(61.0, 64.0, "chovia", "ia", "Chuva na pista", prompt="Chuva forte numa pista vazia"),
    ])
    gravar_receita(corte / "trabalho", Receita([(0.0, 90.0)], [Plano(0.0, 90.0)], []))
    return ep, corte


def baixar_cor(url, destino):
    Image.new("RGB", (1600, 900), VERDE if "A2" in url else AZUL).save(destino, "JPEG")


def baixar_html(url, destino):
    destino.write_text("<html>", "utf-8")


def _proximo(cor, esperada):
    return all(abs(a - b) < 30 for a, b in zip(cor, esperada))


def test_resumo_nao_baixa(tmp_path):
    ep, corte = _sugeridos(tmp_path)
    consultas, medidas = [], []

    def consultar(params):
        consultas.append(params)
        return falso(params)

    tamanhos = {"https://u/1920px-A1.jpg": 1000, "https://u/1920px-A2.jpg": 2048}

    def medir(url):
        medidas.append(url)
        return tamanhos[url]

    fotos, total, resultados = resumir_episodio(ep, None, consultar, medir)
    assert (fotos, total, resultados) == (2, 3048, {1: "ok"})
    assert [c["titles"] for c in consultas] == ["File:A2.jpg", "File:A1.jpg"]  # só o link final
    assert medidas == ["https://u/1920px-A2.jpg", "https://u/1920px-A1.jpg"]  # só o tamanho (HEAD)
    momento = ler_pedidos(corte / "trabalho")[0]
    assert momento.url == ["https://u/1920px-A2.jpg", "https://u/1920px-A1.jpg"] and momento.bytes == [2048, 1000]
    assert momento.resumidas == [2, 1]
    assert not (corte / "imagens-sugeridas").exists()


def test_resumo_escolhas_invalidas_isola_corte(tmp_path):
    ep, corte = _sugeridos(tmp_path)
    momentos = ler_pedidos(corte / "trabalho")
    momentos[0].escolhas = [3]
    gravar_pedidos(corte / "trabalho", momentos)
    assert resumir_episodio(ep, None, falso, lambda u: 1) == (0, 0, {1: "erro: momento 1: escolhas inválidas"})


def test_resumo_wikimedia_fora(tmp_path):
    ep, _ = _sugeridos(tmp_path)
    fotos, _, resultados = resumir_episodio(ep, None, quebra, lambda u: 1)
    assert fotos == 0 and resultados[1].startswith("erro: Wikimedia indisponível")


def test_sugerir_exige_resumo(tmp_path):
    ep, corte = _sugeridos(tmp_path)
    assert sugerir_episodio(ep, None, [], falso, baixar_cor) == {1: "erro: rode imagens resumo"}
    assert not (corte / "imagens-sugeridas").exists()


def test_sugerir_gera_arquivos_e_guia(tmp_path):
    ep, corte = _sugeridos(tmp_path)
    resumir_episodio(ep, None, falso, lambda u: 1)
    assert sugerir_episodio(ep, None, [], falso, baixar_cor) == {1: "ok"}
    pasta = corte / "imagens-sugeridas"
    assert sorted(p.name for p in pasta.iterdir()) == [
        "0012-yas-marina-1.jpg", "0012-yas-marina-2.jpg", "0030-manchete.png", "guia.md"]
    with Image.open(pasta / "0012-yas-marina-1.jpg") as primeira:
        assert primeira.size == (1080, 1920) and _proximo(primeira.getpixel((540, 960)), VERDE)
    with Image.open(pasta / "0012-yas-marina-2.jpg") as segunda:
        assert _proximo(segunda.getpixel((540, 960)), AZUL)
    with Image.open(pasta / "0030-manchete.png") as cartao:
        assert cartao.size == (1080, 1920)
    guia = (pasta / "guia.md").read_text("utf-8")
    assert "2 a 5 s" in guia and "corte seco" in guia and "8%" in guia and "legenda" in guia
    assert "Se usar imagem de IA, avise na publicação" in guia
    assert "## 0:12 a 0:15 · Yas Marina (foto)" in guia
    assert 'Fala: "quando a corrida foi para Abu Dhabi"' in guia
    assert "Opções: 0012-yas-marina-1.jpg, 0012-yas-marina-2.jpg" in guia
    assert "1. Beltrana, CC BY-SA 4.0, https://c/A2\n2. Fulano, CC BY-SA 4.0, https://c/A1" in guia
    assert "## 0:30 a 0:33 · Manchete (notícia)" in guia and "Opções: 0030-manchete.png" in guia
    assert "## 1:01 a 1:04 · Chuva na pista (IA)" in guia
    assert 'Prompt (9:16): "Chuva forte numa pista vazia"' in guia
    assert guia.index("0:12 a") < guia.index("0:30 a") < guia.index("1:01 a") and "\r" not in guia
    assert json.loads((corte / "trabalho" / "sugeridas.json").read_text("utf-8")) == [
        "0012-yas-marina-1.jpg", "0012-yas-marina-2.jpg", "0030-manchete.png"]
    assert not (corte / "video-final").exists()


def test_sugerir_falha_isolada(tmp_path):
    ep, corte = _sugeridos(tmp_path)
    resumir_episodio(ep, None, falso, lambda u: 1)

    def falha_a2(url, destino):
        if "A2" in url:
            raise OSError("caiu")
        baixar_cor(url, destino)

    resultado = sugerir_episodio(ep, None, [], falso, falha_a2)[1]
    assert resultado.startswith("ok com alertas") and "download falhou" in resultado
    pasta = corte / "imagens-sugeridas"
    assert not (pasta / "0012-yas-marina-1.jpg").exists()
    assert (pasta / "0012-yas-marina-2.jpg").exists() and (pasta / "0030-manchete.png").exists()
    guia = (pasta / "guia.md").read_text("utf-8")
    assert "Sem imagem: opção 1: download falhou" in guia and "Opções: 0012-yas-marina-2.jpg" in guia


def test_sugerir_tudo_falha_vira_sem_imagem(tmp_path):
    ep, corte = _sugeridos(tmp_path)
    resumir_episodio(ep, None, falso, lambda u: 1)
    sugerir_episodio(ep, None, [], falso, baixar_html)
    guia = (corte / "imagens-sugeridas" / "guia.md").read_text("utf-8")
    assert "Sem imagem: download falhou" in guia
    assert not list((corte / "imagens-sugeridas").glob("*.jpg"))


def test_sugerir_nao_apaga_arquivo_do_dono(tmp_path):
    ep, corte = _sugeridos(tmp_path)
    pasta = corte / "imagens-sugeridas"
    pasta.mkdir()
    Image.new("RGB", (10, 10)).save(pasta / "minha.png")
    resumir_episodio(ep, None, falso, lambda u: 1)
    sugerir_episodio(ep, None, [], falso, baixar_cor)
    momentos = ler_pedidos(corte / "trabalho")
    momentos[0].escolhas, momentos[0].url, momentos[0].bytes = [1], [momentos[0].url[1]], [1]
    momentos[0].resumidas = [1]
    momentos[1].inicio, momentos[1].fim = 40.0, 43.0
    gravar_pedidos(corte / "trabalho", momentos)
    assert sugerir_episodio(ep, None, [], falso, baixar_cor) == {1: "ok"}
    assert sorted(p.name for p in pasta.iterdir()) == ["0012-yas-marina-1.jpg", "0040-manchete.png", "guia.md", "minha.png"]


def test_sugerir_nao_sobrescreve_arquivo_do_dono_com_mesmo_nome(tmp_path):
    ep, corte = _sugeridos(tmp_path)
    pasta = corte / "imagens-sugeridas"
    pasta.mkdir()
    (pasta / "0030-manchete.png").write_bytes(b"do dono")
    resumir_episodio(ep, None, falso, lambda u: 1)
    resultado = sugerir_episodio(ep, None, [], falso, baixar_cor)[1]
    assert "0030-manchete.png" in resultado and (pasta / "0030-manchete.png").read_bytes() == b"do dono"
    assert "0030-manchete.png" not in json.loads((corte / "trabalho" / "sugeridas.json").read_text("utf-8"))
    guia = (pasta / "guia.md").read_text("utf-8")
    assert "Opções: 0030-manchete.png" not in guia
    assert "Sem imagem: arquivo do dono mantido (0030-manchete.png)" in guia


def test_sugerir_foto_do_dono_sem_credito(tmp_path):
    ep, corte = _sugeridos(tmp_path)
    pasta = corte / "imagens-sugeridas"
    pasta.mkdir()
    (pasta / "0012-yas-marina-1.jpg").write_bytes(b"do dono")
    resumir_episodio(ep, None, falso, lambda u: 1)
    sugerir_episodio(ep, None, [], falso, baixar_cor)
    guia = (pasta / "guia.md").read_text("utf-8")
    assert "Opções: 0012-yas-marina-2.jpg\n" in guia
    assert "Sem imagem: opção 1: arquivo do dono mantido (0012-yas-marina-1.jpg)" in guia
    assert "Beltrana" not in guia and "2. Fulano, CC BY-SA 4.0, https://c/A1" in guia


def test_sugerir_recusa_escolhas_trocadas_depois_do_resumo(tmp_path):
    ep, corte = _sugeridos(tmp_path)
    momentos = ler_pedidos(corte / "trabalho")
    momentos[0].candidatas.append(_candidata(3, "Sicrano"))
    gravar_pedidos(corte / "trabalho", momentos)
    resumir_episodio(ep, None, falso, lambda u: 1)
    momentos = ler_pedidos(corte / "trabalho")
    momentos[0].escolhas = [3, 1]
    gravar_pedidos(corte / "trabalho", momentos)
    assert sugerir_episodio(ep, None, [], falso, baixar_cor) == {1: "erro: rode imagens resumo"}
    assert not (corte / "imagens-sugeridas").exists()


def test_sugerir_nao_herda_motivo_antigo(tmp_path):
    ep, corte = _sugeridos(tmp_path)
    momentos = ler_pedidos(corte / "trabalho")
    momentos[1].motivo = "cartão falhou"
    gravar_pedidos(corte / "trabalho", momentos)
    resumir_episodio(ep, None, falso, lambda u: 1)
    assert sugerir_episodio(ep, None, [], falso, baixar_cor) == {1: "ok"}
    assert "Sem imagem" not in (corte / "imagens-sugeridas" / "guia.md").read_text("utf-8")


def test_sugerir_lista_em_dia_se_interromper(tmp_path, monkeypatch):
    ep, corte = _sugeridos(tmp_path)
    resumir_episodio(ep, None, falso, lambda u: 1)

    def interrompe(*a):
        raise KeyboardInterrupt

    monkeypatch.setattr("esteira.fluxo_imagens.gerar_cartao", interrompe)
    with pytest.raises(KeyboardInterrupt):
        sugerir_episodio(ep, None, [], falso, baixar_cor)
    assert json.loads((corte / "trabalho" / "sugeridas.json").read_text("utf-8")) == [
        "0012-yas-marina-1.jpg", "0012-yas-marina-2.jpg"]


def test_sugerir_recusa_prompt_com_pessoa(tmp_path):
    ep, corte = _sugeridos(tmp_path)
    resumir_episodio(ep, None, falso, lambda u: 1)
    assert sugerir_episodio(ep, None, ["Chuva"], falso, baixar_cor)[1].startswith("erro: momento 3: prompt cita")
    assert not (corte / "imagens-sugeridas").exists()


# --- imagens de IA no ia.json e no guia ---

def _item_ia(versao, momento="0061-chuva-na-pista", provedor="openai", criado="2026-11-09T10:30:00"):
    return {"momento": momento, "arquivo": f"{momento.split('-', 1)[0]}-{momento.split('-', 1)[1]}-ia-{versao}.jpg",
            "versao": versao, "provedor": provedor, "criado": criado}


def _com_ia(tmp_path, nomes_presentes):
    ep, corte = _sugeridos(tmp_path)
    momentos = ler_pedidos(corte / "trabalho")
    chave = chave_momento(momentos[2])
    trabalho = corte / "trabalho"
    pasta = corte / "imagens-sugeridas"
    pasta.mkdir()
    for versao in (1, 2):
        item = _item_ia(versao, chave)
        registrar_ia(trabalho, item, tmp_path)
        if versao in nomes_presentes:
            Image.new("RGB", (10, 10)).save(pasta / item["arquivo"])
    return ep, corte, chave


def test_chave_momento_e_ia_registrada(tmp_path):
    m = Momento(52.0, 55.0, "f", "ia", "Turistas", prompt="p")
    assert chave_momento(m) == "0052-turistas"
    registrar_ia(tmp_path, {"momento": "0052-turistas", "arquivo": "0052-turistas-ia-1.jpg"}, tmp_path)
    registrar_ia(tmp_path, {"momento": "0052-turistas", "arquivo": "0052-turistas-ia-2.jpg"}, tmp_path)
    assert [i["arquivo"] for i in ler_ia(tmp_path)] == ["0052-turistas-ia-1.jpg", "0052-turistas-ia-2.jpg"]
    assert not list(tmp_path.glob("*.tmp"))


def test_ler_ia_ilegivel(tmp_path):
    assert ler_ia(tmp_path) == []
    (tmp_path / "ia.json").write_text("{quebrado", "utf-8")
    assert ler_ia(tmp_path) == []
    (tmp_path / "ia.json").write_text('{"a": 1}', "utf-8")
    assert ler_ia(tmp_path) == []
    (tmp_path / "ia.json").write_text('[1, {"momento": "x"}]', "utf-8")
    assert ler_ia(tmp_path) == [{"momento": "x"}]


def test_guia_lista_versoes_de_ia(tmp_path):
    ep, corte = _episodio(tmp_path, [Momento(52.0, 55.0, "turistas", "ia", "Turistas", prompt="Turistas na praia")])
    chave = "0052-turistas"
    pasta = corte / "imagens-sugeridas"
    pasta.mkdir()
    for v in (1, 2):
        registrar_ia(corte / "trabalho", {"momento": chave, "arquivo": f"{chave}-ia-{v}.jpg", "versao": v,
                                          "provedor": "openai", "criado": f"2026-11-0{v + 7}T10:00:00"}, tmp_path)
        Image.new("RGB", (10, 10)).save(pasta / f"{chave}-ia-{v}.jpg")
    escrever_guia(corte, ler_pedidos(corte / "trabalho"))
    guia = (pasta / "guia.md").read_text("utf-8")
    assert "Imagem de IA: 0052-turistas-ia-1.jpg, 0052-turistas-ia-2.jpg (openai, 2026-11-09)" in guia
    assert 'Prompt (9:16): "Turistas na praia"' in guia


def test_guia_ignora_ia_sem_arquivo(tmp_path):
    ep, corte, chave = _com_ia(tmp_path, nomes_presentes={1})
    escrever_guia(corte, ler_pedidos(corte / "trabalho"))
    guia = (corte / "imagens-sugeridas" / "guia.md").read_text("utf-8")
    assert f"Imagem de IA: {chave}-ia-1.jpg (openai, 2026-11-09)" in guia
    assert "-ia-2.jpg" not in guia


def test_sugerir_nao_apaga_ia(tmp_path):
    ep, corte, chave = _com_ia(tmp_path, nomes_presentes={1})
    resumir_episodio(ep, None, falso, lambda u: 1)
    assert sugerir_episodio(ep, None, [], falso, baixar_cor) == {1: "ok"}
    pasta = corte / "imagens-sugeridas"
    assert (pasta / f"{chave}-ia-1.jpg").exists()
    assert f"Imagem de IA: {chave}-ia-1.jpg" in (pasta / "guia.md").read_text("utf-8")
