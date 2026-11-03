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
