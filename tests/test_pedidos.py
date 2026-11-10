import json

import pytest

from esteira.pedidos import (
    Momento,
    _pessoa_citada,
    ajustar_tempos,
    gravar_pedidos,
    ler_pedidos,
    pessoas_do_glossario,
    validar_escolhas,
    validar_pedidos,
)


def test_valida_campos_por_tipo():
    m = [Momento(1, 3, "f", "foto", "A"), Momento(5, 7, "f", "noticia", "B", titulo="T"),
         Momento(9, 11, "f", "ia", "C"), Momento(13, 15, "f", "video", "D")]
    assert validar_pedidos(m, 60, []) == [
        "momento 1: foto sem busca", "momento 2: notícia sem veiculo",
        "momento 2: notícia sem data", "momento 3: ia sem prompt", "momento 4: tipo inválido 'video'"]


def test_tempo_fora_do_corte():
    assert validar_pedidos([Momento(58, 62, "f", "foto", "A", busca="x")], 60, []) == ["momento 1: fora do corte"]
    assert validar_pedidos([Momento(5, 5, "f", "foto", "A", busca="x")], 60, []) == ["momento 1: fora do corte"]


def test_prompt_com_pessoa_recusado():
    m = [Momento(1, 3, "f", "ia", "A", prompt="retrato de ayrton senna na chuva"),
         Momento(5, 7, "f", "ia", "B", prompt="carro igual ao do Hulkenberg"),
         Momento(9, 11, "f", "ia", "C", prompt="parque Lulalândia")]
    assert validar_pedidos(m, 60, ["Ayrton Senna", "Nico Hülkenberg", "Hülkenberg", "Lula"]) == [
        "momento 1: prompt cita pessoa real (Ayrton Senna)",
        "momento 2: prompt cita pessoa real (Hülkenberg)"]


@pytest.mark.parametrize("prompt", [
    "foto do Felipe  Massa na pista", "foto do Felipe\nMassa na pista", "foto do felipe\t  massa",
])
def test_pessoa_com_espacos_diferentes_no_prompt(prompt):
    assert _pessoa_citada(prompt, ["Felipe Massa"]) == "Felipe Massa"


def test_pessoa_com_espacos_diferentes_no_glossario():
    assert _pessoa_citada("foto do felipe massa", [" Felipe   Massa "]) == " Felipe   Massa "
    assert _pessoa_citada("foto do felipe massa", ["   "]) is None


def test_mensagens_do_painel_usam_tempo_e_nome():
    m = [Momento(75.4, 78, "f", "ia", "Sala"), Momento(5, 7, "f", "foto", "Ministro", busca="x", candidatas=[{}])]
    assert validar_pedidos(m, 60, [], painel=True) == [
        "1:15 Sala: IA sem prompt (escreva o prompt ou descarte o momento)", "1:15 Sala: fora do corte"]
    assert validar_escolhas(m, painel=True) == [
        "0:05 Ministro: nenhuma foto escolhida (escolha ao menos uma foto ou descarte o momento)"]
    m[1].escolhas = [2]
    assert validar_escolhas(m, painel=True) == ["0:05 Ministro: escolhas inválidas"]
    assert validar_escolhas(m) == ["momento 2: escolhas inválidas"]


def test_ajustar_tempos_no_painel_usa_o_tempo_de_antes_do_ajuste():
    m = [Momento(10, 13.9, "f", "foto", "A"), Momento(14.1, 14.4, "f", "foto", "B"), Momento(15.5, 18, "f", "foto", "C")]
    assert ajustar_tempos(m, 60, painel=True) == ["0:14 B descartado: não cabe em 2 s"]  # o tempo do cartão
    assert m[1].inicio == 13.9  # o ajuste tinha puxado o início para 0:13


def test_descartado_nao_e_validado():
    assert validar_pedidos([Momento(1, 3, "f", "video", "A", descartar=True)], 60, []) == []


def test_pessoas_do_glossario(tmp_path):
    (tmp_path / "g.md").write_text("# G\n\n## Canal\nTudo é Política\n\n## Pessoas citadas\nOs apresentadores também foram convidados do Por Trás do TCC.\n"
        "Lula, Messi\n\n## Pessoas do automobilismo\nMax Verstappen\n\n## Automobilismo\nFerrari\n", "utf-8")
    assert pessoas_do_glossario(tmp_path / "g.md") == ["Lula", "Messi", "Max Verstappen"]


def test_pessoas_do_glossario_ponto_final(tmp_path):
    (tmp_path / "g.md").write_text("## Pessoas citadas\nLula, Messi.\n", "utf-8")
    assert pessoas_do_glossario(tmp_path / "g.md") == ["Lula", "Messi"]


def test_proximo_mantido_ignora_descartado():
    m = [Momento(10, 18, "f", "foto", "A"), Momento(12, 12.5, "f", "foto", "B"), Momento(13.5, 14, "f", "foto", "C")]
    assert ajustar_tempos(m, 60) == ["momento 2 (B) descartado: não cabe em 2 s"]
    assert [(x.inicio, x.fim) for x in (m[0], m[2])] == [(10, 13.5), (13.5, 15.5)] and m[1].descartar


def test_estende_curto_para_frente():
    m = [Momento(10, 11, "f", "foto", "A")]
    assert ajustar_tempos(m, 60) == [] and (m[0].inicio, m[0].fim) == (10, 12)


def test_estende_para_tras_quando_encosta():
    m = [Momento(10, 11.5, "f", "foto", "A"), Momento(11.5, 14, "f", "foto", "B")]
    ajustar_tempos(m, 60); assert (m[0].inicio, m[0].fim) == (9.5, 11.5)


def test_corta_longo():
    m = [Momento(10, 18, "f", "foto", "A")]; ajustar_tempos(m, 60); assert m[0].fim == 15


def test_sem_espaco_descarta():
    m = [Momento(10, 12, "f", "foto", "A"), Momento(12, 13, "f", "foto", "B"), Momento(13, 15, "f", "foto", "C")]
    assert ajustar_tempos(m, 60) == ["momento 2 (B) descartado: não cabe em 2 s"]
    assert m[1].descartar and m[1].motivo == "não cabe em 2 s"


def test_fim_do_corte():
    m = [Momento(59, 59.5, "f", "foto", "A")]; ajustar_tempos(m, 60); assert (m[0].inicio, m[0].fim) == (58, 60)


def test_ida_e_volta_json(tmp_path):
    m = [Momento(1, 3, "f", "foto", "A", busca="x", candidatas=[{"titulo": "File:A.jpg"}], escolhas=[1],
                 url=["https://u/A.jpg"], bytes=[10])]
    gravar_pedidos(tmp_path, m); assert ler_pedidos(tmp_path) == m


def test_sobreposicao_limita_ao_proximo():
    m = [Momento(10, 15, "f", "foto", "A"), Momento(12, 16, "f", "foto", "B")]
    assert ajustar_tempos(m, 60) == [] and [(x.inicio, x.fim) for x in m] == [(10, 12), (12, 16)]


def test_sobreposicao_sem_espaco_descarta():
    m = [Momento(0, 5, "f", "foto", "A"), Momento(1, 6, "f", "foto", "B")]
    assert ajustar_tempos(m, 60) == ["momento 1 (A) descartado: não cabe em 2 s"]
    assert m[0].descartar and not m[1].descartar


def test_nome_vazio_apos_normalizar_e_ignorado():
    m = [Momento(1, 3, "f", "ia", "A", prompt="paisagem")]
    assert validar_pedidos(m, 60, ["李"]) == []


def _com_escolhas(escolhas):
    return [Momento(1, 3, "f", "foto", "A", busca="x", candidatas=[{"titulo": f"File:{i}.jpg"} for i in range(6)],
                    escolhas=escolhas)]


def test_escolhas_invalidas():
    for escolhas in ([0], [1, 1], [1, 2, 3, 4], [7], [], [True], [1.0]):
        assert validar_escolhas(_com_escolhas(escolhas)) == ["momento 1: escolhas inválidas"], escolhas
    assert validar_escolhas(_com_escolhas([2, 1])) == []


def test_escolhas_ignora_descartada_e_outros_tipos():
    m = [Momento(1, 3, "f", "foto", "A", busca="x", descartar=True), Momento(5, 7, "f", "ia", "B", prompt="p")]
    assert validar_escolhas(m) == []


def test_le_pedido_antigo_com_escolha(tmp_path):
    (tmp_path / "pedidos.json").write_text(
        '{"momentos": [{"inicio": 1, "fim": 3, "fala": "f", "tipo": "foto", "nome": "A", "escolha": 2, '
        '"numero": 1, "url": "https://u/x.jpg", "bytes": 10}]}', "utf-8")
    m = ler_pedidos(tmp_path)[0]
    assert (m.escolhas, m.url, m.bytes) == ([2], [], [])


def test_momento_aprovado_default_e_ida_e_volta(tmp_path):
    assert Momento(1.0, 2.0, "f", "ia", "n", prompt="p").aprovado is False
    (tmp_path / "pedidos.json").write_text(
        json.dumps({"momentos": [{"inicio": 1.0, "fim": 2.0, "fala": "f", "tipo": "ia", "nome": "n", "prompt": "p"}]}), "utf-8")
    antigo = ler_pedidos(tmp_path)
    assert antigo[0].aprovado is False
    antigo[0].aprovado = True
    gravar_pedidos(tmp_path, antigo)
    assert json.loads((tmp_path / "pedidos.json").read_text("utf-8"))["momentos"][0]["aprovado"] is True
    assert ler_pedidos(tmp_path)[0].aprovado is True
