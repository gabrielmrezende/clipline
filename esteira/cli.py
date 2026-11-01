import argparse
import json
import sys
from pathlib import Path

from esteira.caminhos import CONTEXTO, garantir_escrita
from esteira.cartao import gerar_cartao
from esteira.cortar import cortar_episodio, ler_aprovados
from esteira.episodio import criar_episodio
from esteira.midia import ErroMidia
from esteira.transcrever import carregar_glossario, ler_palavras, transcrever
from esteira.validar import validar_trecho


def _transcrever(args) -> int:
    pasta = criar_episodio(Path(args.video), args.quadro, args.numero, args.convidado)
    nomes = carregar_glossario(CONTEXTO / "glossario.md")
    palavras = transcrever(Path(args.video), pasta, nomes, forcar=args.forcar)
    print(f"{len(palavras)} palavras em {pasta / 'transcricao'}")
    return 0


def _validar(args) -> int:
    pasta = Path(args.pasta)
    duracao = json.loads((pasta / "episodio.json").read_text("utf-8"))["duracao"]
    palavras = ler_palavras(pasta)
    erros = 0
    for corte in ler_aprovados(pasta):
        problemas = validar_trecho(palavras, corte, duracao)
        erros += len(problemas)
        print(f"{corte.numero:02d} {corte.titulo}: {'; '.join(problemas) or 'ok'}")
    return 1 if erros else 0


def _cortar(args) -> int:
    pasta = garantir_escrita(Path(args.pasta))
    numeros = set(args.numero) if args.numero else None
    resultados = cortar_episodio(pasta, numeros, args.forcar)
    for numero, resultado in resultados.items():
        print(f"{numero:02d}: {resultado}")
    return 0 if all(r == "ok" for r in resultados.values()) else 1


def _cartao(args) -> int:
    saida = garantir_escrita(Path(args.saida))
    print(gerar_cartao(args.manchete, args.veiculo, args.data, saida))
    return 0


def principal(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="esteira")
    comandos = parser.add_subparsers(required=True)

    c = comandos.add_parser("transcrever")
    c.add_argument("video")
    c.add_argument("--quadro", required=True)
    c.add_argument("--numero", type=int, required=True)
    c.add_argument("--convidado", required=True)
    c.add_argument("--forcar", action="store_true")
    c.set_defaults(funcao=_transcrever)

    c = comandos.add_parser("validar")
    c.add_argument("pasta")
    c.set_defaults(funcao=_validar)

    c = comandos.add_parser("cortar")
    c.add_argument("pasta")
    c.add_argument("--numero", type=int, action="append")
    c.add_argument("--forcar", action="store_true")
    c.set_defaults(funcao=_cortar)

    c = comandos.add_parser("cartao")
    c.add_argument("--manchete", required=True)
    c.add_argument("--veiculo", required=True)
    c.add_argument("--data", required=True)
    c.add_argument("--saida", required=True)
    c.set_defaults(funcao=_cartao)

    args = parser.parse_args(argv)
    try:
        return args.funcao(args)
    except (ErroMidia, FileExistsError) as erro:
        print(f"Erro: {erro}", file=sys.stderr)
        return 1
