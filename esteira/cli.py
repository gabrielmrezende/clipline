import argparse
import json
import sys
from pathlib import Path

from esteira.caminhos import CONTEXTO, CORTES, MUSICAS, EscritaProibida, garantir_escrita
from esteira.cartao import gerar_cartao
from esteira.cortar import TRABALHO, ler_aprovados, pasta_de_trabalho, pasta_do_corte, preparar_episodio
from esteira.episodio import criar_episodio
from esteira.fluxo_imagens import ErroBusca, buscar_episodio, resumir_episodio, sugerir_episodio
from esteira.fluxo_planos import planejar_episodio
from esteira.midia import ErroMidia
from esteira.montar import montar_episodio
from esteira.musica import (
    atualizar_musica, baixar_catalogo, baixar_musicas, baixar_url, escrever_proposta, ler_catalogo, propor,
)
from esteira.painel.acesso import CofreKeyring, gerar_codigo
from esteira.pedidos import pessoas_do_glossario
from esteira.publicar import comandos as publicar
from esteira.publicar.agendar import ErroAgendar
from esteira.publicar.credenciais import ErroConexao
from esteira.publicar.http import ErroRede
from esteira.publicar.post import ErroPost
from esteira.receita import NOME_ARQUIVO
from esteira.revisao import escrever_revisao
from esteira.transcrever import carregar_glossario, ler_palavras, transcrever
from esteira.validar import validar_trecho
from esteira import vozes as modulo_vozes


def _transcrever(args) -> int:
    pasta = criar_episodio(Path(args.video), args.quadro, args.numero, args.convidado)
    nomes = carregar_glossario(CONTEXTO / "glossario.md")
    palavras = transcrever(Path(args.video), pasta, nomes, forcar=args.forcar)
    print(f"{len(palavras)} palavras em {pasta / 'transcricao'}")
    return 0


def _vozes(args) -> int:
    pasta = garantir_escrita(Path(args.pasta))
    try:
        trechos = modulo_vozes.separar_vozes(
            Path(args.video), pasta, args.pessoas, criar=modulo_vozes.criar_pipeline, forcar=args.forcar
        )
    except (modulo_vozes.ErroVozes, FileExistsError) as erro:
        print(f"Erro: {erro}", file=sys.stderr)
        return 1
    print(f"{len({t.voz for t in trechos})} vozes, {len(trechos)} trechos")
    return 0


def _positivo(texto: str) -> int:
    valor = int(texto)
    if valor <= 0:
        raise argparse.ArgumentTypeError(f"precisa ser maior que zero: {texto}")
    return valor


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
    numeros = set(args.numero) if args.numero else None
    pessoas = pessoas_do_glossario(CONTEXTO / "glossario.md")
    if args.acao == "resumo":
        fotos, total, resultados = resumir_episodio(pasta, numeros, pessoas=pessoas)
        codigo = _imprimir(resultados)
        megas = f"{total / 1_048_576:.1f}".replace(".", ",")
        print(f"{fotos} fotos, {megas} MB, origem Wikimedia Commons")
        return codigo
    fluxo = buscar_episodio if args.acao == "buscar" else sugerir_episodio
    return _imprimir(fluxo(pasta, numeros, pessoas))


def _musica(args) -> int:
    pasta = garantir_escrita(Path(args.pasta))
    falhas = 0
    for corte in ler_aprovados(pasta):
        if args.numero and corte.numero not in args.numero:
            continue
        destino = pasta_do_corte(pasta, corte)
        if not (destino / TRABALHO / NOME_ARQUIVO).exists():
            falhas += 1
            print(f"{corte.numero:02d}: erro: {NOME_ARQUIVO} não encontrado, rode preparar")
            continue
        try:
            titulo = atualizar_musica(pasta_de_trabalho(destino), corte, f"{pasta.name}/{destino.name}", MUSICAS)
        except (OSError, ValueError, KeyError, TypeError) as erro:
            falhas += 1
            print(f"{corte.numero:02d}: erro: {erro}")
            continue
        print(f"{corte.numero:02d}: {titulo or f'sem música para o clima {corte.clima}'}")
    return 1 if falhas else 0


def _planos(args) -> int:
    pasta = garantir_escrita(Path(args.pasta))
    numeros = set(args.numero) if args.numero else None
    resultados = planejar_episodio(pasta, numeros, args.forcar or args.religar, religar=args.religar)
    for numero, resultado in resultados.items():
        print(f"{numero:02d}: {resultado}")
    return 1 if any(r.startswith("erro") for r in resultados.values()) else 0


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
        return 1 if erros else 0
    selecao = propor(baixar_catalogo())
    escrever_proposta(selecao, MUSICAS, args.forcar)
    for clima, pecas in selecao.items():
        print(f"{clima}: {len(pecas)} faixas")
    print(f"Proposta em {MUSICAS / 'proposta.md'}")
    return 0


ESTATICO = Path(__file__).parent / "painel" / "estatico"


def _ip_local() -> str:
    import socket

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as soquete:
            soquete.connect(("8.8.8.8", 80))  # UDP: não envia nada, só descobre a interface de saída
            return soquete.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def _painel(args, servir=None, cofre=None) -> int:
    if args.acao == "codigo":
        codigo = gerar_codigo(cofre or CofreKeyring())
        print(f"Código de acesso: {codigo} (anote; ele não será mostrado de novo)")
        return 0
    if not (ESTATICO / "index.html").is_file():
        print('Painel sem build: rode "npm install" e "npm run build" em painel-web/', file=sys.stderr)
        return 1
    cofre = cofre or CofreKeyring()
    if args.rede and not (cofre.ler("codigo") and cofre.ler("chave_sessao")):
        print('Sem código de acesso: rode "python -m esteira painel codigo"', file=sys.stderr)
        return 1
    from esteira.painel.app import criar_app

    hosts = ["127.0.0.1", "localhost"]
    if args.rede:
        ip = _ip_local()
        hosts.append(ip)
    cortes = Path(args.cortes).resolve() if args.cortes else CORTES
    app = criar_app(cortes, rede=args.rede, cofre=cofre if args.rede else None, estatico=ESTATICO, hosts=hosts)
    if args.rede:
        print(f"Painel na rede: http://{ip}:{args.porta}")
        print("Use só na Wi-Fi de casa. Não use em rede pública.")
    else:
        print(f"Painel em http://127.0.0.1:{args.porta}")
    if servir is None:
        import uvicorn

        servir = uvicorn.run
    servir(app, host="0.0.0.0" if args.rede else "127.0.0.1", port=args.porta)
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

    c = comandos.add_parser("vozes")
    c.add_argument("video")
    c.add_argument("pasta")
    c.add_argument("--pessoas", type=_positivo, default=3)
    c.add_argument("--forcar", action="store_true")
    c.set_defaults(funcao=_vozes)

    c = comandos.add_parser("validar")
    c.add_argument("pasta")
    c.set_defaults(funcao=_validar)

    c = comandos.add_parser("preparar")
    c.add_argument("pasta")
    c.add_argument("--numero", type=int, action="append")
    c.add_argument("--forcar", action="store_true")
    c.set_defaults(funcao=_preparar)

    c = comandos.add_parser("imagens")
    c.add_argument("acao", choices=["buscar", "resumo", "sugerir"])
    c.add_argument("pasta")
    c.add_argument("--numero", type=int, action="append")
    c.set_defaults(funcao=_imagens)

    c = comandos.add_parser("montar")
    c.add_argument("pasta")
    c.add_argument("--numero", type=int, action="append")
    c.add_argument("--forcar", action="store_true")
    c.set_defaults(funcao=_montar)

    c = comandos.add_parser("musica")
    c.add_argument("pasta")
    c.add_argument("--numero", type=int, action="append")
    c.set_defaults(funcao=_musica)

    c = comandos.add_parser("planos")
    c.add_argument("pasta")
    c.add_argument("--numero", type=int, action="append")
    c.add_argument("--forcar", action="store_true")
    c.add_argument("--religar", action="store_true", help="recalcula a ligação voz/pessoa (implica --forcar)")
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
    c.add_argument("--forcar", action="store_true")
    c.set_defaults(funcao=_musicas)

    c = comandos.add_parser("painel")
    c.add_argument("acao", nargs="?", choices=["codigo"])
    c.add_argument("--rede", action="store_true")
    c.add_argument("--porta", type=_positivo, default=8765)
    c.add_argument("--cortes")
    c.set_defaults(funcao=_painel)

    publicar.registrar(comandos)

    args = parser.parse_args(argv)
    try:
        return args.funcao(args)
    except (ErroMidia, ErroBusca, FileExistsError, EscritaProibida, ErroAgendar, ErroPost, ErroConexao, ErroRede) as erro:
        print(f"Erro: {erro}", file=sys.stderr)
        return 1
