"""`clipline init`: cria o layout de um canal novo.

As pastas (contexto, programas, cortes e identidade, com `Encerramentos/` e `Logos/`), o `Contexto/` copiado de
`Contexto.exemplo/` e um `clipline.toml` com o nome do canal, a arroba, o perfil do TikTok, a duração dos cortes, as
pastas, a identidade e o prefixo das credenciais. O que falta vem das flags, de perguntas no terminal ou, com
`--sem-perguntas`, de padrões tirados do nome da pasta. Nunca sobrescreve: o que já existe fica como está e aparece
no relatório.

Só usa a biblioteca padrão: `py -m esteira init` roda logo depois do clone, antes do venv (ver `__main__.py`).
"""

import argparse
import json
import os
import re
import shutil
import sys
import tomllib
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from esteira import caminhos

AUTOMACAO = caminhos.AUTOMACAO
EXEMPLO_CONTEXTO = AUTOMACAO / "Contexto.exemplo"
EXTENSOES_DE_VIDEO = (".mp4", ".mov", ".mkv", ".webm")
LOGO_NOVA = "Logos/logo.png"
SUBPASTAS_DA_IDENTIDADE = ("Encerramentos", "Logos")
DURACAO_MINIMA = 60.0
DURACAO_MAXIMA = 120.0


class ErroInit(ValueError):
    pass


@dataclass
class Canal:
    nome: str
    arroba: str
    perfil_tiktok: str
    duracao_minima: float = DURACAO_MINIMA
    duracao_maxima: float = DURACAO_MAXIMA
    prefixo: str = ""  # credenciais; vazio: tirado do nome
    pastas: dict[str, str] = field(default_factory=lambda: dict(caminhos.PASTAS_PADRAO))


@dataclass
class Relatorio:
    linhas: list[tuple[str, Path]] = field(default_factory=list)  # (o que aconteceu, caminho)
    toml_criado: bool = False

    def anotar(self, estado: str, caminho: Path) -> None:
        self.linhas.append((estado, Path(caminho)))


# --- lógica pura -----------------------------------------------------------------------------------------------


def slug(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", sem_acento.lower()).strip("-")


def normalizar_arroba(texto: str) -> str:
    arroba = texto.strip()
    return arroba if not arroba or arroba.startswith("@") else f"@{arroba}"


def perfil_padrao(arroba: str) -> str:
    return f"https://www.tiktok.com/{arroba}" if arroba else ""


def nome_padrao(raiz: Path) -> str:
    """O nome do canal sem flag nem resposta: o da pasta do canal."""
    return Path(raiz).name.strip() or "Meu Canal"


def arroba_padrao(nome: str) -> str:
    """Tirada do nome: "Meu Canal" vira @meucanal."""
    return "@" + (slug(nome).replace("-", "") or "meucanal")


def conferir(canal: Canal) -> list[str]:
    problemas = []
    if not canal.nome.strip():
        problemas.append("o nome do canal não pode ser vazio")
    if not re.fullmatch(r"@[^\s@]+", canal.arroba):
        problemas.append(f"arroba inválida: {canal.arroba!r} (use algo como @meucanal)")
    if not 0 < canal.duracao_minima < canal.duracao_maxima:
        problemas.append("a duração mínima precisa ser positiva e menor que a máxima")
    for chave, nome in canal.pastas.items():
        if not nome.strip():
            problemas.append(f"o nome da pasta de {chave} não pode ser vazio")
    if not (canal.prefixo or slug(canal.nome)):
        problemas.append("não deu para tirar o prefixo das credenciais do nome; use --prefixo-credenciais")
    return problemas


def encerramentos_encontrados(identidade: Path) -> list[str]:
    """Os vídeos que já estão em Encerramentos/, relativos à pasta de identidade, em ordem de nome. Se forem
    exatamente os do canal original, na ordem de sempre (o rodízio não muda)."""
    pasta = Path(identidade) / "Encerramentos"
    if not pasta.is_dir():
        return []
    nomes = sorted((a.name for a in pasta.iterdir() if a.is_file() and a.suffix.lower() in EXTENSOES_DE_VIDEO),
                   key=str.casefold)
    achados = [f"Encerramentos/{nome}" for nome in nomes]
    if sorted(achados) == sorted(caminhos.ENCERRAMENTOS_PADRAO):
        return list(caminhos.ENCERRAMENTOS_PADRAO)
    return achados


def logo_encontrada(identidade: Path) -> str:
    """A logo que já está na pasta de identidade, ou o lugar onde ela deve entrar."""
    if (Path(identidade) / caminhos.LOGO_PADRAO).is_file():
        return caminhos.LOGO_PADRAO
    pasta = Path(identidade) / "Logos"
    pngs = sorted((a.name for a in pasta.glob("*.png") if a.is_file()), key=str.casefold) if pasta.is_dir() else []
    return f"Logos/{pngs[0]}" if pngs else LOGO_NOVA


def _texto(valor: str) -> str:
    """Um texto TOML entre aspas (o escape do JSON vale em TOML)."""
    return json.dumps(valor, ensure_ascii=False)


def _numero(valor: float) -> str:
    return str(int(valor)) if float(valor).is_integer() else str(valor)


def texto_do_toml(canal: Canal, raiz: str | None, encerramentos: list[str], logo: str) -> str:
    """O clipline.toml do canal novo, comentado. `raiz` None: a pasta acima do repositório (sem a chave)."""
    prefixo = canal.prefixo or slug(canal.nome)
    linha_raiz = (f"raiz = {_texto(raiz)}" if raiz is not None
                  else '# raiz = "D:/Canais/Meu Canal"     # sem a chave: a pasta acima do repositório')
    pastas = "\n".join(f"{chave} = {_texto(canal.pastas[chave])}" for chave in caminhos.PASTAS_PADRAO)
    lista = ", ".join(_texto(e) for e in encerramentos)
    return f"""# Configuração do canal, criada pelo clipline init. Todas as chaves: docs/configuracao.md.
# Outras seções (legenda, voz, youtube) estão comentadas em clipline.exemplo.toml.

[canal]
nome = {_texto(canal.nome)}
arroba = {_texto(canal.arroba)}             # vai no cartão de notícia e na sobreposição do encerramento
perfil_tiktok = {_texto(canal.perfil_tiktok)}

[duracao]
minima = {_numero(canal.duracao_minima)}                        # segundos; o validar recusa cortes fora da faixa
maxima = {_numero(canal.duracao_maxima)}

[pastas]
# A raiz é relativa ao repositório; as outras, à raiz (caminho absoluto também vale).
{linha_raiz}
{pastas}

[identidade]
# Relativos à pasta de identidade. Um vídeo de encerramento por corte, em rodízio; [] = corte sem encerramento.
encerramentos = [{lista}]
logo = {_texto(logo)}       # PNG com fundo transparente: cartão de notícia e sobreposição
# sobreposicao = "Encerramentos/sobreposicao.png"
#   sem a chave: a esteira gera a imagem (logo + "SIGA @arroba") na primeira montagem; "" = nada por cima

[credenciais]
# Prefixo dos nomes no Gerenciador de Credenciais (chaves de IA, contas das redes, código do painel).
# Trocar depois de conectar as contas esconde o que já foi guardado: conecte de novo.
prefixo = {_texto(prefixo)}
"""


def raiz_no_toml(raiz: Path, automacao: Path) -> str | None:
    """None quando a raiz é a de sempre (a pasta acima do repositório); senão, o caminho absoluto com barras."""
    raiz, automacao = Path(os.path.abspath(raiz)), Path(automacao)
    return None if raiz == automacao.parent else raiz.as_posix()


# --- gravação ----------------------------------------------------------------------------------------------------


def _criar_pasta(pasta: Path, relatorio: Relatorio) -> None:
    if pasta.is_dir():
        relatorio.anotar("já existe", pasta)
        return
    pasta.mkdir(parents=True)
    relatorio.anotar("criada", pasta)


def _copiar_contexto(destino: Path, exemplo: Path, relatorio: Relatorio) -> None:
    """Copia o exemplo só para pasta nova ou vazia: regra de exemplo misturada com as do canal confundiria o agente."""
    if destino.is_dir() and any(destino.iterdir()):
        relatorio.anotar("já existe (mantida como está)", destino)
        return
    if not exemplo.is_dir():
        _criar_pasta(destino, relatorio)
        relatorio.anotar("sem modelo para copiar", exemplo)
        return
    destino.mkdir(parents=True, exist_ok=True)
    for arquivo in sorted(exemplo.rglob("*")):
        alvo = destino / arquivo.relative_to(exemplo)
        if arquivo.is_dir():
            alvo.mkdir(exist_ok=True)
        elif not alvo.exists():
            shutil.copy2(arquivo, alvo)
    relatorio.anotar(f"criada com o modelo de {exemplo.name}/", destino)


def pastas_do_canal(raiz: Path, nomes: dict[str, str], automacao: Path) -> caminhos.Pastas:
    """As pastas que o init cria, conferidas pelas mesmas regras do clipline.toml (programas fora dos cortes etc.)."""
    return caminhos.resolver({"pastas": {"raiz": Path(raiz).as_posix(), **nomes}}, {}, automacao)


def iniciar(
    raiz: Path, canal: Canal | None, automacao: Path = AUTOMACAO, exemplo: Path = EXEMPLO_CONTEXTO,
    nomes: dict[str, str] | None = None,
) -> Relatorio:
    """Cria o que falta do canal em `raiz`. `canal` None: o clipline.toml já existe e não é escrito; as pastas
    seguem `nomes` (padrão: os de sempre)."""
    raiz, automacao = Path(os.path.abspath(raiz)), Path(automacao)
    if raiz == automacao or raiz.is_relative_to(automacao):
        raise ErroInit(f"a pasta do canal não pode ficar dentro do repositório ({automacao}); use a pasta acima dele")
    if canal is not None:
        problemas = conferir(canal)
        if problemas:
            raise ErroInit("; ".join(problemas))
        nomes = canal.pastas
    pastas = pastas_do_canal(raiz, nomes or dict(caminhos.PASTAS_PADRAO), automacao)
    arquivo = automacao / "clipline.toml"

    relatorio = Relatorio()
    _criar_pasta(raiz, relatorio)
    _copiar_contexto(pastas.contexto, exemplo, relatorio)
    for pasta in (pastas.programas, pastas.cortes, pastas.identidade):
        _criar_pasta(pasta, relatorio)
    for nome in SUBPASTAS_DA_IDENTIDADE:
        _criar_pasta(pastas.identidade / nome, relatorio)

    if canal is None:
        relatorio.anotar("já existe (mantido como está)", arquivo)
        return relatorio
    texto = texto_do_toml(canal, raiz_no_toml(raiz, automacao), encerramentos_encontrados(pastas.identidade),
                          logo_encontrada(pastas.identidade))
    caminhos.resolver(tomllib.loads(texto), {}, automacao)  # o arquivo gerado precisa ser válido
    try:
        with open(arquivo, "x", encoding="utf-8", newline="\n") as saida:  # "x": nunca sobrescreve
            saida.write(texto)
    except FileExistsError:
        relatorio.anotar("já existe (mantido como está)", arquivo)
        return relatorio
    relatorio.toml_criado = True
    relatorio.anotar("criado", arquivo)
    return relatorio


# --- conversa com quem roda ---------------------------------------------------------------------------------------


Perguntar = Callable[[str, str], str]


def perguntar_no_terminal(rotulo: str, padrao: str) -> str:
    """Pergunta com o padrão entre colchetes; Enter aceita o padrão. Sem terminal (EOF), fica o padrão."""
    try:
        resposta = input(f"{rotulo} [{padrao}]: ").strip()
    except EOFError:
        print()
        return padrao
    return resposta or padrao


def _numero_perguntado(perguntar: Perguntar, rotulo: str, padrao: float) -> float:
    for _ in range(3):
        resposta = perguntar(rotulo, _numero(padrao)).replace(",", ".")
        try:
            return float(resposta)
        except ValueError:
            print(f"  {resposta!r} não é um número.")
    raise ErroInit(f"{rotulo}: precisa ser um número de segundos")


def montar_canal(args, raiz: Path, perguntar: Perguntar | None) -> Canal:
    """O canal das flags; o que falta vem das perguntas (`perguntar`) ou, sem elas, dos padrões."""
    nome = args.canal or (perguntar("Nome do canal", nome_padrao(raiz)) if perguntar else nome_padrao(raiz))
    sugerida = arroba_padrao(nome)
    arroba = normalizar_arroba(args.arroba or (perguntar("Arroba nas redes", sugerida) if perguntar else sugerida))
    perfil = args.perfil_tiktok or (perguntar("Perfil do TikTok", perfil_padrao(arroba)) if perguntar
                                    else perfil_padrao(arroba))
    minima, maxima = args.duracao_minima, args.duracao_maxima
    if minima is None:
        minima = _numero_perguntado(perguntar, "Duração mínima do corte (s)", DURACAO_MINIMA) if perguntar else None
    if maxima is None:
        maxima = _numero_perguntado(perguntar, "Duração máxima do corte (s)", DURACAO_MAXIMA) if perguntar else None
    return Canal(nome=nome.strip(), arroba=arroba, perfil_tiktok=perfil.strip(),
                 duracao_minima=DURACAO_MINIMA if minima is None else float(minima),
                 duracao_maxima=DURACAO_MAXIMA if maxima is None else float(maxima),
                 prefixo=(args.prefixo_credenciais or "").strip(), pastas=nomes_das_pastas(args))


def nomes_das_pastas(args) -> dict[str, str]:
    return {chave: getattr(args, chave) or nome for chave, nome in caminhos.PASTAS_PADRAO.items()}


def proximos_passos(raiz: Path, nomes: dict[str, str], automacao: Path, toml_criado: bool) -> list[str]:
    windows = os.name == "nt"
    python = r".venv\Scripts\python.exe" if windows else ".venv/bin/python"
    clipline = r".venv\Scripts\clipline.exe" if windows else ".venv/bin/clipline"
    pastas = pastas_do_canal(raiz, nomes, automacao)
    passos = []
    if not (Path(automacao) / ".venv").is_dir():
        criar = "py -3.12 -m venv .venv" if windows else "python3.12 -m venv .venv"
        passos.append(f"Ambiente Python, na pasta do repositório ({automacao}):\n"
                      f"       {criar}\n"
                      f'       {python} -m pip install -e ".[painel,dev]"')
    if toml_criado:
        passos.append(f"Confira o clipline.toml ({Path(automacao) / 'clipline.toml'}).")
    passos.append(f"Reescreva as regras do canal em {pastas.contexto} (o código só lê o glossario.md).")
    passos.append(f"Ponha a logo (PNG transparente) em {pastas.identidade / 'Logos'} e, se quiser encerramento, "
                  f"os vídeos em {pastas.identidade / 'Encerramentos'}, listados em [identidade] encerramentos.")
    if pastas.raiz != Path(automacao).parent or nomes != caminhos.PASTAS_PADRAO:
        passos.append("Claude Code: troque as pastas de permissions.additionalDirectories em .claude/settings.json "
                      f"(ou ponha em .claude/settings.local.json) por {pastas.contexto}, {pastas.cortes}, "
                      f"{pastas.programas} e {pastas.identidade}.")
    passos.append(f"Confira o ambiente: {clipline} doctor")
    passos.append(f'Primeiro episódio: {clipline} transcrever "{pastas.programas / "<vídeo>.mp4"}" '
                  '--quadro "<quadro>" --numero 1 --convidado "<convidado>"')
    return passos


def _raiz_padrao(automacao: Path) -> Path:
    """A raiz em uso (CLIPLINE_RAIZ ou clipline.toml); sem nenhum dos dois, a pasta acima do repositório."""
    try:
        return caminhos.carregar(Path(automacao) / "clipline.toml", automacao=automacao).raiz
    except caminhos.ErroPastas:
        return Path(automacao).parent


def executar(args, perguntar: Perguntar | None = perguntar_no_terminal, automacao: Path | None = None,
             exemplo: Path | None = None) -> int:
    """`automacao` e `exemplo` lidos na hora (AUTOMACAO e EXEMPLO_CONTEXTO deste módulo): os testes trocam os dois."""
    automacao = Path(automacao or AUTOMACAO)
    exemplo = Path(exemplo or EXEMPLO_CONTEXTO)
    perguntar = None if args.sem_perguntas else perguntar
    try:
        if args.pasta:
            raiz = Path(args.pasta).expanduser()
        elif perguntar:
            raiz = Path(perguntar("Pasta do canal", str(_raiz_padrao(automacao)))).expanduser()
        else:
            raiz = _raiz_padrao(automacao)
        raiz = Path(os.path.abspath(raiz))
        toml_existe = (Path(automacao) / "clipline.toml").exists()
        if toml_existe:
            print("O clipline.toml já existe: só as pastas que faltam serão criadas.")
        canal = None if toml_existe else montar_canal(args, raiz, perguntar)
        nomes = nomes_das_pastas(args)
        relatorio = iniciar(raiz, canal, automacao, exemplo, nomes=nomes)
    except (ErroInit, caminhos.ErroPastas, OSError) as erro:
        print(f"Erro: {erro}", file=sys.stderr)
        return 1
    print(f"\nCanal em {raiz}")
    for estado, caminho in relatorio.linhas:
        mostrado = caminho.relative_to(raiz) if caminho != raiz and caminho.is_relative_to(raiz) else caminho
        print(f"  {estado}: {mostrado}")
    if toml_existe:
        _avisar_se_o_toml_aponta_outra_raiz(raiz, automacao)
    print("\nPróximos passos:")
    for numero, passo in enumerate(proximos_passos(raiz, nomes, automacao, relatorio.toml_criado), 1):
        print(f"  {numero}. {passo}")
    return 0


def _avisar_se_o_toml_aponta_outra_raiz(raiz: Path, automacao: Path) -> None:
    try:
        atual = caminhos.carregar(Path(automacao) / "clipline.toml", automacao=automacao)
    except caminhos.ErroPastas as erro:
        print(f"\nAviso: {erro}")
        return
    if atual.raiz != raiz:
        print(f"\nAviso: a configuração em uso aponta para {atual.raiz} ({atual.origem_raiz}). Para usar {raiz}, "
              f"ponha em [pastas] do clipline.toml: raiz = {_texto(raiz.as_posix())}")


def registrar(comandos) -> None:
    c = comandos.add_parser("init", aliases=["iniciar"], help="cria as pastas e o clipline.toml de um canal novo")
    c.add_argument("pasta", nargs="?", help="pasta do canal (padrão: a pasta acima do repositório)")
    c.add_argument("--canal", help="nome do canal")
    c.add_argument("--arroba", help="arroba nas redes, como @meucanal")
    c.add_argument("--perfil-tiktok", help="endereço do perfil no TikTok")
    c.add_argument("--duracao-minima", type=float, help="segundos (padrão 60)")
    c.add_argument("--duracao-maxima", type=float, help="segundos (padrão 120)")
    for chave, nome in caminhos.PASTAS_PADRAO.items():
        c.add_argument(f"--{chave}", help=f'nome da pasta de {chave}, relativo à pasta do canal (padrão "{nome}")')
    c.add_argument("--prefixo-credenciais", help="prefixo no Gerenciador de Credenciais (padrão: tirado do nome)")
    c.add_argument("--sem-perguntas", action="store_true", help="não pergunta nada: usa as flags e os padrões")
    c.set_defaults(funcao=executar)


def principal(argv: list[str] | None = None) -> int:
    """Entrada do `python -m esteira init` sem as dependências da esteira instaladas."""
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="esteira")
    registrar(parser.add_subparsers(required=True))
    args = parser.parse_args(argv)
    return args.funcao(args)
