"""Ações do subcomando `esteira publicar`."""
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from esteira.caminhos import AUTOMACAO, CORTES
from esteira.publicar.agendar import FUSO, REDES, ErroAgendar, confirmar, preparar_pedido, resumo
from esteira.publicar.config import ler_modos
from esteira.publicar.fila import Ocupado, achar, gravar_fila, ler_fila, trava
from esteira.publicar.rodar import TRAVA, _redes_reais, _relato, rodar_tudo
from esteira.publicar.tarefa import comandos_schtasks

ENVIADOS = ("publicado", "privado", "rascunho")
LUGAR = {"youtube": "no Studio", "instagram": "no app", "tiktok": "no app"}


def _seguro(funcao):
    """Erros de arquivo ou de ambiente viram 'Erro: ...' no CLI, sem traceback."""
    def envolvida(args) -> int:
        try:
            return funcao(args)
        except Ocupado:
            raise ErroAgendar("outra execução em andamento (publicar rodar ou agendar); tente em alguns minutos") from None
        except subprocess.CalledProcessError as erro:
            raise ErroAgendar(f"schtasks falhou (código {erro.returncode})") from None
        except ImportError as erro:
            raise ErroAgendar(f"falta instalar um pacote: {erro.name or erro}") from None
        except json.JSONDecodeError as erro:
            raise ErroAgendar(f"arquivo JSON inválido (linha {erro.lineno}): {erro.msg}") from None
        except ValueError as erro:
            raise ErroAgendar(str(erro)) from None
        except (KeyError, TypeError) as erro:
            raise ErroAgendar(f"arquivo inválido: {type(erro).__name__}: {erro}") from None
    return envolvida


def _redes(texto: str | None) -> list[str]:
    return [r.strip() for r in texto.split(",") if r.strip()] if texto else list(REDES)


def conectar(args) -> int:
    from esteira.publicar import instagram, tiktok, youtube

    {"youtube": youtube, "instagram": instagram, "tiktok": tiktok}[args.rede].conectar()
    print(f"{args.rede}: conectado")
    return 0


def agendar(args) -> int:
    pedido = preparar_pedido(Path(args.pasta), args.numero, args.data, _redes(args.redes), datetime.now(FUSO))
    modos = ler_modos()
    if not args.confirmar:
        print(resumo(pedido, modos))
        print("\nNada foi enviado. Para confirmar, rode de novo com --confirmar.")
        return 0
    with trava(TRAVA):
        itens = confirmar(pedido, modos, _redes_reais())
    for item in itens:
        print(_relato(item))
    falhou = any(i.estado == "erro" or (i.rede == "youtube" and i.estado == "agendado") for i in itens)
    return 1 if falhou else 0


def mostrar_fila(args) -> int:
    pastas = [Path(args.pasta)] if args.pasta else sorted(p.parent for p in Path(CORTES).glob("*/postagens.json"))
    for pasta in pastas:
        itens = [i for i in ler_fila(pasta) if i.estado != "cancelado"]
        if not itens:
            continue
        print(pasta.name)
        for i in sorted(itens, key=lambda i: (i.data, i.numero, i.rede)):
            quando = datetime.fromisoformat(i.data).strftime("%d/%m %H:%M")
            partes = [f"  {i.numero:02d} {i.rede:<9}", quando, i.estado]
            partes += [x for x in (i.link, i.erro) if x]
            print("  ".join(partes))
    return 0


def rodar(args) -> int:
    for linha in rodar_tudo():
        print(linha)
    return 0


def cancelar(args) -> int:
    with trava(TRAVA):
        return _cancelar(args)


def _cancelar(args) -> int:
    pasta = Path(args.pasta)
    itens = ler_fila(pasta)
    for rede in _redes(args.redes):
        item = achar(itens, args.numero, rede)
        if item is None:
            continue
        if item.estado == "agendado":
            item.estado = "cancelado"
            print(f"{rede}: cancelado")
        elif item.estado in ENVIADOS:
            print(f"{rede} já enviado: apague {LUGAR[rede]} se quiser")
        else:
            print(f"{rede}: está em {item.estado}; confira {LUGAR[rede]} e use publicar marcar")
    gravar_fila(pasta, itens)
    return 0


def marcar(args) -> int:
    with trava(TRAVA):
        return _marcar(args)


def _marcar(args) -> int:
    pasta = Path(args.pasta)
    itens = ler_fila(pasta)
    item = achar(itens, args.numero, args.rede)
    if item is None or item.estado != "conferir":
        raise ErroAgendar(f"{args.rede}: corte {args.numero} não está em conferir")
    if args.acao_marcar == "feito":
        item.estado, item.erro = "publicado", ""
    else:
        item.estado, item.tentativas, item.erro = "agendado", 0, ""
    gravar_fila(pasta, itens)
    print(_relato(item))
    return 0


def instalar_tarefa(args) -> int:
    lista = comandos_schtasks(Path(sys.executable), AUTOMACAO)
    if not args.confirmar:
        print("Vou criar estas tarefas no Agendador do Windows:")
        for comando in lista:
            print(subprocess.list2cmdline(comando))
        print("\nNada foi criado. Para confirmar, rode de novo com --confirmar.")
        return 0
    (Path(AUTOMACAO) / "logs").mkdir(exist_ok=True)
    for comando in lista:
        subprocess.run(comando, check=True)
    print("Tarefas criadas.")
    return 0


def registrar(comandos_cli) -> None:
    p = comandos_cli.add_parser("publicar")
    acoes = p.add_subparsers(required=True)

    c = acoes.add_parser("conectar")
    c.add_argument("rede", choices=REDES)
    c.set_defaults(funcao=_seguro(conectar))

    c = acoes.add_parser("agendar")
    c.add_argument("pasta")
    c.add_argument("--numero", type=int, required=True)
    c.add_argument("--data", required=True, help="AAAA-MM-DD HH:MM, horário de Brasília")
    c.add_argument("--redes", help="ex.: youtube,instagram (padrão: as três)")
    c.add_argument("--confirmar", action="store_true")
    c.set_defaults(funcao=_seguro(agendar))

    c = acoes.add_parser("fila")
    c.add_argument("pasta", nargs="?")
    c.set_defaults(funcao=_seguro(mostrar_fila))

    c = acoes.add_parser("rodar")
    c.set_defaults(funcao=_seguro(rodar))

    c = acoes.add_parser("cancelar")
    c.add_argument("pasta")
    c.add_argument("--numero", type=int, required=True)
    c.add_argument("--redes")
    c.set_defaults(funcao=_seguro(cancelar))

    c = acoes.add_parser("marcar")
    c.add_argument("pasta")
    c.add_argument("--numero", type=int, required=True)
    c.add_argument("--rede", choices=REDES, required=True)
    c.add_argument("acao_marcar", choices=["feito", "reenviar"])
    c.set_defaults(funcao=_seguro(marcar))

    c = acoes.add_parser("instalar-tarefa")
    c.add_argument("--confirmar", action="store_true")
    c.set_defaults(funcao=_seguro(instalar_tarefa))
