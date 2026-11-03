import json

import pytest
from PIL import Image

from esteira.fluxo_imagens import ErroBusca, buscar_episodio, listar_episodio, nome_arquivo
from esteira.imagens import ler_imagens
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
    corte.mkdir()
    gravar_receita(corte, Receita([(0.0, 60.0)], [Plano(0.0, 60.0)], []))
    gravar_pedidos(corte, momentos)
    return ep, corte


def _foto(inicio=10.0, fim=11.0, **extra):
    return Momento(inicio, fim, "fala um", "foto", "Gripen", busca="gripen", **extra)


def _completo(tmp_path):
    return _episodio(tmp_path, [
        _foto(escolha=1, candidatas=[{"titulo": "File:A1.jpg", "pagina": "https://c/A1", "miniatura": "m",
                                      "largura": 2000, "altura": 1000, "autor": "Fulano", "licenca": "CC BY-SA 4.0"}]),
        Momento(20.0, 23.0, "fala dois", "ia", "Uno com escada", prompt="Um Uno com escada no teto"),
        Momento(30.0, 33.0, "fala três", "noticia", "Manchete", titulo="Titulo", veiculo="Folha", data="2026-01-02"),
    ])


def test_buscar_grava_candidatas_e_folha(tmp_path):
    ep, corte = _episodio(tmp_path, [_foto(escolha=2)])
    assert buscar_episodio(ep, None, [], falso, baixar) == {1: "ok"}
    momento = ler_pedidos(corte)[0]
    assert len(momento.candidatas) == 2 and momento.escolha is None
    assert (corte / "candidatas" / "01-1.jpg").exists()


def test_buscar_api_fora_nao_grava(tmp_path):
    ep, corte = _episodio(tmp_path, [_foto()])
    with pytest.raises(ErroBusca):
        buscar_episodio(ep, None, [], quebra, baixar)
    assert ler_pedidos(corte)[0].candidatas == [] and not (corte / "candidatas").exists()


def test_buscar_recusa_prompt_com_pessoa(tmp_path):
    ep, corte = _episodio(tmp_path, [_foto(), Momento(20.0, 23.0, "f", "ia", "X", prompt="retrato de Ayrton Senna")])
    assert buscar_episodio(ep, None, ["Ayrton Senna"], falso, baixar)[1].startswith("erro: momento 2: prompt cita pessoa real")
    assert ler_pedidos(corte)[0].candidatas == []


def test_buscar_sem_candidata_alerta(tmp_path):
    ep, _ = _episodio(tmp_path, [_foto()])
    assert buscar_episodio(ep, None, [], lambda p: {}, baixar) == {1: "ok com alertas: momento 1 sem candidata"}


def test_buscar_sem_montagem_e_sem_pedidos(tmp_path):
    ep, corte = _episodio(tmp_path, [_foto()])
    (corte / "montagem.json").unlink()
    assert buscar_episodio(ep, None, [], falso, baixar) == {1: "erro: montagem.json não encontrado, rode preparar"}
    (corte / "pedidos.json").unlink()
    assert buscar_episodio(ep, None, [], falso, baixar) == {}


def test_listar_exige_escolha(tmp_path):
    ep, corte = _episodio(tmp_path, [_foto()])
    assert listar_episodio(ep, None, [], falso, lambda u: 1000) == {1: "erro: momento 1 sem escolha"}
    assert not (corte / "imagens.md").exists()


def test_listar_escreve_imagens_md_lido_pelo_leitor(tmp_path):
    ep, corte = _completo(tmp_path)
    assert listar_episodio(ep, None, [], falso, lambda u: 2048) == {1: "ok"}
    (corte / "imagens").mkdir(exist_ok=True)
    for arquivo in ("01-gripen.jpg", "02-uno-com-escada.png", "03-manchete.png"):
        (corte / "imagens" / arquivo).write_bytes(b"x")
    assert [(i.inicio, i.fim) for i in ler_imagens(corte)] == [(10.0, 12.0), (20.0, 23.0), (30.0, 33.0)]
    texto = (corte / "imagens.md").read_text("utf-8")
    assert "Baixar: https://u/1920px-A1.jpg" in texto
    assert "## 1. 00:00:10,000 a 00:00:12,000 — Gripen" in texto
    assert "Autor e licença: Fulano, CC BY-SA 4.0" in texto
    assert "Autor e licença: cartão do canal, Folha" in texto
    assert "Autor e licença: ilustração de IA, ChatGPT (OpenAI)" in texto
    assert "\r" not in texto


def test_listar_lista_e_prompts(tmp_path):
    ep, corte = _completo(tmp_path)
    listar_episodio(ep, None, [], falso, lambda u: 2048)
    lista = (ep / "lista-imagens.md").read_text("utf-8")
    assert "— 2 KB" in lista and "gerar por IA" in lista and "cartão do canal" in lista
    prompts = (ep / "prompts-chatgpt.md").read_text("utf-8")
    assert "# Prompts para o ChatGPT: Entre Assuntos #03" in prompts
    assert "1 → corte 01, imagem 2" in prompts and "1. Um Uno com escada no teto" in prompts
    assert (ep / "ia-entrada").is_dir()
    assert [m.numero for m in ler_pedidos(corte)] == [1, 2, 3]
    assert ler_pedidos(corte)[0].bytes == 2048


def test_listar_sem_link_nao_descarta_para_sempre(tmp_path):
    ep, corte = _completo(tmp_path)
    resultado = listar_episodio(ep, None, [], sem_thumb, lambda u: 1)[1]
    assert "sem link de download" in resultado
    momentos = ler_pedidos(corte)
    assert not momentos[0].descartar and momentos[0].motivo == "sem link de download"
    assert [m.numero for m in momentos] == [None, 1, 2]
    assert listar_episodio(ep, None, [], falso, lambda u: 1) == {1: "ok"}
    assert [m.numero for m in ler_pedidos(corte)] == [1, 2, 3]
    assert ler_pedidos(corte)[0].motivo == ""


def test_listar_nao_cabe_nao_grava_descarte_nem_tempos(tmp_path):
    ep, corte = _episodio(tmp_path, [
        _foto(0.0, 1.0, escolha=1, candidatas=[{"titulo": "File:A1.jpg", "pagina": "p", "miniatura": "m",
                                                "largura": 1, "altura": 1, "autor": "F", "licenca": "CC0"}]),
        Momento(1.0, 4.0, "f", "ia", "Uno", prompt="Um Uno"),
    ])
    resultado = listar_episodio(ep, None, [], falso, lambda u: 1)[1]
    assert resultado.startswith("ok com alertas") and "não cabe" in resultado
    momentos = ler_pedidos(corte)
    assert not momentos[0].descartar and (momentos[0].inicio, momentos[0].fim) == (0.0, 1.0)
    assert "não cabe" in momentos[0].motivo and [m.numero for m in momentos] == [None, 1]


def test_listar_duas_vezes_troca_ia_por_foto(tmp_path):
    ep, corte = _completo(tmp_path)
    listar_episodio(ep, None, [], falso, lambda u: 1)
    momentos = ler_pedidos(corte)
    momentos[1] = Momento(20.0, 23.0, "fala dois", "foto", "Uno", busca="uno", escolha=1, candidatas=momentos[0].candidatas)
    gravar_pedidos(corte, momentos)
    listar_episodio(ep, None, [], falso, lambda u: 1)
    prompts = (ep / "prompts-chatgpt.md").read_text("utf-8")
    assert "Um Uno com escada" not in prompts and "Nenhuma imagem de IA" in prompts


def test_listar_nao_mostra_foto_antiga_de_corte_refeito(tmp_path):
    ep, corte1 = _completo(tmp_path)
    (ep / "aprovados.json").write_text(json.dumps({"cortes": [CORTE, {**CORTE, "numero": 2, "titulo": "Outro"}]}), "utf-8")
    corte2 = ep / "02-outro"
    corte2.mkdir()
    gravar_receita(corte2, Receita([(0.0, 60.0)], [Plano(0.0, 60.0)], []))
    gravar_pedidos(corte2, [Momento(20.0, 23.0, "f", "ia", "Outra", prompt="Outra cena")])
    listar_episodio(ep, None, [], falso, lambda u: 1)
    buscar_episodio(ep, {1}, [], falso, baixar)
    listar_episodio(ep, {2}, [], falso, lambda u: 1)
    lista = (ep / "lista-imagens.md").read_text("utf-8")
    assert "Gripen" not in lista and "Outra" in lista


def test_listar_sem_nenhum_corte_listado_regrava_lista(tmp_path):
    ep, _ = _completo(tmp_path)
    listar_episodio(ep, None, [], falso, lambda u: 1)
    buscar_episodio(ep, {1}, [], falso, baixar)
    listar_episodio(ep, {1}, [], falso, lambda u: 1)
    assert "Gripen" not in (ep / "lista-imagens.md").read_text("utf-8")


def test_nome_arquivo():
    m = Momento(0, 1, "f", "foto", "Uno, o rápido", numero=4)
    assert nome_arquivo(m, ".jpg") == "imagens/04-uno-o-rapido.jpg"


# --- baixar_episodio ---
from esteira.fluxo_imagens import baixar_episodio  # noqa: E402
from esteira.receita import ler_receita  # noqa: E402


def _listado(tmp_path, ia=True):
    ep, corte = _completo(tmp_path)
    if not ia:
        momentos = [m for m in ler_pedidos(corte) if m.tipo != "ia"]
        gravar_pedidos(corte, momentos)
    listar_episodio(ep, None, [], falso, lambda u: 2048)
    return ep, corte


def _ia(ep, nome="gerada.png"):
    Image.new("RGB", (32, 56), (10, 10, 200)).save(ep / "ia-entrada" / nome)


def _contador(chamadas):
    def baixar_imagem(url, destino):
        chamadas.append(url)
        baixar(url, destino)
    return baixar_imagem


def baixar_html(url, destino):
    destino.write_text("<html>", "utf-8")


def test_baixar_foto_cartao_e_ia(tmp_path):
    ep, corte = _listado(tmp_path)
    _ia(ep)
    assert baixar_episodio(ep, None, baixar) == {1: "ok: 3 imagens"}
    assert len(ler_receita(corte).imagens) == 3
    assert sorted(p.name for p in (corte / "imagens").iterdir()) == [
        ".origens.json", "01-gripen.jpg", "02-uno-com-escada.png", "03-manchete.png"]
    origens = json.loads((corte / "imagens" / ".origens.json").read_text("utf-8"))
    assert origens == {"01-gripen.jpg": "https://u/1920px-A1.jpg", "03-manchete.png": "cartao|Titulo|Folha|2026-01-02"}


def test_baixar_falha_isolada(tmp_path):
    ep, corte = _listado(tmp_path)
    _ia(ep)
    assert baixar_episodio(ep, None, baixar_html)[1] == "ok com alertas: imagem 1: download falhou"
    assert not list((corte / "imagens").glob("*.parcial"))
    assert not (corte / "imagens" / "01-gripen.jpg").exists()


def test_baixar_erro_de_rede_e_alerta(tmp_path):
    ep, corte = _listado(tmp_path)
    _ia(ep)

    def cai(url, destino):
        destino.write_bytes(b"meio")
        raise OSError("caiu")

    assert baixar_episodio(ep, None, cai)[1] == "ok com alertas: imagem 1: download falhou"
    assert not list((corte / "imagens").glob("*.parcial"))


def test_baixar_nao_repete_download(tmp_path):
    ep, corte = _listado(tmp_path)
    _ia(ep)
    chamadas = []
    baixar_episodio(ep, None, _contador(chamadas))
    assert len(chamadas) == 1
    chamadas.clear()
    assert baixar_episodio(ep, None, _contador(chamadas)) == {1: "ok: 3 imagens"}
    assert chamadas == []


def test_baixar_contagem_ia_errada(tmp_path):
    ep, corte = _listado(tmp_path)
    assert baixar_episodio(ep, None, baixar) == {1: "erro: ia-entrada/: esperadas 1 imagens, encontradas 0"}
    assert not (corte / "imagens").exists()


def test_baixar_episodio_sem_ia(tmp_path):
    ep, corte = _listado(tmp_path, ia=False)
    assert baixar_episodio(ep, None, baixar) == {1: "ok: 2 imagens"}
    assert not (ep / "ia-entrada" / ".mapa.tsv").exists()


def test_baixar_arquivo_antigo_com_mesmo_numero(tmp_path):
    ep, corte = _listado(tmp_path)
    _ia(ep)
    (corte / "imagens").mkdir()
    (corte / "imagens" / "01-outro-nome.jpg").write_bytes(b"x")
    (corte / "imagens" / "descartadas").mkdir()
    (corte / "imagens" / "descartadas" / "02-velho.png").write_bytes(b"x")
    (corte / "imagens" / "02-uno-com-escada.png.parcial").write_bytes(b"x")
    resultado = baixar_episodio(ep, None, baixar)
    assert resultado == {1: "erro: imagens/ tem arquivo antigo com o mesmo número: 01-outro-nome.jpg"}
    assert sorted(p.name for p in (corte / "imagens").iterdir()) == [
        "01-outro-nome.jpg", "02-uno-com-escada.png.parcial", "descartadas"]


def test_baixar_ignora_subpasta_e_parcial_sem_conflito(tmp_path):
    ep, corte = _listado(tmp_path)
    _ia(ep)
    (corte / "imagens" / "descartadas").mkdir(parents=True)
    (corte / "imagens" / "descartadas" / "01-velho.jpg").write_bytes(b"x")
    (corte / "imagens" / "01-gripen.jpg.parcial").write_bytes(b"x")
    assert baixar_episodio(ep, None, baixar) == {1: "ok: 3 imagens"}


def test_baixar_sem_montagem(tmp_path):
    ep, corte = _listado(tmp_path)
    _ia(ep)
    (corte / "montagem.json").unlink()
    assert baixar_episodio(ep, None, baixar) == {1: "erro: montagem.json não encontrado, rode preparar"}


def test_baixar_corte_sem_pedidos_nao_aparece(tmp_path):
    ep, corte = _listado(tmp_path)
    _ia(ep)
    (corte / "pedidos.json").unlink()
    assert baixar_episodio(ep, None, baixar) == {}


def _dois_cortes(tmp_path):
    """Corte 1: foto + IA; corte 2: IA + cartão. Já listado."""
    ep, corte1 = _episodio(tmp_path, [
        _foto(escolha=1, candidatas=[{"titulo": "File:A1.jpg", "pagina": "p", "miniatura": "m",
                                      "largura": 2000, "altura": 1000, "autor": "F", "licenca": "CC BY 4.0"}]),
        Momento(20.0, 23.0, "f", "ia", "Uno com escada", prompt="Um Uno com escada"),
    ])
    corte2 = ep / "02-segundo-corte"
    corte2.mkdir()
    gravar_receita(corte2, Receita([(0.0, 60.0)], [Plano(0.0, 60.0)], []))
    gravar_pedidos(corte2, [
        Momento(10.0, 13.0, "f", "ia", "Chuva forte", prompt="Chuva forte na avenida"),
        Momento(30.0, 33.0, "f", "noticia", "Manchete", titulo="Titulo", veiculo="Folha", data="2026-01-02"),
    ])
    dados = json.loads((ep / "aprovados.json").read_text("utf-8"))
    dados["cortes"].append({"numero": 2, "titulo": "Segundo corte", "inicio": 0.0, "fim": 60.0, "clima": "leve"})
    (ep / "aprovados.json").write_text(json.dumps(dados), "utf-8")
    listar_episodio(ep, None, [], falso, lambda u: 2048)
    return ep, corte1, corte2


def test_baixar_filtro_de_cortes_mantem_ia_de_todos(tmp_path):
    ep, corte1, corte2 = _dois_cortes(tmp_path)
    # ordem do prompts-chatgpt.md: corte 1 (Uno), corte 2 (Chuva); a de menor mtime é a primeira
    Image.new("RGB", (32, 56), (1, 1, 1)).save(ep / "ia-entrada" / "a.png")
    Image.new("RGB", (32, 56), (2, 2, 2)).save(ep / "ia-entrada" / "b.png")
    import os
    os.utime(ep / "ia-entrada" / "a.png", (100, 100))
    os.utime(ep / "ia-entrada" / "b.png", (200, 200))
    assert baixar_episodio(ep, {2}, baixar) == {2: "ok: 2 imagens"}
    assert Image.open(corte1 / "imagens" / "02-uno-com-escada.png").getpixel((0, 0)) == (1, 1, 1)
    assert Image.open(corte2 / "imagens" / "01-chuva-forte.png").getpixel((0, 0)) == (2, 2, 2)
    assert not (corte1 / "imagens" / "01-gripen.jpg").exists()
    assert ler_receita(corte1).imagens == [] and len(ler_receita(corte2).imagens) == 2


def test_baixar_ordem_ia_ignora_corte_com_erro_no_listar(tmp_path):
    ep, corte1, corte2 = _dois_cortes(tmp_path)
    momentos = ler_pedidos(corte2)
    assert momentos[0].numero == 1  # número antigo continua no pedidos.json
    assert listar_episodio(ep, None, ["Chuva Forte"], falso, lambda u: 2048)[2].startswith("erro: momento 1: prompt cita pessoa")
    assert ler_pedidos(corte2)[0].numero == 1
    assert "Chuva forte" not in (ep / "prompts-chatgpt.md").read_text("utf-8")
    lista = json.loads((ep / "lista-imagens.json").read_text("utf-8"))
    assert [i["pasta"] for i in lista["ia"]] == ["01-bom-corte"] and lista["cortes"] == ["01-bom-corte"]
    Image.new("RGB", (32, 56)).save(ep / "ia-entrada" / "a.png")
    assert baixar_episodio(ep, {1}, baixar) == {1: "ok: 2 imagens"}
    assert (ep / "ia-entrada" / ".mapa.tsv").read_text("utf-8").count(chr(10)) == 1


def test_baixar_ordem_mudou(tmp_path):
    ep, corte1, corte2 = _dois_cortes(tmp_path)
    for nome in ("a.png", "b.png"):
        Image.new("RGB", (32, 56)).save(ep / "ia-entrada" / nome)
    momentos = ler_pedidos(corte2)
    momentos[0].nome = "Outro nome"
    gravar_pedidos(corte2, momentos)
    esperado = "erro: ordem das imagens de IA mudou, rode imagens lista de novo"
    assert baixar_episodio(ep, None, baixar) == {1: esperado, 2: esperado}
    assert not (corte1 / "imagens").exists() and not (ep / "ia-entrada" / ".mapa.tsv").exists()


def test_baixar_sem_lista_json_recusa(tmp_path):
    ep, corte = _listado(tmp_path)
    _ia(ep)
    (ep / "lista-imagens.json").unlink()
    assert baixar_episodio(ep, None, baixar) == {1: "erro: rode imagens lista antes de baixar"}
    assert not (corte / "imagens").exists()


def test_listar_grava_ia_vazia_sem_ia(tmp_path):
    ep, corte = _listado(tmp_path, ia=False)
    assert json.loads((ep / "lista-imagens.json").read_text("utf-8")) == {"cortes": ["01-bom-corte"], "ia": []}


def test_baixar_recusa_corte_com_erro_na_ultima_lista(tmp_path):
    ep, corte1, corte2 = _dois_cortes(tmp_path)
    assert listar_episodio(ep, None, ["Chuva Forte"], falso, lambda u: 2048)[2].startswith("erro:")
    Image.new("RGB", (32, 56)).save(ep / "ia-entrada" / "a.png")
    resultado = baixar_episodio(ep, None, baixar)
    assert resultado == {1: "ok: 2 imagens", 2: "erro: corte fora da última lista, rode imagens lista"}
    assert not (corte2 / "imagens").exists()


def test_baixar_imagem_a_mais_em_ia_entrada(tmp_path):
    ep, corte = _listado(tmp_path)
    _ia(ep, "a.png")
    _ia(ep, "b.png")
    assert baixar_episodio(ep, None, baixar) == {1: "erro: ia-entrada/: esperadas 1 imagens, encontradas 2"}
    assert not (corte / "imagens").exists()


def test_baixar_foto_que_falhou_vem_na_segunda_rodada(tmp_path):
    ep, corte = _listado(tmp_path)
    _ia(ep)
    assert baixar_episodio(ep, None, baixar_html)[1].startswith("ok com alertas")
    chamadas = []
    assert baixar_episodio(ep, None, _contador(chamadas)) == {1: "ok: 3 imagens"}
    assert len(chamadas) == 1  # só a foto; IA e cartão já existiam


def test_baixar_cartao_que_falha_vira_alerta(tmp_path, monkeypatch):
    ep, corte = _listado(tmp_path)
    _ia(ep)

    def quebra_cartao(*args):
        raise OSError("sem fonte")

    monkeypatch.setattr("esteira.fluxo_imagens.gerar_cartao", quebra_cartao)
    assert baixar_episodio(ep, None, baixar)[1] == "ok com alertas: imagem 3: cartão falhou"


def test_listar_apaga_motivo_so_quando_nao_e_descarte_manual(tmp_path):
    ep, corte = _completo(tmp_path)
    momentos = ler_pedidos(corte)
    momentos[0].descartar, momentos[0].motivo = True, "foto ruim"
    gravar_pedidos(corte, momentos)
    listar_episodio(ep, None, [], falso, lambda u: 1)
    primeiro = ler_pedidos(corte)[0]
    assert primeiro.descartar and primeiro.motivo == "foto ruim"


def test_lista_informa_origem_e_licenca_da_foto(tmp_path):
    ep, corte = _completo(tmp_path)
    listar_episodio(ep, None, [], falso, lambda u: 2048)
    lista = (ep / "lista-imagens.md").read_text("utf-8")
    assert "- 1. 00:00:10,000 a 00:00:12,000 — Gripen — 01-gripen.jpg — Wikimedia Commons: https://c/A1 — CC BY-SA 4.0 — 2 KB" in lista
    listar_episodio(ep, None, [], falso, lambda u: None)
    assert "CC BY-SA 4.0 — tamanho desconhecido" in (ep / "lista-imagens.md").read_text("utf-8")


def test_baixar_falhas_inesperadas_viram_alerta(tmp_path):
    import http.client
    ep, corte = _listado(tmp_path)
    _ia(ep)

    def incompleto(url, destino):
        destino.write_bytes(b"meio")
        raise http.client.IncompleteRead(b"")

    assert baixar_episodio(ep, None, incompleto)[1] == "ok com alertas: imagem 1: download falhou"
    assert not list((corte / "imagens").glob("*.parcial"))

    def truncado(url, destino):
        import io
        buf = io.BytesIO()
        Image.effect_noise((200, 200), 100).convert("RGB").save(buf, "JPEG")
        destino.write_bytes(buf.getvalue()[:-400] if len(buf.getvalue()) > 800 else b"x")

    assert baixar_episodio(ep, None, truncado)[1] == "ok com alertas: imagem 1: download falhou"
    assert not list((corte / "imagens").glob("*.parcial"))
    assert not (corte / "imagens" / "01-gripen.jpg").exists()


def _duas_candidatas():
    base = {"pagina": "p", "miniatura": "m", "largura": 2000, "altura": 1000, "autor": "F", "licenca": "CC0"}
    return [{**base, "titulo": "File:A1.jpg"}, {**base, "titulo": "File:A2.jpg"}]


def _cor_pela_url(url, destino):
    Image.new("RGB", (64, 40), (200, 0, 0) if "A1" in url else (0, 0, 200)).save(destino, "JPEG")


def test_baixar_troca_de_escolha_substitui_o_arquivo(tmp_path):
    ep, corte = _episodio(tmp_path, [_foto(escolha=1, candidatas=_duas_candidatas())])
    listar_episodio(ep, None, [], falso, lambda u: 1)
    baixar_episodio(ep, None, _cor_pela_url)
    arquivo = corte / "imagens" / "01-gripen.jpg"
    assert Image.open(arquivo).getpixel((0, 0))[0] > 150
    momentos = ler_pedidos(corte)
    momentos[0].escolha = 2
    gravar_pedidos(corte, momentos)
    listar_episodio(ep, None, [], falso, lambda u: 1)
    chamadas = []

    def registra(url, destino):
        chamadas.append(url)
        _cor_pela_url(url, destino)

    assert baixar_episodio(ep, None, registra) == {1: "ok: 1 imagens"}
    assert chamadas == ["https://u/1920px-A2.jpg"]
    assert Image.open(arquivo).getpixel((0, 0))[2] > 150
    assert not list((corte / "imagens").glob("*.parcial*"))
    chamadas.clear()
    baixar_episodio(ep, None, registra)
    assert chamadas == []


def test_baixar_troca_falha_mantem_arquivo_antigo(tmp_path):
    ep, corte = _episodio(tmp_path, [_foto(escolha=1, candidatas=_duas_candidatas())])
    listar_episodio(ep, None, [], falso, lambda u: 1)
    baixar_episodio(ep, None, _cor_pela_url)
    momentos = ler_pedidos(corte)
    momentos[0].escolha = 2
    gravar_pedidos(corte, momentos)
    listar_episodio(ep, None, [], falso, lambda u: 1)
    assert baixar_episodio(ep, None, baixar_html)[1] == "ok com alertas: imagem 1: download falhou"
    assert Image.open(corte / "imagens" / "01-gripen.jpg").getpixel((0, 0))[0] > 150


def test_baixar_cartao_com_dados_novos_e_regerado(tmp_path):
    ep, corte = _episodio(tmp_path, [Momento(30.0, 33.0, "f", "noticia", "Manchete", titulo="Titulo", veiculo="Folha", data="2026-01-02")])
    listar_episodio(ep, None, [], falso, lambda u: 1)
    baixar_episodio(ep, None, baixar)
    arquivo = corte / "imagens" / "01-manchete.png"
    antes = arquivo.read_bytes()
    momentos = ler_pedidos(corte)
    momentos[0].titulo = "Outro titulo bem diferente"
    gravar_pedidos(corte, momentos)
    listar_episodio(ep, None, [], falso, lambda u: 1)
    baixar_episodio(ep, None, baixar)
    assert arquivo.read_bytes() != antes
    assert not list((corte / "imagens").glob("*parcial*"))


def test_baixar_arquivo_feito_a_mao_e_mantido_com_alerta(tmp_path):
    ep, corte = _episodio(tmp_path, [_foto(escolha=1, candidatas=_duas_candidatas())])
    listar_episodio(ep, None, [], falso, lambda u: 1)
    (corte / "imagens").mkdir()
    Image.new("RGB", (64, 40), (0, 200, 0)).save(corte / "imagens" / "01-gripen.jpg")
    chamadas = []
    resultado = baixar_episodio(ep, None, _contador(chamadas))
    assert resultado == {1: "ok com alertas: imagem 1: arquivo existente sem origem registrada, mantido"}
    assert chamadas == [] and Image.open(corte / "imagens" / "01-gripen.jpg").getpixel((0, 0))[1] > 150
