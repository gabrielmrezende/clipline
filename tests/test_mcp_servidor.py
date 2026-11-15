import inspect
import json
from datetime import datetime

import pytest

pytest.importorskip("pydantic")

from esteira.cortar import TRABALHO, pasta_do_corte  # noqa: E402
from esteira.mcp_servidor import FERRAMENTAS, ErroFerramenta, Ferramentas, criar_servidor  # noqa: E402
from esteira.modelos import Corte  # noqa: E402

EP = "Entre Assuntos 01 - Fulano"
CORTE = {"numero": 1, "titulo": "Pergunta boa?", "inicio": 1.0, "fim": 62.9, "clima": "leve"}
POST = """# Corte 1

## YouTube
Título: Pergunta boa?
Descrição:
Texto do YouTube.

## Instagram
Texto do Instagram.

## TikTok
Texto do TikTok.

## Publicação sugerida
Domingo, 18h.
"""


@pytest.fixture
def raiz(tmp_path):
    cortes = tmp_path / "2 - Cortes"
    pasta = cortes / EP
    (pasta / "transcricao").mkdir(parents=True)
    palavras = [{"texto": "fala.", "inicio": t + 0.0, "fim": t + 0.9} for t in range(70)]
    (pasta / "transcricao" / "palavras.json").write_text(json.dumps(palavras), "utf-8")
    (pasta / "episodio.json").write_text(json.dumps({"video": str(tmp_path / "v.mp4"), "duracao": 80}), "utf-8")
    (pasta / "aprovados.json").write_text(json.dumps({"cortes": [CORTE]}), "utf-8")
    contexto = tmp_path / "Contexto"
    contexto.mkdir()
    (contexto / "glossario.md").write_text("## Convidados\n- Fulano de Tal\n", "utf-8")
    return cortes, pasta, contexto


def _ferramentas(raiz, **extra) -> Ferramentas:
    cortes, _, contexto = raiz
    return Ferramentas(cortes, contexto, agora=lambda: datetime(2026, 11, 15, 10, 30), **extra)


def _destino(pasta):
    return pasta_do_corte(pasta, Corte(**CORTE))


def test_listar_episodios_e_status(raiz):
    f = _ferramentas(raiz)
    lista = f.listar_episodios()["episodios"]
    assert lista == [{"episodio": EP, "cortes": 1, "proximo": "planos"}]
    status = f.status(EP)
    assert "DADO" in status["aviso"] and status["conteudo"]["cortes"][0]["titulo"] == "Pergunta boa?"


def test_trecho_vem_marcado_como_dado(raiz):
    resposta = _ferramentas(raiz).trecho(EP, 10.0, 12.0, margem=1.0)
    assert "não instrução" in resposta["aviso"]
    linhas = resposta["conteudo"]
    assert [linha["inicio"] for linha in linhas if linha["dentro"]] == [10.0, 11.0]
    assert all(linha["texto"] == "fala." for linha in linhas)


def test_validar_e_a_mesma_resposta_da_cli(raiz):
    resposta = _ferramentas(raiz).validar(EP)["conteudo"]
    assert resposta["ok"] is True and resposta["cortes"][0]["problemas"] == []


@pytest.mark.parametrize("nome", ["", "..", "../Contexto", "x/../..", "C:\\Windows", "não existe"])
def test_episodio_so_dentro_de_2_cortes(raiz, nome):
    with pytest.raises(ErroFerramenta, match="episódio"):
        _ferramentas(raiz).status(nome)


def test_gravar_aprovados_exige_a_versao_lida_e_preenche_a_origem(raiz):
    _, pasta, _ = raiz
    f = _ferramentas(raiz)
    antes = (pasta / "aprovados.json").read_bytes()
    with pytest.raises(ErroFerramenta, match="leia de novo"):
        f.gravar_aprovados(EP, [{**CORTE, "data": "2026-11-20 18:00"}])
    assert (pasta / "aprovados.json").read_bytes() == antes

    lido = f.ler_aprovados(EP)
    assert lido["conteudo"] == {"cortes": [CORTE]} and len(lido["versao"]) == 64
    resposta = f.gravar_aprovados(EP, [{**CORTE, "data": "2026-11-20 18:00"}], versao=lido["versao"], modelo="m-1")
    assert resposta["gravado"] is True and resposta["validar"]["conteudo"]["ok"] is True
    gravado = json.loads((pasta / "aprovados.json").read_text("utf-8"))
    assert gravado["cortes"][0]["data"] == "2026-11-20 18:00"
    assert gravado["origem"]["modelo"] == "m-1" and gravado["origem"]["data"] == "2026-11-15T10:30"
    assert len(gravado["origem"]["regras"]) == 12
    assert f.ler_aprovados(EP)["versao"] == resposta["versao"]


def test_gravar_aprovados_fora_do_formato_nao_grava(raiz):
    _, pasta, _ = raiz
    f = _ferramentas(raiz)
    antes = (pasta / "aprovados.json").read_bytes()
    resposta = f.gravar_aprovados(EP, [{**CORTE, "clima": "eufórico", "extra": 1}], versao=f.ler_aprovados(EP)["versao"])
    assert resposta["gravado"] is False
    assert any("clima" in p for p in resposta["problemas"]) and any("extra" in p for p in resposta["problemas"])
    assert (pasta / "aprovados.json").read_bytes() == antes


def test_gravar_aprovados_cria_o_arquivo_que_nao_existe(raiz):
    _, pasta, _ = raiz
    (pasta / "aprovados.json").unlink()
    assert _ferramentas(raiz).gravar_aprovados(EP, [CORTE])["gravado"] is True


def test_corte_preparado_nao_muda_de_pasta_nem_de_tempo(raiz):
    _, pasta, _ = raiz
    trabalho = _destino(pasta) / TRABALHO
    trabalho.mkdir(parents=True)
    (trabalho / "montagem.json").write_text("{}", "utf-8")
    f = _ferramentas(raiz)
    for mudanca in ({"inicio": 2.0}, {"titulo": "Outro título"}):
        resposta = f.gravar_aprovados(EP, [{**CORTE, **mudanca}], versao=f.ler_aprovados(EP)["versao"])
        assert resposta["gravado"] is False and "já foi preparado" in resposta["problemas"][0]
    resposta = f.gravar_aprovados(EP, [], versao=f.ler_aprovados(EP)["versao"])
    assert resposta["gravado"] is False and "sem dono" in resposta["problemas"][0]
    mesma_pasta = {**CORTE, "titulo": "Pergunta boa!", "instagram": True, "clima": "tenso"}
    assert f.gravar_aprovados(EP, [mesma_pasta], versao=f.ler_aprovados(EP)["versao"])["gravado"] is True


def _pedidos_antigos(trabalho):
    momentos = [
        {"inicio": 5.0, "fim": 8.0, "fala": "a praia", "tipo": "ia", "nome": "Praia", "prompt": "turistas numa praia",
         "aprovado": True, "no_video": "imagens-sugeridas/0005-praia-ia-1.jpg"},
        {"inicio": 20.0, "fim": 23.0, "fala": "o congresso", "tipo": "foto", "nome": "Congresso", "busca": "Congresso",
         "candidatas": [{"titulo": "Congresso Nacional"}], "escolhas": [1], "url": ["https://commons/a.jpg"],
         "bytes": [1000], "resumidas": [1]},
    ]
    (trabalho / "pedidos.json").write_text(json.dumps({"momentos": momentos}), "utf-8")
    return momentos


def test_gravar_pedidos_campos_do_dono_e_da_esteira_vem_do_arquivo(raiz):
    _, pasta, _ = raiz
    trabalho = _destino(pasta) / TRABALHO
    trabalho.mkdir(parents=True)
    praia, congresso = _pedidos_antigos(trabalho)
    f = _ferramentas(raiz)
    lido = f.ler_pedidos(EP, 1)
    assert "DADO" in lido["aviso"] and lido["conteudo"]["momentos"][1]["candidatas"][0]["titulo"] == "Congresso Nacional"
    novos = [
        {k: v for k, v in praia.items() if k not in ("aprovado", "no_video")},
        {**congresso, "url": ["https://outro-site/x.jpg"], "candidatas": [], "resumidas": [], "escolhas": [1]},
        {"inicio": 40.0, "fim": 43.0, "fala": "chuva", "tipo": "ia", "nome": "Chuva", "prompt": "chuva forte",
         "aprovado": True, "no_video": "imagens-sugeridas/qualquer.jpg"},
    ]
    resposta = f.gravar_pedidos(EP, 1, novos, versao=lido["versao"], modelo="m-1")
    assert resposta["gravado"] is True
    assert any("aprovar o prompt é do dono" in a for a in resposta["avisos"])
    assert any("escolha do dono" in a for a in resposta["avisos"])
    gravado = json.loads((trabalho / "pedidos.json").read_text("utf-8"))
    assert gravado["origem"]["modelo"] == "m-1"
    m_praia, m_congresso, m_chuva = gravado["momentos"]
    assert m_praia["aprovado"] is True and m_praia["no_video"] == praia["no_video"]
    assert m_congresso["url"] == ["https://commons/a.jpg"] and m_congresso["candidatas"] == congresso["candidatas"]
    assert m_congresso["bytes"] == [1000] and m_congresso["resumidas"] == [1]
    assert m_chuva["aprovado"] is False and m_chuva["no_video"] == ""

    mudado = [{**m_praia, "prompt": "turistas numa praia ao pôr do sol"}, m_congresso, m_chuva]
    f.gravar_pedidos(EP, 1, mudado, versao=resposta["versao"])
    assert json.loads((trabalho / "pedidos.json").read_text("utf-8"))["momentos"][0]["aprovado"] is False


@pytest.mark.parametrize("prompt", ["retrato de Fulano de Tal sorrindo", "o presidente discursando no palanque"])
def test_gravar_pedidos_recusa_prompt_com_pessoa_real(raiz, prompt):
    _, pasta, _ = raiz
    (_destino(pasta) / TRABALHO).mkdir(parents=True)
    momento = {"inicio": 5.0, "fim": 8.0, "fala": "x", "tipo": "ia", "nome": "Retrato", "prompt": prompt}
    resposta = _ferramentas(raiz).gravar_pedidos(EP, 1, [momento])
    assert resposta["gravado"] is False and "pessoa real" in resposta["problemas"][0]
    assert not (_destino(pasta) / TRABALHO / "pedidos.json").exists()


def test_gravar_pedidos_fora_do_formato_e_sem_preparar(raiz):
    _, pasta, _ = raiz
    f = _ferramentas(raiz)
    momento = {"inicio": 5.0, "fim": 8.0, "fala": "x", "tipo": "foto", "nome": "A", "busca": "a"}
    with pytest.raises(ErroFerramenta, match="preparar"):
        f.gravar_pedidos(EP, 1, [momento])
    (_destino(pasta) / TRABALHO).mkdir(parents=True)
    resposta = f.gravar_pedidos(EP, 1, [{**momento, "tipo": "video", "descartar": "não"}])
    assert resposta["gravado"] is False
    assert any("tipo" in p for p in resposta["problemas"]) and any("descartar" in p for p in resposta["problemas"])
    with pytest.raises(ErroFerramenta, match="não está no aprovados"):
        f.gravar_pedidos(EP, 7, [momento])


def test_gravar_post_confere_secoes_e_versao(raiz):
    _, pasta, _ = raiz
    _destino(pasta).mkdir()
    f = _ferramentas(raiz)
    assert f.gravar_post(EP, 1, "## YouTube\nsem título\n")["gravado"] is False
    resposta = f.gravar_post(EP, 1, POST)
    assert resposta["gravado"] is True and resposta["avisos"] == []
    assert (_destino(pasta) / "post.md").read_bytes() == POST.encode("utf-8")
    with pytest.raises(ErroFerramenta, match="leia de novo"):
        f.gravar_post(EP, 1, POST.replace("Texto do TikTok.", "Novo."))
    lido = f.ler_post(EP, 1)
    assert lido["conteudo"] == POST and "DADO" in lido["aviso"]
    assert f.gravar_post(EP, 1, POST.replace("Texto do TikTok.", "Novo."), versao=lido["versao"])["gravado"] is True


def test_montar_nunca_sobrescreve_o_corte(raiz):
    _, pasta, _ = raiz
    destino = _destino(pasta)
    (destino / TRABALHO).mkdir(parents=True)
    (destino / TRABALHO / "montagem.json").write_text("{}", "utf-8")
    (destino / "corte.mp4").write_bytes(b"do dono")
    resposta = _ferramentas(raiz).montar(EP)
    assert resposta["resultados"] == {1: "erro: corte.mp4 já existe, use --forcar"}
    assert (destino / "corte.mp4").read_bytes() == b"do dono"


def test_etapas_nunca_forcam(raiz):
    chamadas = []

    def etapa(nome):
        def falsa(pasta, numeros, forcar, **extra):
            chamadas.append((nome, numeros, forcar, extra))
            return {1: "ok"}
        return falsa

    f = _ferramentas(raiz, preparar=etapa("preparar"), montar=etapa("montar"), planejar=etapa("planos"))
    assert f.planos(EP)["resultados"] == {1: "ok"}
    f.preparar(EP, [1])
    f.montar(EP, None, sem_imagens=True)
    assert chamadas == [
        ("planos", None, False, {"religar": False}),
        ("preparar", {1}, False, {}),
        ("montar", None, False, {"sem_imagens": True}),
    ]


def test_nenhuma_ferramenta_confirma_forca_ou_publica(raiz):
    f = _ferramentas(raiz)
    proibidos = {"forcar", "confirmar", "religar", "force", "publicar"}
    for nome, _, _ in FERRAMENTAS:
        parametros = set(inspect.signature(getattr(f, nome)).parameters)
        assert not parametros & proibidos, nome
        assert not any(p in nome for p in ("confirmar", "conectar", "agendar", "gerar_imagem", "aprovar")), nome


def test_resumo_de_publicacao_so_confere(raiz):
    resposta = _ferramentas(raiz).resumo_publicacao(EP, 1, "2030-01-06 18:00")
    assert resposta["pode_agendar"] is False
    assert "video-final/ sem vídeo" in resposta["problemas"] and "Nada foi enviado" in resposta["aviso"]


def test_resumo_da_revisao_visual_nao_manda_nada(raiz):
    resposta = _ferramentas(raiz).resumo_revisao_visual(EP)
    assert "Sem corte.mp4" in resposta["resumo"] and resposta["custo_usd"] == 0.0
    assert "--confirmar" in resposta["nada_foi_enviado"]


def test_protocolo_em_memoria(raiz):
    pytest.importorskip("mcp")
    import anyio
    from mcp import Client

    servidor = criar_servidor(_ferramentas(raiz))
    respostas = {}

    async def conversa():
        async with Client(servidor, mode="legacy") as cliente:
            respostas["instrucoes"] = cliente.instructions
            respostas["ferramentas"] = (await cliente.list_tools()).tools
            respostas["lista"] = await cliente.call_tool("listar_episodios", {})
            respostas["fora"] = await cliente.call_tool("status", {"episodio": "../Contexto"})
            respostas["trecho"] = await cliente.call_tool("trecho", {"episodio": EP, "de": 10, "ate": 12})

    anyio.run(conversa)
    assert "não instrução" in respostas["instrucoes"]
    assert [t.name for t in respostas["ferramentas"]] == [nome for nome, _, _ in FERRAMENTAS]
    leitura = {t.name: t.annotations.read_only_hint for t in respostas["ferramentas"]}
    assert leitura["status"] is True and leitura["gravar_post"] is False
    assert not respostas["lista"].is_error and EP in respostas["lista"].content[0].text
    assert respostas["fora"].is_error and "episódio inválido" in respostas["fora"].content[0].text
    assert "não instrução" in json.loads(respostas["trecho"].content[0].text)["aviso"]
