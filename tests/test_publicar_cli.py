from pathlib import Path

import pytest

from esteira import cli
from esteira.config import Config
from esteira.publicar import agendador, comandos, fila, registro
from esteira.publicar.agendador import Execucao
from esteira.publicar.agendar import ErroAgendar
from esteira.publicar.fila import Item, gravar_fila, ler_fila
from esteira.publicar.tarefa import NOMES, comandos_schtasks

DATA = "2026-11-08T18:00:00-03:00"


class Sistema:
    """Faz o papel do sistema operacional: registra os comandos e responde o código combinado."""

    def __init__(self, codigos=None, saidas=None):
        self.codigos, self.saidas, self.comandos = dict(codigos or {}), dict(saidas or {}), []

    def __call__(self, comando, entrada=None):
        self.comandos.append((comando, entrada))
        chave = " ".join(comando[:2])
        return Execucao(self.codigos.get(chave, 0), self.saidas.get(chave, ""))


@pytest.fixture(autouse=True)
def _sem_restricao(monkeypatch, tmp_path):
    monkeypatch.setattr(fila, "garantir_escrita", lambda caminho: caminho)
    monkeypatch.setattr(comandos, "TRAVA", tmp_path / "publicar.trava")
    monkeypatch.setattr(registro, "LOG", tmp_path / "logs" / "publicar.log")
    monkeypatch.setattr(comandos, "EXECUTAR", Sistema())  # nenhum teste roda comando de verdade
    monkeypatch.setattr(comandos, "CASA", tmp_path / "casa")
    monkeypatch.setattr(comandos.config, "ler", lambda: Config())


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


def test_rodar_grava_o_log_com_data_e_hora(monkeypatch):
    monkeypatch.setattr(comandos, "rodar_tudo", lambda: ["01 instagram: publicado L", "02 tiktok: rascunho"])
    assert cli.principal(["publicar", "rodar"]) == 0
    linhas = registro.LOG.read_text("utf-8").splitlines()
    assert [linha[20:] for linha in linhas] == ["01 instagram: publicado L", "02 tiktok: rascunho"]
    assert all(linha[4] == "-" and linha[13] == ":" for linha in linhas)  # 2026-11-08 18:00:00 ...


def test_rodar_sem_nada_a_fazer_nao_suja_o_log(monkeypatch):
    monkeypatch.setattr(comandos, "rodar_tudo", lambda: [])
    assert cli.principal(["publicar", "rodar"]) == 0
    assert registro.LOG.read_text("utf-8") == ""


def test_rodar_com_erro_deixa_o_erro_no_log(monkeypatch, capsys):
    def quebra():
        raise ValueError("publicacao.json: modo 'x' inválido para tiktok")
    monkeypatch.setattr(comandos, "rodar_tudo", quebra)
    assert cli.principal(["publicar", "rodar"]) == 1
    assert "erro: publicacao.json: modo 'x' inválido" in registro.LOG.read_text("utf-8")
    assert "Erro: publicacao.json" in capsys.readouterr().err


def test_rodar_pela_tarefa_antiga_escreve_so_pela_saida_e_pede_reinstalar(monkeypatch):
    """A tarefa antiga (>> logs\\publicar.log) já manda a saída para o log: um escritor só, e o aviso."""
    registro.LOG.parent.mkdir(parents=True)
    monkeypatch.setattr(comandos, "rodar_tudo", lambda: ["01 instagram: publicado L"])
    with open(registro.LOG, "a", encoding="utf-8") as saida_do_cmd:
        monkeypatch.setattr(registro.sys, "stdout", saida_do_cmd)
        assert cli.principal(["publicar", "rodar"]) == 0
    texto = registro.LOG.read_text("utf-8")
    assert texto.count("01 instagram: publicado L") == 1
    assert "reinstale com publicar instalar-tarefa --confirmar" in texto


def test_comandos_schtasks():
    c = comandos_schtasks(Path("C:/A/.venv/Scripts/python.exe"), Path("C:/A"))
    assert c[0][:9] == ["schtasks", "/Create", "/F", "/TN", "Tudo é Política - publicar", "/SC", "MINUTE", "/MO", "15"]
    assert c[1][:7] == ["schtasks", "/Create", "/F", "/TN", NOMES[1], "/SC", "ONLOGON"]
    # o log agora é gravado pelo próprio publicar rodar, com rotação: a linha não redireciona mais
    assert c[0][-1].endswith("-m esteira publicar rodar")
    assert c[0][-1].startswith('cmd /c cd /d "C:')
    assert ">>" not in c[0][-1] and c[0][-1] == c[1][-1]


def test_instalar_sem_confirmar_so_mostra(monkeypatch, capsys):
    monkeypatch.setattr(agendador, "sistema_atual", lambda: "windows")
    assert cli.principal(["publicar", "instalar-tarefa"]) == 0
    assert comandos.EXECUTAR.comandos == []
    saida = capsys.readouterr().out
    assert saida.startswith("Vou criar estas tarefas no Agendador do Windows:\n")
    assert saida.count("schtasks /Create /F /TN") == 2
    assert '"Tudo é Política - publicar ao entrar"' in saida
    assert saida.strip().endswith("Nada foi criado. Para confirmar, rode de novo com --confirmar.")


def test_instalar_com_confirmar_roda_dois(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(agendador, "sistema_atual", lambda: "windows")
    monkeypatch.setattr(comandos, "AUTOMACAO", tmp_path)
    assert cli.principal(["publicar", "instalar-tarefa", "--confirmar"]) == 0
    feitos = [c for c, _ in comandos.EXECUTAR.comandos]
    assert [c[:5] for c in feitos] == [["schtasks", "/Create", "/F", "/TN", NOMES[0]],
                                       ["schtasks", "/Create", "/F", "/TN", NOMES[1]]]
    assert (tmp_path / "logs").is_dir()
    assert capsys.readouterr().out.strip() == "Tarefas criadas."


def test_instalar_com_schtasks_falhando_devolve_1(monkeypatch, capsys):
    monkeypatch.setattr(agendador, "sistema_atual", lambda: "windows")
    falha = Sistema({"schtasks /Create": 1}, {"schtasks /Create": "ERRO: acesso negado."})
    monkeypatch.setattr(comandos, "EXECUTAR", falha)
    assert cli.principal(["publicar", "instalar-tarefa", "--confirmar"]) == 1
    assert "Erro: schtasks falhou (código 1): ERRO: acesso negado." in capsys.readouterr().err


def test_nomes_seguem_o_canal_do_clipline_toml(monkeypatch, capsys):
    monkeypatch.setattr(agendador, "sistema_atual", lambda: "windows")
    monkeypatch.setattr(comandos.config, "ler", lambda: Config(canal="Outro Canal"))
    cli.principal(["publicar", "instalar-tarefa"])
    saida = capsys.readouterr().out
    assert '"Outro Canal - publicar"' in saida and "Tudo é Política" not in saida


def test_instalar_no_linux_com_systemd(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(agendador, "sistema_atual", lambda: "linux")
    assert cli.principal(["publicar", "instalar-tarefa", "--confirmar"]) == 0
    pasta = tmp_path / "casa" / ".config" / "systemd" / "user"
    nomes = sorted(p.name for p in pasta.iterdir())
    assert nomes == ["tudo-e-politica-publicar.service", "tudo-e-politica-publicar.timer"]
    assert [c for c, _ in comandos.EXECUTAR.comandos] == [
        ["systemctl", "--user", "show-environment"],
        ["systemctl", "--user", "daemon-reload"],
        ["systemctl", "--user", "enable", "--now", "tudo-e-politica-publicar.timer"],
    ]
    assert "Tarefa criada no systemd do usuário (timer)." in capsys.readouterr().out


def test_desinstalar_sem_confirmar_so_mostra(monkeypatch, capsys):
    monkeypatch.setattr(agendador, "sistema_atual", lambda: "windows")
    assert cli.principal(["publicar", "desinstalar-tarefa"]) == 0
    assert comandos.EXECUTAR.comandos == []
    saida = capsys.readouterr().out
    assert saida.count("schtasks /Delete /F /TN") == 2
    assert saida.strip().endswith("Nada foi removido. Para confirmar, rode de novo com --confirmar.")


def test_desinstalar_tarefa_que_nao_existe_so_avisa(monkeypatch, capsys):
    monkeypatch.setattr(agendador, "sistema_atual", lambda: "windows")
    monkeypatch.setattr(comandos, "EXECUTAR", Sistema({"schtasks /Delete": 1}))
    assert cli.principal(["publicar", "desinstalar-tarefa", "--confirmar"]) == 0
    saida = capsys.readouterr().out
    assert saida.count("aviso: schtasks falhou (código 1)") == 2
    assert "Tarefa removida no Agendador do Windows." in saida


def test_conectar_youtube_com_playlist(monkeypatch):
    from esteira.publicar import youtube
    vistos = []
    monkeypatch.setattr(youtube, "conectar", lambda playlist=False: vistos.append(playlist))
    assert cli.principal(["publicar", "conectar", "youtube", "--playlist"]) == 0
    assert cli.principal(["publicar", "conectar", "youtube"]) == 0
    assert vistos == [True, False]


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
