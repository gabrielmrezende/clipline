from pathlib import Path

import pytest

from esteira import cli
from esteira.publicar import comandos, fila
from esteira.publicar.agendar import ErroAgendar
from esteira.publicar.fila import Item, gravar_fila, ler_fila
from esteira.publicar.tarefa import NOMES, comandos_schtasks

DATA = "2026-11-08T18:00:00-03:00"


@pytest.fixture(autouse=True)
def _sem_restricao(monkeypatch, tmp_path):
    monkeypatch.setattr(fila, "garantir_escrita", lambda caminho: caminho)
    monkeypatch.setattr(comandos, "TRAVA", tmp_path / "publicar.trava")


def test_agendar_sem_confirmar_nao_envia(tmp_path, monkeypatch, capsys):
    chamadas = []
    monkeypatch.setattr(comandos, "preparar_pedido", lambda *a: "PEDIDO")
    monkeypatch.setattr(comandos, "resumo", lambda pedido, modos: "RESUMO DO CORTE")
    monkeypatch.setattr(comandos, "confirmar", lambda *a: chamadas.append(a))
    codigo = cli.principal(["publicar", "agendar", str(tmp_path), "--numero", "1", "--data", "2026-11-08 18:00"])
    saida = capsys.readouterr().out
    assert codigo == 0 and chamadas == []
    assert "RESUMO DO CORTE" in saida
    assert saida.strip().endswith("Nada foi enviado. Para confirmar, rode de novo com --confirmar.")


def test_agendar_passa_redes(tmp_path, monkeypatch):
    vistos = []
    monkeypatch.setattr(comandos, "preparar_pedido", lambda pasta, numero, data, redes, agora: vistos.append(redes) or "P")
    monkeypatch.setattr(comandos, "resumo", lambda pedido, modos: "")
    cli.principal(["publicar", "agendar", str(tmp_path), "--numero", "1", "--data", "x", "--redes", "youtube,tiktok"])
    assert vistos == [["youtube", "tiktok"]]


def test_agendar_com_confirmar(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(comandos, "preparar_pedido", lambda *a: "PEDIDO")
    monkeypatch.setattr(comandos, "_redes_reais", lambda: {"youtube": object()})
    monkeypatch.setattr(comandos, "confirmar", lambda pedido, modos, redes: [
        Item(1, "youtube", DATA, "privado", link="https://youtube.com/shorts/abc"), Item(1, "instagram", DATA)])
    codigo = cli.principal(["publicar", "agendar", str(tmp_path), "--numero", "1", "--data", "x", "--confirmar"])
    saida = capsys.readouterr().out
    assert codigo == 0
    assert "01 youtube: privado https://youtube.com/shorts/abc" in saida
    assert "01 instagram: agendado" in saida


def test_agendar_erro_devolve_1(tmp_path, monkeypatch, capsys):
    def falha(*a):
        raise ErroAgendar("data no passado")
    monkeypatch.setattr(comandos, "preparar_pedido", falha)
    assert cli.principal(["publicar", "agendar", str(tmp_path), "--numero", "1", "--data", "x"]) == 1
    assert "Erro: data no passado" in capsys.readouterr().err


def test_fila_lista_sem_cancelados(tmp_path, monkeypatch, capsys):
    ep = tmp_path / "Ep 1"
    ep.mkdir()
    gravar_fila(ep, [Item(1, "youtube", DATA, "privado", link="L"), Item(2, "tiktok", DATA, "cancelado")])
    monkeypatch.setattr(comandos, "CORTES", tmp_path)
    assert cli.principal(["publicar", "fila"]) == 0
    saida = capsys.readouterr().out
    assert "Ep 1" in saida and "01 youtube" in saida and "08/11 18:00" in saida and "privado" in saida
    assert "tiktok" not in saida


def test_cancelar_agendado(tmp_path, capsys):
    gravar_fila(tmp_path, [Item(1, "instagram", DATA), Item(1, "tiktok", DATA)])
    assert cli.principal(["publicar", "cancelar", str(tmp_path), "--numero", "1", "--redes", "instagram"]) == 0
    assert [i.estado for i in ler_fila(tmp_path)] == ["cancelado", "agendado"]


def test_cancelar_youtube_ja_enviado_avisa(tmp_path, capsys):
    gravar_fila(tmp_path, [Item(1, "youtube", DATA, "privado")])
    cli.principal(["publicar", "cancelar", str(tmp_path), "--numero", "1"])
    assert "youtube já enviado: apague no Studio se quiser" in capsys.readouterr().out
    assert ler_fila(tmp_path)[0].estado == "privado"


def test_marcar_feito_e_reenviar(tmp_path):
    gravar_fila(tmp_path, [Item(1, "instagram", DATA, "conferir", 1, "", "", "x"), Item(1, "tiktok", DATA, "conferir", 2)])
    assert cli.principal(["publicar", "marcar", str(tmp_path), "--numero", "1", "--rede", "instagram", "feito"]) == 0
    assert cli.principal(["publicar", "marcar", str(tmp_path), "--numero", "1", "--rede", "tiktok", "reenviar"]) == 0
    instagram, tiktok = ler_fila(tmp_path)
    assert (instagram.estado, instagram.erro) == ("publicado", "")
    assert (tiktok.estado, tiktok.tentativas) == ("agendado", 0)


def test_marcar_so_em_conferir(tmp_path, capsys):
    gravar_fila(tmp_path, [Item(1, "instagram", DATA)])
    assert cli.principal(["publicar", "marcar", str(tmp_path), "--numero", "1", "--rede", "instagram", "feito"]) == 1
    assert "não está em conferir" in capsys.readouterr().err


def test_rodar_imprime_relato(monkeypatch, capsys):
    monkeypatch.setattr(comandos, "rodar_tudo", lambda: ["01 instagram: publicado L"])
    assert cli.principal(["publicar", "rodar"]) == 0
    assert "01 instagram: publicado L" in capsys.readouterr().out


def test_comandos_schtasks():
    c = comandos_schtasks(Path("C:/A/.venv/Scripts/python.exe"), Path("C:/A"))
    assert c[0][:9] == ["schtasks", "/Create", "/F", "/TN", "Tudo é Política - publicar", "/SC", "MINUTE", "/MO", "15"]
    assert c[1][:7] == ["schtasks", "/Create", "/F", "/TN", NOMES[1], "/SC", "ONLOGON"]
    assert c[0][-1].endswith("-m esteira publicar rodar >> logs\\publicar.log 2>&1")
    assert c[0][-1].startswith('cmd /c cd /d "C:')


def test_instalar_sem_confirmar_so_mostra(monkeypatch, capsys):
    chamadas = []
    monkeypatch.setattr(comandos.subprocess, "run", lambda *a, **k: chamadas.append(a))
    assert cli.principal(["publicar", "instalar-tarefa"]) == 0
    assert chamadas == []
    assert "schtasks" in capsys.readouterr().out


def test_instalar_com_confirmar_roda_dois(monkeypatch, tmp_path):
    chamadas = []
    monkeypatch.setattr(comandos, "AUTOMACAO", tmp_path)
    monkeypatch.setattr(comandos.subprocess, "run", lambda comando, **k: chamadas.append(comando))
    assert cli.principal(["publicar", "instalar-tarefa", "--confirmar"]) == 0
    assert len(chamadas) == 2 and (tmp_path / "logs").is_dir()


def test_cancelar_com_rodar_em_andamento_recusa(tmp_path, capsys):
    gravar_fila(tmp_path, [Item(1, "instagram", DATA)])
    with fila.trava(comandos.TRAVA):
        assert cli.principal(["publicar", "cancelar", str(tmp_path), "--numero", "1"]) == 1
    assert "outra execução em andamento" in capsys.readouterr().err
    assert ler_fila(tmp_path)[0].estado == "agendado"


def test_confirmar_pega_a_trava(tmp_path, monkeypatch):
    vistos = []
    monkeypatch.setattr(comandos, "preparar_pedido", lambda *a: "PEDIDO")
    monkeypatch.setattr(comandos, "_redes_reais", lambda: {})
    monkeypatch.setattr(comandos, "confirmar", lambda *a: vistos.append(comandos.TRAVA.exists()) or [])
    cli.principal(["publicar", "agendar", str(tmp_path), "--numero", "1", "--data", "x", "--confirmar"])
    assert vistos == [True]


def test_youtube_que_nao_saiu_devolve_1(tmp_path, monkeypatch):
    monkeypatch.setattr(comandos, "preparar_pedido", lambda *a: "PEDIDO")
    monkeypatch.setattr(comandos, "_redes_reais", lambda: {})
    monkeypatch.setattr(comandos, "confirmar", lambda *a: [Item(1, "youtube", DATA, "agendado", 1, erro="HTTP 503")])
    assert cli.principal(["publicar", "agendar", str(tmp_path), "--numero", "1", "--data", "x", "--confirmar"]) == 1


def test_modo_invalido_sem_traceback(tmp_path, monkeypatch, capsys):
    def ruim(*a):
        raise ValueError("publicacao.json: modo 'x' inválido para tiktok")
    monkeypatch.setattr(comandos, "preparar_pedido", lambda *a: "PEDIDO")
    monkeypatch.setattr(comandos, "ler_modos", ruim)
    assert cli.principal(["publicar", "agendar", str(tmp_path), "--numero", "1", "--data", "x"]) == 1
    assert "Erro: publicacao.json" in capsys.readouterr().err


def test_fila_corrompida_sem_traceback(tmp_path, capsys):
    (tmp_path / "postagens.json").write_text("{quebrado", "utf-8")
    assert cli.principal(["publicar", "fila", str(tmp_path)]) == 1
    assert "Erro:" in capsys.readouterr().err
