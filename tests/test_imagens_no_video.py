import json

from PIL import Image

from esteira.imagens_no_video import escolhas_do_corte, imagens_do_corte
from esteira.pedidos import Momento, gravar_pedidos, ler_pedidos
from esteira.planos import Plano
from esteira.receita import ImagemNoVideo, Receita, gravar_receita

CANDIDATAS = [
    {"titulo": f"File:A{i}.jpg", "pagina": f"https://c/A{i}", "autor": "Fulano", "licenca": "CC BY-SA 4.0"}
    for i in (1, 2, 3)
]


def _corte(tmp_path, momentos, duracao=60.0):
    corte = tmp_path / "Tudo é Política" / "01-corte"
    (corte / "trabalho").mkdir(parents=True)
    (corte / "imagens-sugeridas").mkdir()
    gravar_receita(corte / "trabalho", Receita([(0.0, duracao)], [Plano(0.0, duracao)], []))
    gravar_pedidos(corte / "trabalho", momentos)
    return corte


def _foto(inicio=12.0, fim=15.0, escolhas=(1, 2), **extra):
    return Momento(inicio, fim, "a placa", "foto", "Placa", busca="placa", candidatas=CANDIDATAS,
                   escolhas=list(escolhas), **extra)


def _ia(inicio=30.0, fim=33.0, **extra):
    return Momento(inicio, fim, "chovia", "ia", "Chuva", prompt="chuva numa pista", aprovado=True, **extra)


def _noticia(inicio=40.0, fim=43.0):
    return Momento(inicio, fim, "saiu no jornal", "noticia", "Manchete", titulo="T", veiculo="Folha", data="2026-01-02")


def _gravada(corte, nome, credito=None):
    """Um arquivo que a própria esteira gravou (sugeridas.json e, nas fotos, creditos.json)."""
    trabalho = corte / "trabalho"
    Image.new("RGB", (1080, 1920)).save(corte / "imagens-sugeridas" / nome)
    sugeridas = trabalho / "sugeridas.json"
    lista = json.loads(sugeridas.read_text("utf-8")) if sugeridas.exists() else []
    sugeridas.write_text(json.dumps(lista + [nome]), "utf-8")
    if credito is not None:
        creditos = trabalho / "creditos.json"
        dados = json.loads(creditos.read_text("utf-8")) if creditos.exists() else {}
        dados[nome] = credito
        creditos.write_text(json.dumps(dados), "utf-8")


def _gerada(corte, chave, versao):
    nome = f"{chave}-ia-{versao}.jpg"
    Image.new("RGB", (1080, 1920)).save(corte / "imagens-sugeridas" / nome)
    ia = corte / "trabalho" / "ia.json"
    lista = json.loads(ia.read_text("utf-8")) if ia.exists() else []
    lista.append({"arquivo": nome, "momento": chave, "versao": versao, "provedor": "openai", "data": "2026-11-09T10:00:00"})
    ia.write_text(json.dumps(lista), "utf-8")
    return nome


def _mtime(corte, nome):
    return (corte / "imagens-sugeridas" / nome).stat().st_mtime_ns


def test_foto_entra_a_primeira_opcao_pronta(tmp_path):
    corte = _corte(tmp_path, [_foto()])
    _gravada(corte, "0012-placa-2.jpg", CANDIDATAS[1])  # a opção 1 falhou no download
    credito = {campo: CANDIDATAS[1][campo] for campo in ("autor", "licenca", "pagina", "titulo")}
    assert imagens_do_corte(corte) == (
        [ImagemNoVideo(12.0, 15.0, "imagens-sugeridas/0012-placa-2.jpg", "foto", "0012-placa",
                       _mtime(corte, "0012-placa-2.jpg"), credito)],
        [],
    )
    _gravada(corte, "0012-placa-1.jpg", CANDIDATAS[0])
    assert imagens_do_corte(corte)[0][0].arquivo == "imagens-sugeridas/0012-placa-1.jpg"


def test_foto_baixada_de_outra_candidata_nao_conta(tmp_path):
    corte = _corte(tmp_path, [_foto(escolhas=(3,))])
    _gravada(corte, "0012-placa-1.jpg", CANDIDATAS[0])  # baixada quando a escolha 1 era a candidata 1
    lista, alertas = imagens_do_corte(corte)
    assert lista == [] and alertas == ["imagem 0:12 Placa fora do vídeo: foto não baixada"]


def test_ia_entra_a_versao_mais_nova(tmp_path):
    corte = _corte(tmp_path, [_ia()])
    _gerada(corte, "0030-chuva", 1)
    _gerada(corte, "0030-chuva", 2)
    lista, alertas = imagens_do_corte(corte)
    assert [i.arquivo for i in lista] == ["imagens-sugeridas/0030-chuva-ia-2.jpg"] and lista[0].tipo == "ia"
    assert alertas == []


def test_noticia_entra_o_cartao(tmp_path):
    corte = _corte(tmp_path, [_noticia()])
    _gravada(corte, "0040-manchete.png")
    assert [i.arquivo for i in imagens_do_corte(corte)[0]] == ["imagens-sugeridas/0040-manchete.png"]


def test_no_video_valido_manda(tmp_path):
    corte = _corte(tmp_path, [_ia(no_video="0030-chuva-ia-1.jpg")])
    _gerada(corte, "0030-chuva", 1)
    _gerada(corte, "0030-chuva", 2)
    lista, alertas = imagens_do_corte(corte)
    assert [i.arquivo for i in lista] == ["imagens-sugeridas/0030-chuva-ia-1.jpg"] and alertas == []


def test_no_video_vencido_entra_o_padrao_com_alerta(tmp_path):
    corte = _corte(tmp_path, [_foto(no_video="0012-placa-3.jpg")])
    _gravada(corte, "0012-placa-1.jpg", CANDIDATAS[0])
    _gravada(corte, "0012-placa-2.jpg", CANDIDATAS[1])
    lista, alertas = imagens_do_corte(corte)
    assert [i.arquivo for i in lista] == ["imagens-sugeridas/0012-placa-1.jpg"]
    assert alertas == ["imagem 0:12 Placa: 0012-placa-3.jpg não está pronta, entrou 0012-placa-1.jpg"]


def test_momento_sem_imagem_fica_de_fora_com_motivo(tmp_path):
    corte = _corte(tmp_path, [_foto(), _ia(), _noticia()])
    lista, alertas = imagens_do_corte(corte)
    assert lista == []
    assert alertas == [
        "imagem 0:12 Placa fora do vídeo: foto não baixada",
        "imagem 0:30 Chuva fora do vídeo: IA ainda não gerada",
        "imagem 0:40 Manchete fora do vídeo: cartão não gerado",
    ]


def test_descartado_pelo_dono_nao_entra_nem_alerta(tmp_path):
    corte = _corte(tmp_path, [_foto(descartar=True)])
    _gravada(corte, "0012-placa-1.jpg", CANDIDATAS[0])
    assert imagens_do_corte(corte) == ([], [])


def test_descartado_pelo_ajuste_alerta(tmp_path):
    antes = _noticia(10.0, 12.0)
    corte = _corte(tmp_path, [antes, _foto(12.0, 12.5, escolhas=(1,)), _noticia(13.0, 16.0)])
    _gravada(corte, "0012-placa-1.jpg", CANDIDATAS[0])
    lista, alertas = imagens_do_corte(corte)
    assert "imagem 0:12 Placa fora do vídeo: não cabe em 2 s" in alertas
    assert all("placa" not in i.arquivo for i in lista)


def test_tempo_de_tela_e_o_ajustado(tmp_path):
    corte = _corte(tmp_path, [_foto(12.0, 12.5, escolhas=(1,))])
    _gravada(corte, "0012-placa-1.jpg", CANDIDATAS[0])
    lista, _ = imagens_do_corte(corte)
    assert (lista[0].inicio, lista[0].fim) == (12.0, 14.0)
    escolha = escolhas_do_corte(corte, ler_pedidos(corte / "trabalho"), 60.0)[0]
    assert (escolha.inicio_tela, escolha.fim_tela, escolha.chave) == (12.0, 14.0, "0012-placa")
    assert escolha.prontas == ["0012-placa-1.jpg"] and escolha.arquivo == "0012-placa-1.jpg"


def test_lista_em_ordem_de_tempo(tmp_path):
    corte = _corte(tmp_path, [_ia(), _foto(escolhas=(1,))])
    _gerada(corte, "0030-chuva", 1)
    _gravada(corte, "0012-placa-1.jpg", CANDIDATAS[0])
    assert [i.momento for i in imagens_do_corte(corte)[0]] == ["0012-placa", "0030-chuva"]


def test_sem_duracao_nao_ajusta(tmp_path):
    corte = _corte(tmp_path, [_foto(12.0, 12.5, escolhas=(1,))])
    escolha = escolhas_do_corte(corte, ler_pedidos(corte / "trabalho"), None)[0]
    assert (escolha.inicio_tela, escolha.fim_tela) == (12.0, 12.5)


def test_sem_pedidos_lista_vazia_sem_alerta(tmp_path):
    corte = _corte(tmp_path, [])
    (corte / "trabalho" / "pedidos.json").unlink()
    assert imagens_do_corte(corte) == ([], [])


def test_pedidos_ilegivel_lista_vazia_com_alerta(tmp_path):
    corte = _corte(tmp_path, [])
    (corte / "trabalho" / "pedidos.json").write_text("{quebrado", "utf-8")
    lista, alertas = imagens_do_corte(corte)
    assert lista == [] and len(alertas) == 1 and alertas[0].startswith("imagens: pedidos.json ilegível:")


def _registro(corte, imagens=None, resultado="ok"):
    dados = {"resultado": resultado, "alertas": []}
    if imagens is not None:
        dados["imagens"] = imagens
    (corte / "trabalho" / "registro.json").write_text(json.dumps(dados), "utf-8")


def test_montagem_desatualizada(tmp_path):
    from dataclasses import asdict

    from esteira.imagens_no_video import montagem_desatualizada, no_corte

    corte = _corte(tmp_path, [_foto(escolhas=(1,))])
    _gravada(corte, "0012-placa-1.jpg", CANDIDATAS[0])
    previstas = [asdict(i) for i in imagens_do_corte(corte)[0]]
    _registro(corte, [])
    assert not montagem_desatualizada(corte)  # sem corte.mp4 não há o que comparar
    (corte / "corte.mp4").write_bytes(b"")
    assert montagem_desatualizada(corte)
    _registro(corte, previstas)
    assert not montagem_desatualizada(corte) and no_corte(corte) == previstas
    _registro(corte, previstas, resultado="erro: x")
    assert no_corte(corte) == []
    (corte / "trabalho" / "registro.json").write_text("{quebrado", "utf-8")
    assert no_corte(corte) == [] and montagem_desatualizada(corte)


def test_corte_antigo_sem_imagens_no_registro_e_nada_pronto_nao_esta_desatualizado(tmp_path):
    from esteira.imagens_no_video import montagem_desatualizada

    corte = _corte(tmp_path, [_foto()])
    (corte / "corte.mp4").write_bytes(b"")
    _registro(corte)
    assert not montagem_desatualizada(corte)


def test_foto_sem_creditos_json_leva_o_credito_da_candidata_escolhida(tmp_path):
    corte = _corte(tmp_path, [_foto(escolhas=(3,), resumidas=[3])])  # corte antigo, sem creditos.json
    _gravada(corte, "0012-placa-1.jpg")
    assert imagens_do_corte(corte)[0][0].credito == {
        "autor": "Fulano", "licenca": "CC BY-SA 4.0", "pagina": "https://c/A3", "titulo": "File:A3.jpg"}


def test_ia_e_noticia_nao_levam_credito(tmp_path):
    corte = _corte(tmp_path, [_ia(), _noticia()])
    _gerada(corte, "0030-chuva", 1)
    _gravada(corte, "0040-manchete.png")
    assert [i.credito for i in imagens_do_corte(corte)[0]] == [None, None]
