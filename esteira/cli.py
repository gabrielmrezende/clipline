import argparse
import getpass
import json
import os
import sys
from pathlib import Path

from esteira import agente, contrato, diagnostico, falantes

from esteira.caminhos import CONTEXTO, CORTES, MUSICAS, EscritaProibida, garantir_escrita
from esteira.cartao import gerar_cartao
from esteira.cortar import CORTE_MP4, TRABALHO, ler_aprovados, pasta_de_trabalho, pasta_do_corte, preparar_episodio
from esteira.episodio import criar_episodio
from esteira.fluxo_imagens import ErroBusca, buscar_episodio, cortes_com_pedidos, resumir_episodio, sugerir_episodio
from esteira.fluxo_planos import planejar_episodio
from esteira.imagens_ia.chaves import gravar_chave
from esteira.imagens_ia.config import PROVEDORES, ler_config, provedor_atual
from esteira.imagens_ia.gerar import gerar_cortes, orcamento
from esteira.imagens_ia.provedor import ErroImagem
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
    arquivo = _gravar_texto_com_falantes(pasta)
    if arquivo:
        print(f"Transcrição com falantes em {arquivo}")
    return 0


def _ligacao_e_nomes(pasta: Path) -> tuple[dict, dict]:
    try:
        dados = json.loads((pasta / "transcricao" / "pessoas.json").read_text("utf-8"))
        return dict(dados.get("ligacao") or {}), dict(dados.get("nomes") or {})
    except (OSError, ValueError, AttributeError, TypeError):
        return {}, {}


def _gravar_texto_com_falantes(pasta: Path) -> Path | None:
    """transcricao/texto-falantes.md: a transcrição com quem fala e as pausas longas (para o agente)."""
    try:
        palavras = ler_palavras(pasta)
        trechos = modulo_vozes.ler_vozes(pasta)
    except (OSError, ValueError, KeyError, TypeError, modulo_vozes.ErroVozes):
        return None
    ligacao, nomes = _ligacao_e_nomes(pasta)
    destino = garantir_escrita(pasta / "transcricao" / "texto-falantes.md")
    temporario = destino.with_name(destino.name + ".tmp")
    temporario.write_text(falantes.texto_com_falantes(palavras, trechos, ligacao, nomes), "utf-8")
    temporario.replace(destino)
    return destino


def _positivo(texto: str) -> int:
    valor = int(texto)
    if valor <= 0:
        raise argparse.ArgumentTypeError(f"precisa ser maior que zero: {texto}")
    return valor


def _validar(args) -> int:
    pasta = Path(args.pasta)
    catalogo = {f.arquivo for f in ler_catalogo(MUSICAS)} if (MUSICAS / "catalogo.json").exists() else None
    problemas = [p.como_dict() for p in contrato.conferir_episodio(pasta, None, catalogo)]
    trechos: list[dict] = []
    if not any(p["arquivo"] == contrato.APROVADOS for p in problemas):
        try:
            duracao = json.loads((pasta / "episodio.json").read_text("utf-8"))["duracao"]
            palavras = ler_palavras(pasta)
        except (OSError, ValueError, KeyError) as erro:
            problemas.append({"arquivo": "episodio.json ou transcricao/palavras.json", "campo": "", "mensagem": f"ilegível: {erro}"})
        else:
            for corte in ler_aprovados(pasta):
                achados = validar_trecho(palavras, corte, duracao)
                trechos.append({"numero": corte.numero, "titulo": corte.titulo, "problemas": achados})
    if args.json:
        print(json.dumps({"ok": not problemas and not any(t["problemas"] for t in trechos),
                          "arquivos": problemas, "cortes": trechos}, ensure_ascii=False, indent=2))
    else:
        for p in problemas:
            print(f"{p['arquivo']}: {p['campo'] + ': ' if p['campo'] else ''}{p['mensagem']}")
        for t in trechos:
            print(f"{t['numero']:02d} {t['titulo']}: {'; '.join(t['problemas']) or 'ok'}")
    return 1 if problemas or any(t["problemas"] for t in trechos) else 0


def _trecho(args) -> int:
    pasta = Path(args.pasta)
    palavras = ler_palavras(pasta)
    try:
        trechos = modulo_vozes.ler_vozes(pasta)
    except modulo_vozes.ErroVozes:
        trechos = []
    ligacao, nomes = _ligacao_e_nomes(pasta)
    intervalo = falantes.palavras_do_intervalo(palavras, args.de - args.margem, args.ate + args.margem)
    rotulos = falantes.rotular([p for _, p in intervalo], trechos) if trechos else [None] * len(intervalo)
    linhas = [
        {"indice": i, "texto": p.texto, "inicio": round(p.inicio, 3), "fim": round(p.fim, 3),
         "falante": falantes.nome_da_voz(v, ligacao, nomes) if trechos else None,
         "dentro": args.de <= p.inicio and p.fim <= args.ate}
        for (i, p), v in zip(intervalo, rotulos)
    ]
    if args.json:
        print(json.dumps(linhas, ensure_ascii=False))
        return 0
    for linha in linhas:
        marca = " " if linha["dentro"] else "~"
        quem = f" {linha['falante']}" if linha["falante"] else ""
        print(f"{marca}{linha['inicio']:9.3f} {linha['fim']:9.3f}{quem}  {linha['texto']}")
    return 0


def _status(args) -> int:
    if args.regras:
        print(diagnostico.hash_das_regras())
        return 0
    pastas = [Path(args.pasta)] if args.pasta else sorted(p for p in CORTES.iterdir() if p.is_dir()) if CORTES.is_dir() else []
    todos = [diagnostico.status_episodio(p) for p in pastas]
    if args.json:
        print(json.dumps(todos if not args.pasta else todos[0], ensure_ascii=False, indent=2))
    else:
        print("\n\n".join(diagnostico.texto_do_status(s) for s in todos) or "Nenhum episódio em 2 - Cortes.")
    return 0


def _sugerir_cortes(args) -> int:
    arquivo = agente.sugerir_cortes(Path(args.pasta), modelo=args.modelo)
    print(f"Proposta em {arquivo}. Revise e copie para aprovados.json; depois rode validar.")
    return 0


def _aprendizado(args) -> int:
    print(f"Comparação em {agente.aprendizado(Path(args.pasta))}")
    return 0


def _doctor(args) -> int:
    itens = diagnostico.doctor()
    if args.json:
        print(json.dumps([i.como_dict() for i in itens], ensure_ascii=False, indent=2))
    else:
        simbolo = {"ok": "ok   ", "aviso": "aviso", "falta": "FALTA"}
        for i in itens:
            print(f"{simbolo[i.estado]}  {i.nome}: {i.detalhe}")
    return 1 if any(i.estado == "falta" for i in itens) else 0


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
    return _imprimir(montar_episodio(pasta, numeros, args.forcar, sem_imagens=args.sem_imagens))


def _imagens_conectar(provedor: str) -> int:
    if provedor not in PROVEDORES:
        print(f"Provedor desconhecido: {provedor}. Use um destes: {', '.join(PROVEDORES)}.", file=sys.stderr)
        return 2
    chave = getpass.getpass(f"Chave da API ({provedor}): ").strip()
    if not chave:
        raise ErroImagem("Chave da API vazia; nada foi guardado.")
    gravar_chave(provedor, chave)
    print(f"Chave da {provedor} guardada no Windows.")
    return 0


def _imagens_gerar(args, pasta: Path, numeros: set[int] | None, pessoas: list[str]) -> int:
    config = ler_config()
    cortes = [destino for _, destino in cortes_com_pedidos(pasta, numeros)]
    previsto = orcamento(cortes, config)
    if not args.confirmar:
        custo = f"{previsto['custo_usd']:.2f}"
        print(f"{previsto['imagens']} imagens, provedor {previsto['provedor']}, modelo {previsto['modelo']}, "
              f"custo estimado ~US$ {custo}")
        return 0
    arquivos, avisos = gerar_cortes(cortes, provedor_atual(config), config, pessoas, progresso=print)
    for arquivo in arquivos:
        print(f"Gerada: {arquivo}")
    for aviso in avisos:
        print(f"Aviso: {aviso}")
    return 1 if avisos else 0


def _imagens(args) -> int:
    if args.acao == "conectar":
        return _imagens_conectar(args.pasta)
    pasta = garantir_escrita(Path(args.pasta))
    numeros = set(args.numero) if args.numero else None
    pessoas = pessoas_do_glossario(CONTEXTO / "glossario.md")
    if args.acao == "gerar":
        return _imagens_gerar(args, pasta, numeros, pessoas)
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


def _tem_dependencias_do_painel() -> bool:
    try:
        import fastapi  # noqa: F401
        import uvicorn  # noqa: F401
    except ImportError:
        return False
    return True


def _montagem_falsa(pasta: Path, numero: int) -> str:
    """Montagem de mentira, só para os testes de ponta a ponta: não roda o ffmpeg.

    Regrava o corte.mp4 com os mesmos bytes ou, se ele não existir, grava um vazio. Na troca de música
    o corte.mp4 antigo já foi para trabalho/corte-anterior.mp4, então ali o corte.mp4 novo sai sempre vazio.
    """
    corte = next(c for c in ler_aprovados(pasta) if c.numero == numero)
    video = pasta_do_corte(pasta, corte) / CORTE_MP4
    video.write_bytes(video.read_bytes() if video.exists() else b"")
    return "ok"


def _painel(args, servir=None, cofre=None) -> int:
    if args.acao == "codigo":
        codigo = gerar_codigo(cofre or CofreKeyring())
        print(f"Código de acesso: {codigo} (anote; ele não será mostrado de novo)")
        return 0
    if not _tem_dependencias_do_painel():
        print(
            'O painel precisa de fastapi e uvicorn: rode ".venv\\Scripts\\python.exe -m pip install fastapi uvicorn"',
            file=sys.stderr,
        )
        return 1
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
    extra = {}
    if os.environ.get("ESTEIRA_PAINEL_MONTAGEM_FALSA") == "1":  # só para os testes de ponta a ponta
        extra["montar"] = _montagem_falsa
    if os.environ.get("ESTEIRA_PAINEL_PASTA_MUSICAS"):  # só para os testes de ponta a ponta
        extra["pasta_musicas"] = Path(os.environ["ESTEIRA_PAINEL_PASTA_MUSICAS"]).resolve()
    if os.environ.get("ESTEIRA_PAINEL_IMAGEM_FALSA") == "1":  # só para os testes de ponta a ponta
        from esteira.imagens_ia import falso

        extra["provedores"] = falso.fabricas()
        extra["tem_chave"] = falso.tem_chave
    app = criar_app(
        cortes, rede=args.rede, cofre=cofre if args.rede else None, estatico=ESTATICO, hosts=hosts, **extra
    )
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

    c = comandos.add_parser("validar", help="confere os arquivos do agente e os tempos dos cortes")
    c.add_argument("pasta")
    c.add_argument("--json", action="store_true", help="resposta em JSON")
    c.set_defaults(funcao=_validar)

    c = comandos.add_parser("trecho", help="palavras, tempos e quem fala de um intervalo do episódio")
    c.add_argument("pasta")
    c.add_argument("--de", type=float, required=True, help="segundos do episódio")
    c.add_argument("--ate", type=float, required=True)
    c.add_argument("--margem", type=float, default=5.0, help="segundos antes e depois (marcados com ~)")
    c.add_argument("--json", action="store_true")
    c.set_defaults(funcao=_trecho)

    c = comandos.add_parser("status", help="em que etapa está cada corte e qual o próximo passo")
    c.add_argument("pasta", nargs="?")
    c.add_argument("--json", action="store_true")
    c.add_argument("--regras", action="store_true", help="só a marca das regras de Contexto/ (vai na origem)")
    c.set_defaults(funcao=_status)

    c = comandos.add_parser("sugerir-cortes", help="o Claude propõe os cortes sem sessão interativa (aprovados.proposta.json)")
    c.add_argument("pasta")
    c.add_argument("--modelo", help="modelo do Claude Code (padrão: o configurado nele)")
    c.set_defaults(funcao=_sugerir_cortes)

    c = comandos.add_parser("aprendizado", help="compara a proposta do Claude com o aprovados.json final")
    c.add_argument("pasta")
    c.set_defaults(funcao=_aprendizado)

    c = comandos.add_parser("doctor", help="confere ffmpeg, GPU, modelos, chaves, pastas e build do painel")
    c.add_argument("--json", action="store_true")
    c.set_defaults(funcao=_doctor)

    c = comandos.add_parser("preparar")
    c.add_argument("pasta")
    c.add_argument("--numero", type=int, action="append")
    c.add_argument("--forcar", action="store_true")
    c.set_defaults(funcao=_preparar)

    c = comandos.add_parser("imagens")
    c.add_argument("acao", choices=["buscar", "resumo", "sugerir", "conectar", "gerar"])
    c.add_argument("pasta")
    c.add_argument("--numero", type=int, action="append")
    c.add_argument("--confirmar", action="store_true")
    c.set_defaults(funcao=_imagens)

    c = comandos.add_parser("montar")
    c.add_argument("pasta")
    c.add_argument("--numero", type=int, action="append")
    c.add_argument("--forcar", action="store_true")
    c.add_argument("--sem-imagens", action="store_true")
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
    except (ErroMidia, ErroBusca, FileExistsError, EscritaProibida, ErroAgendar, ErroPost, ErroConexao, ErroRede, ErroImagem,
            contrato.ErroContrato, agente.ErroAgente) as erro:
        print(f"Erro: {erro}", file=sys.stderr)
        return 1
    except FileNotFoundError as erro:
        print(f"Erro: arquivo não encontrado: {erro.filename or erro}. Rode esteira status para ver a etapa que falta.",
              file=sys.stderr)
        return 1
    except json.JSONDecodeError as erro:
        print(f"Erro: JSON inválido (linha {erro.lineno}, coluna {erro.colno}): {erro.msg}. Rode esteira validar.",
              file=sys.stderr)
        return 1
    except (KeyError, TypeError) as erro:
        print(f"Erro: arquivo fora do formato ({type(erro).__name__}: {erro}). Rode esteira validar para ver o campo.",
              file=sys.stderr)
        return 1
