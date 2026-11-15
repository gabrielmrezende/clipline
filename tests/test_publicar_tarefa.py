"""Tarefa agendada em cada sistema: os arquivos e os comandos gerados, sem rodar nada no sistema."""
import plistlib
from pathlib import Path, PurePosixPath

import pytest

from esteira.publicar import agendador, tarefa
from esteira.publicar.agendador import (
    ErroTarefa,
    Execucao,
    aplicar,
    descrever,
    plano_desinstalar,
    plano_instalar,
    situacao,
)

PYTHON = PurePosixPath("/home/ana/clipline/Automacao/.venv/bin/python")
AUTOMACAO = PurePosixPath("/home/ana/clipline/Automacao")


class Sistema:
    def __init__(self, respostas=None):
        self.respostas = dict(respostas or {})  # "programa arg1" -> Execucao
        self.comandos = []

    def __call__(self, comando, entrada=None):
        self.comandos.append((comando, entrada))
        return self.respostas.get(" ".join(comando[:2]), Execucao(0))


SEM_SYSTEMD = {"systemctl --user": Execucao(1, "Failed to connect to bus")}


# --- nomes ------------------------------------------------------------------------------------------------


def test_nomes_padrao_sao_os_de_sempre():
    assert tarefa.nomes("Tudo é Política") == ("Tudo é Política - publicar", "Tudo é Política - publicar ao entrar")
    assert tarefa.NOMES == tarefa.nomes()


def test_nomes_de_outro_canal_sem_caracteres_proibidos_no_windows():
    assert tarefa.nomes('Canal: A/B "x"') == ("Canal- A-B -x- - publicar", "Canal- A-B -x- - publicar ao entrar")
    assert tarefa.nomes("   ")[0] == "clipline - publicar"


def test_apelido_sem_acento_para_arquivos_e_unidades():
    assert tarefa.apelido("Tudo é Política") == "tudo-e-politica"
    assert tarefa.apelido("Canal 2.0 (BR)!") == "canal-2-0-br"
    assert tarefa.apelido("🎙️") == "clipline"


# --- Windows ----------------------------------------------------------------------------------------------


def test_windows_sem_redirecionar_o_log_e_com_os_nomes_de_sempre():
    plano = plano_instalar("windows", Path("C:/A/py.exe"), Path("C:/A"), "Tudo é Política", Path("C:/casa"), Sistema())
    linha = tarefa.linha_windows(Path("C:/A/py.exe"), Path("C:/A"))
    assert [p.comando for p in plano.passos] == [
        ["schtasks", "/Create", "/F", "/TN", "Tudo é Política - publicar", "/SC", "MINUTE", "/MO", "15", "/TR", linha],
        ["schtasks", "/Create", "/F", "/TN", "Tudo é Política - publicar ao entrar", "/SC", "ONLOGON", "/TR", linha],
    ]
    assert "publicar.log" not in linha


def test_windows_desinstalar_tolera_tarefa_que_nao_existe():
    plano = plano_desinstalar("windows", "Tudo é Política", Path("C:/casa"), Sistema())
    assert [p.comando for p in plano.passos] == [
        ["schtasks", "/Delete", "/F", "/TN", "Tudo é Política - publicar"],
        ["schtasks", "/Delete", "/F", "/TN", "Tudo é Política - publicar ao entrar"],
    ]
    avisos = aplicar(plano, Sistema({"schtasks /Delete": Execucao(1, "ERRO: o sistema não pode encontrar")}))
    assert len(avisos) == 2 and avisos[0].startswith("aviso: schtasks falhou (código 1): ERRO")


def test_windows_descrever_mostra_como_sempre():
    plano = plano_instalar("windows", Path("C:/A/py.exe"), Path("C:/A"), "Tudo é Política", Path("C:/casa"), Sistema())
    linhas = descrever(plano)
    assert linhas[0].startswith('schtasks /Create /F /TN "Tudo é Política - publicar" /SC MINUTE /MO 15 /TR ')


# --- Linux: systemd ---------------------------------------------------------------------------------------


def test_systemd_unidades():
    arquivos = tarefa.arquivos_systemd(PYTHON, AUTOMACAO, "Tudo é Política")
    servico = arquivos["tudo-e-politica-publicar.service"]
    timer = arquivos["tudo-e-politica-publicar.timer"]
    assert "Type=oneshot\n" in servico
    assert "WorkingDirectory=/home/ana/clipline/Automacao\n" in servico
    assert 'ExecStart="/home/ana/clipline/Automacao/.venv/bin/python" -m esteira publicar rodar\n' in servico
    assert ">>" not in servico
    assert "OnActiveSec=1min\n" in timer and "OnUnitActiveSec=15min\n" in timer
    assert "Unit=tudo-e-politica-publicar.service\n" in timer
    assert "WantedBy=timers.target\n" in timer


def test_systemd_escapa_porcentagem_aspas_e_espacos():
    arquivos = tarefa.arquivos_systemd(PurePosixPath('/opt/a 100% "b"/py'), PurePosixPath("/opt/50%"), "Canal")
    servico = arquivos["canal-publicar.service"]
    assert "WorkingDirectory=/opt/50%%\n" in servico
    assert 'ExecStart="/opt/a 100%% \\"b\\"/py" -m esteira' in servico


def test_systemd_plano_instalar_grava_na_casa_e_liga_o_timer(tmp_path):
    sistema = Sistema()
    plano = plano_instalar("linux", PYTHON, AUTOMACAO, "Tudo é Política", tmp_path, sistema)
    assert plano.sistema == "systemd"
    assert aplicar(plano, sistema) == []
    pasta = tmp_path / ".config" / "systemd" / "user"
    servico = (pasta / "tudo-e-politica-publicar.service").read_bytes()
    assert b"\r\n" not in servico and b"ExecStart=" in servico
    assert (pasta / "tudo-e-politica-publicar.timer").is_file()
    assert [c for c, _ in sistema.comandos] == [
        ["systemctl", "--user", "show-environment"],
        ["systemctl", "--user", "daemon-reload"],
        ["systemctl", "--user", "enable", "--now", "tudo-e-politica-publicar.timer"],
    ]


def test_systemd_desinstalar(tmp_path):
    sistema = Sistema()
    aplicar(plano_instalar("linux", PYTHON, AUTOMACAO, "Tudo é Política", tmp_path, sistema), sistema)
    sistema.comandos.clear()
    aplicar(plano_desinstalar("linux", "Tudo é Política", tmp_path, sistema), sistema)
    assert list((tmp_path / ".config" / "systemd" / "user").iterdir()) == []
    assert [c for c, _ in sistema.comandos] == [
        ["systemctl", "--user", "show-environment"],
        ["systemctl", "--user", "disable", "--now", "tudo-e-politica-publicar.timer"],
        ["systemctl", "--user", "daemon-reload"],
    ]


def test_systemd_falha_ao_ligar_para_tudo(tmp_path):
    sistema = Sistema({"systemctl --user": Execucao(0)})
    plano = plano_instalar("linux", PYTHON, AUTOMACAO, "Tudo é Política", tmp_path, sistema)
    falha = Sistema({"systemctl --user": Execucao(1, "Unit not found")})
    with pytest.raises(ErroTarefa, match=r"systemctl falhou \(código 1\): Unit not found"):
        aplicar(plano, falha)


# --- Linux: cron ------------------------------------------------------------------------------------------


def test_cron_quando_nao_ha_systemd_do_usuario():
    atual = "MAILTO=ana\n0 3 * * * backup.sh\n"
    sistema = Sistema({**SEM_SYSTEMD, "crontab -l": Execucao(0, atual)})
    plano = plano_instalar("linux", PYTHON, AUTOMACAO, "Tudo é Política", Path("/casa"), sistema)
    assert plano.sistema == "cron"
    [passo] = plano.passos
    assert passo.comando == ["crontab", "-"]
    linhas = passo.entrada.splitlines()
    assert linhas[:2] == ["MAILTO=ana", "0 3 * * * backup.sh"]
    comando = f"cd {AUTOMACAO} && {PYTHON} -m esteira publicar rodar"
    assert linhas[2] == f"*/15 * * * * {comando} >/dev/null # clipline: tudo-e-politica-publicar"
    assert linhas[3] == f"@reboot {comando} >/dev/null # clipline: tudo-e-politica-publicar"
    assert passo.entrada.endswith("\n")


def test_cron_reinstalar_troca_as_linhas_antigas_e_desinstalar_tira():
    primeira = tarefa.crontab_com("0 3 * * * backup.sh\n", PYTHON, AUTOMACAO, "Tudo é Política")
    segunda = tarefa.crontab_com(primeira, PurePosixPath("/outro/python"), AUTOMACAO, "Tudo é Política")
    assert segunda.count("# clipline: tudo-e-politica-publicar") == 2 and "/outro/python" in segunda
    assert tarefa.crontab_sem(segunda, "Tudo é Política") == "0 3 * * * backup.sh\n"
    assert tarefa.crontab_sem(segunda, "Outro Canal") == segunda  # a tarefa de outro canal fica


def test_cron_sem_crontab_ainda_comeca_vazio_e_aspas_em_caminho_com_espaco():
    sistema = Sistema({**SEM_SYSTEMD, "crontab -l": Execucao(1, "no crontab for ana")})
    plano = plano_instalar("linux", PurePosixPath("/a b/py"), PurePosixPath("/a b/100%"), "X", Path("/casa"), sistema)
    texto = plano.passos[0].entrada
    assert texto.startswith("*/15 * * * * cd '/a b/100\\%' && '/a b/py' -m esteira")
    assert "no crontab" not in texto


def test_sem_systemd_e_sem_crontab_explica():
    sistema = Sistema({**SEM_SYSTEMD, "crontab -l": Execucao(127, "crontab não encontrado")})
    with pytest.raises(ErroTarefa, match="sem systemd do usuário e sem crontab"):
        plano_instalar("linux", PYTHON, AUTOMACAO, "Tudo é Política", Path("/casa"), sistema)


def test_cron_desinstalar():
    atual = tarefa.crontab_com("0 3 * * * backup.sh\n", PYTHON, AUTOMACAO, "Tudo é Política")
    sistema = Sistema({**SEM_SYSTEMD, "crontab -l": Execucao(0, atual)})
    plano = plano_desinstalar("linux", "Tudo é Política", Path("/casa"), sistema)
    assert [(p.comando, p.entrada) for p in plano.passos] == [(["crontab", "-"], "0 3 * * * backup.sh\n")]


# --- macOS: launchd ---------------------------------------------------------------------------------------


def test_launchd_plist():
    dados = plistlib.loads(tarefa.plist_launchd(PYTHON, AUTOMACAO, "Tudo é Política").encode("utf-8"))
    assert dados == {
        "Label": "clipline.tudo-e-politica.publicar",
        "ProgramArguments": [str(PYTHON), "-m", "esteira", "publicar", "rodar"],
        "WorkingDirectory": str(AUTOMACAO),
        "StartInterval": 900,
        "RunAtLoad": True,
        "ProcessType": "Background",
    }


def test_launchd_plano_instalar_e_desinstalar(tmp_path):
    sistema = Sistema()
    plano = plano_instalar("launchd", PYTHON, AUTOMACAO, "Tudo é Política", tmp_path, sistema, uid=501)
    plist = tmp_path / "Library" / "LaunchAgents" / "clipline.tudo-e-politica.publicar.plist"
    assert aplicar(plano, sistema) == []
    assert plistlib.loads(plist.read_bytes())["Label"] == "clipline.tudo-e-politica.publicar"
    assert [c for c, _ in sistema.comandos] == [
        ["launchctl", "bootout", "gui/501/clipline.tudo-e-politica.publicar"],
        ["launchctl", "bootstrap", "gui/501", str(plist)],
    ]
    sistema.comandos.clear()
    aplicar(plano_desinstalar("launchd", "Tudo é Política", tmp_path, sistema, uid=501), sistema)
    assert not plist.exists()
    assert [c for c, _ in sistema.comandos] == [["launchctl", "bootout", "gui/501/clipline.tudo-e-politica.publicar"]]


def test_launchd_bootout_sem_tarefa_carregada_nao_para_a_instalacao(tmp_path):
    sistema = Sistema({"launchctl bootout": Execucao(3, "No such process")})
    plano = plano_instalar("launchd", PYTHON, AUTOMACAO, "Tudo é Política", tmp_path, sistema, uid=501)
    avisos = aplicar(plano, sistema)
    assert avisos == ["aviso: launchctl falhou (código 3): No such process"]
    assert sistema.comandos[-1][0][:2] == ["launchctl", "bootstrap"]


# --- sistema e situação (doctor) --------------------------------------------------------------------------


def test_sistema_atual():
    assert agendador.sistema_atual("win32") == "windows"
    assert agendador.sistema_atual("darwin") == "launchd"
    assert agendador.sistema_atual("linux") == "linux"


def test_situacao_windows_tarefa_antiga_pede_reinstalar():
    linha = 'cmd /c cd /d "C:\\A" && "py" -m esteira publicar rodar >> logs\\publicar.log 2>&1'
    antiga = Execucao(0, f"Tarefa a ser executada: {linha}")
    feito = situacao("windows", "Tudo é Política", Path("C:/casa"), Sistema({"schtasks /Query": antiga}))
    assert feito.estado == "aviso" and "reinstale com publicar instalar-tarefa --confirmar" in feito.detalhe


def test_situacao_windows_nova_e_ausente():
    nova = Execucao(0, 'Tarefa a ser executada: cmd /c cd /d "C:\\A" && "py" -m esteira publicar rodar')
    assert situacao("windows", "Tudo é Política", Path("C:/c"), Sistema({"schtasks /Query": nova})).estado == "ok"
    ausente = Sistema({"schtasks /Query": Execucao(1, "ERRO: o sistema não pode encontrar o arquivo especificado.")})
    feito = situacao("windows", "Tudo é Política", Path("C:/c"), ausente)
    assert feito.estado == "aviso" and feito.detalhe.startswith("não instalada")
    assert [c for c, _ in ausente.comandos] == tarefa.comandos_consultar_schtasks("Tudo é Política")


def test_situacao_linux_e_mac_pelos_arquivos(tmp_path):
    sistema = Sistema({"crontab -l": Execucao(1, "no crontab")})
    assert situacao("linux", "Tudo é Política", tmp_path, sistema).estado == "aviso"
    aplicar(plano_instalar("linux", PYTHON, AUTOMACAO, "Tudo é Política", tmp_path, Sistema()), Sistema())
    assert situacao("linux", "Tudo é Política", tmp_path, sistema).detalhe == "instalada no systemd do usuário (timer)"
    assert situacao("launchd", "Tudo é Política", tmp_path, sistema).estado == "aviso"
    no_cron = Sistema({"crontab -l": Execucao(0, tarefa.crontab_com("", PYTHON, AUTOMACAO, "Canal"))})
    assert situacao("linux", "Canal", tmp_path, no_cron).detalhe == "instalada no crontab do usuário"


def test_doctor_mostra_a_tarefa_antiga(monkeypatch):
    from esteira import diagnostico

    monkeypatch.setattr(agendador, "sistema_atual", lambda: "windows")
    antiga = Execucao(0, "cmd /c ... >> logs\\publicar.log 2>&1")
    [item] = diagnostico._tarefa_publicacao(Sistema({"schtasks /Query": antiga}))
    assert item.nome == "tarefa de publicação" and item.estado == "aviso"
    assert "reinstale" in item.detalhe


def test_executar_no_sistema_sem_o_programa():
    feito = agendador.executar_no_sistema(["programa-que-nao-existe-clipline-123"])
    assert feito.codigo == 127
