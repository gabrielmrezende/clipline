import argparse
import json
import sys
from pathlib import Path

from esteira.caminhos import CONTEXTO, MUSICAS, garantir_escrita
from esteira.cartao import gerar_cartao
from esteira.cortar import atualizar_imagens, ler_aprovados, pasta_do_corte, preparar_episodio
from esteira.episodio import criar_episodio
from esteira.midia import ErroMidia
from esteira.montar import montar_episodio
from esteira.musica import (
    baixar_catalogo, baixar_musicas, baixar_url, escrever_proposta, ler_catalogo, propor,
)
from esteira.planos import gerar_folha, gravar_planos, ler_planos, planos_iniciais
from esteira.revisao import escrever_revisao
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


def _imprimir(resultados: dict[int, str]) -> int:
    for numero, resultado in resultados.items():
        print(f"{numero:02d}: {resultado}")
    return 0 if all(r.startswith("ok") for r in resultados.values()) else 1


def _preparar(args) -> int:
    pasta = garantir_escrita(Path(args.pasta))
    numeros = set(args.numero) if args.numero else None
    return _imprimir(preparar_episodio(pasta, numeros, args.forcar))


def _montar(args) -> int:
    pasta = garantir_escrita(Path(args.pasta))
    numeros = set(args.numero) if args.numero else None
    return _imprimir(montar_episodio(pasta, numeros, args.forcar))


def _imagens(args) -> int:
    pasta = garantir_escrita(Path(args.pasta))
    falhas = 0
    for corte in ler_aprovados(pasta):
        if args.numero and corte.numero not in args.numero:
            continue
        try:
            print(f"{corte.numero:02d}: {atualizar_imagens(pasta_do_corte(pasta, corte))} imagens")
        except FileNotFoundError:
            falhas += 1
            print(f"{corte.numero:02d}: erro: montagem.json não encontrado, rode preparar")
        except (OSError, ValueError, KeyError, TypeError) as erro:
            falhas += 1
            print(f"{corte.numero:02d}: erro: {erro}")
    return 1 if falhas else 0


def _planos(args) -> int:
    pasta = garantir_escrita(Path(args.pasta))
    video = Path(json.loads((pasta / "episodio.json").read_text("utf-8"))["video"])
    for corte in ler_aprovados(pasta):
        if args.numero and corte.numero not in args.numero:
            continue
        destino = pasta_do_corte(pasta, corte)
        destino.mkdir(exist_ok=True)
        planos = ler_planos(destino)
        if not planos or args.forcar:
            planos = planos_iniciais(video, corte.inicio, corte.fim)
            gravar_planos(destino, planos)
        gerar_folha(video, planos, destino / "planos.jpg")
        print(f"{corte.numero:02d}: {len(planos)} planos")
    return 0


def _revisao(args) -> int:
    pasta = garantir_escrita(Path(args.pasta))
    print(escrever_revisao(pasta))
    return 0


def _cartao(args) -> int:
    saida = garantir_escrita(Path(args.saida))
    print(gerar_cartao(args.manchete, args.veiculo, args.data, saida))
    return 0


def _musicas(args) -> int:
    if args.acao == "baixar":
        erros = baixar_musicas(MUSICAS, baixar_catalogo(), baixar_url)
        print(f"{len(ler_catalogo(MUSICAS))} faixas no catálogo")
        for erro in erros:
            print(erro)
        return 0
    selecao = propor(baixar_catalogo())
    escrever_proposta(selecao, MUSICAS)
    for clima, pecas in selecao.items():
        print(f"{clima}: {len(pecas)} faixas")
    print(f"Proposta em {MUSICAS / 'proposta.md'}")
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

    c = comandos.add_parser("preparar")
    c.add_argument("pasta")
    c.add_argument("--numero", type=int, action="append")
    c.add_argument("--forcar", action="store_true")
    c.set_defaults(funcao=_preparar)

    c = comandos.add_parser("imagens")
    c.add_argument("pasta")
    c.add_argument("--numero", type=int, action="append")
    c.set_defaults(funcao=_imagens)

    c = comandos.add_parser("montar")
    c.add_argument("pasta")
    c.add_argument("--numero", type=int, action="append")
    c.add_argument("--forcar", action="store_true")
    c.set_defaults(funcao=_montar)

    c = comandos.add_parser("planos")
    c.add_argument("pasta")
    c.add_argument("--numero", type=int, action="append")
    c.add_argument("--forcar", action="store_true")
    c.set_defaults(funcao=_planos)

    c = comandos.add_parser("revisao")
    c.add_argument("pasta")
    c.set_defaults(funcao=_revisao)

    c = comandos.add_parser("cartao")
    c.add_argument("--manchete", required=True)
    c.add_argument("--veiculo", required=True)
    c.add_argument("--data", required=True)
    c.add_argument("--saida", required=True)
    c.set_defaults(funcao=_cartao)

    c = comandos.add_parser("musicas")
    c.add_argument("acao", choices=["propor", "baixar"])
    c.set_defaults(funcao=_musicas)

    args = parser.parse_args(argv)
    try:
        return args.funcao(args)
    except (ErroMidia, FileExistsError) as erro:
        print(f"Erro: {erro}", file=sys.stderr)
        return 1
