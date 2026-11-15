"""Pastas e arquivos do canal.

Sem configuração, valem as pastas de sempre, irmãs do repositório: `Contexto`, `1 - Programas`, `2 - Cortes` e
`3 - Identidade`. A seção `[pastas]` do `clipline.toml` e a variável de ambiente `CLIPLINE_RAIZ` mudam onde elas
ficam; `[identidade]` muda os vídeos de encerramento, a logo e a sobreposição. Todas as chaves: docs/configuracao.md.

`config.py` importa este módulo, então as duas seções são lidas aqui mesmo, com tomllib, sem depender de `config`.
Tudo é calculado uma vez, na importação: as constantes abaixo (e os valores padrão que os outros módulos tiram
delas) já nascem com o configurado.
"""

import os
import re
import tomllib
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

AUTOMACAO = Path(__file__).resolve().parent.parent
ARQUIVO_CONFIG = AUTOMACAO / "clipline.toml"
VARIAVEL_RAIZ = "CLIPLINE_RAIZ"
# [pastas]: nome padrão de cada pasta, relativo à raiz.
PASTAS_PADRAO = {
    "contexto": "Contexto", "programas": "1 - Programas", "cortes": "2 - Cortes", "identidade": "3 - Identidade",
}
# [identidade]: relativos à pasta de identidade. Os padrões são os do canal original.
ENCERRAMENTOS_PADRAO = tuple(
    f"Encerramentos/Final Corte ({nome}).mp4" for nome in ("Gabriel 1", "Tigas 1", "Gabriel 2", "Tigas 2")
)
LOGO_PADRAO = "Logos/Logo sem Fundo.png"
CHAVES_PASTAS = ("raiz", *PASTAS_PADRAO)
CHAVES_IDENTIDADE = ("encerramentos", "logo", "sobreposicao")


class ErroPastas(ValueError):
    """[pastas] ou [identidade] do clipline.toml com chave, tipo ou combinação de pastas errados."""


@dataclass(frozen=True)
class Pastas:
    raiz: Path
    origem_raiz: str  # "padrão" (a pasta acima do repositório), "clipline.toml" ou "CLIPLINE_RAIZ"
    contexto: Path
    programas: Path
    cortes: Path
    identidade: Path
    encerramentos: tuple[Path, ...]  # vazio: corte sem encerramento
    logo: Path
    sobreposicao: Path | None  # None: nada por cima do encerramento


def _secao(dados: Mapping, nome: str, aceitas: tuple[str, ...]) -> Mapping:
    secao = dados.get(nome, {})
    if not isinstance(secao, Mapping):
        raise ErroPastas(f"clipline.toml: [{nome}] precisa ser uma seção")
    desconhecidas = sorted(set(secao) - set(aceitas))
    if desconhecidas:
        raise ErroPastas(f"clipline.toml: [{nome}] {desconhecidas[0]} não existe; aceitas: {', '.join(aceitas)}")
    return secao


def _texto(secao: str, chave: str, valor) -> str:
    if not isinstance(valor, str) or not valor.strip():
        raise ErroPastas(f"clipline.toml: [{secao}] {chave} precisa ser um caminho entre aspas")
    return valor.strip()


def _juntar(base: Path, caminho: str) -> Path:
    """`caminho` relativo a `base` (absoluto fica como está), com `..` resolvido sem seguir atalhos."""
    return Path(os.path.abspath(Path(base) / Path(caminho).expanduser()))


def _dentro(pasta: Path, base: Path) -> bool:
    return pasta == base or pasta.is_relative_to(base)


def _encerramentos(identidade: Mapping, pasta: Path) -> tuple[Path, ...]:
    if "encerramentos" not in identidade:
        return tuple(pasta / nome for nome in ENCERRAMENTOS_PADRAO)
    lista = identidade["encerramentos"]
    if not isinstance(lista, list) or not all(isinstance(item, str) and item.strip() for item in lista):
        raise ErroPastas(
            "clipline.toml: [identidade] encerramentos precisa ser uma lista de caminhos, "
            'como ["Encerramentos/fim.mp4"] ([] tira o encerramento)'
        )
    return tuple(_juntar(pasta, item.strip()) for item in lista)


def _sobreposicao(identidade: Mapping, pasta: Path, automacao: Path) -> Path | None:
    if "sobreposicao" not in identidade:
        return automacao / "assets" / "encerramento.png"
    valor = identidade["sobreposicao"]
    if not isinstance(valor, str):
        raise ErroPastas('clipline.toml: [identidade] sobreposicao precisa ser um caminho entre aspas ("" tira)')
    return _juntar(pasta, valor.strip()) if valor.strip() else None


def resolver(dados: Mapping, ambiente: Mapping[str, str], automacao: Path = AUTOMACAO) -> Pastas:
    """Pura: o clipline.toml já lido e as variáveis de ambiente viram as pastas do canal.

    A raiz vem de CLIPLINE_RAIZ, de [pastas] raiz ou, sem nenhum dos dois, da pasta acima do repositório. Caminho
    relativo na raiz vale a partir do repositório; nas outras pastas, a partir da raiz; em [identidade], a partir da
    pasta de identidade.
    """
    automacao = Path(automacao)
    pastas = _secao(dados, "pastas", CHAVES_PASTAS)
    identidade = _secao(dados, "identidade", CHAVES_IDENTIDADE)
    if ambiente.get(VARIAVEL_RAIZ, "").strip():
        raiz, origem = _juntar(automacao, ambiente[VARIAVEL_RAIZ].strip()), VARIAVEL_RAIZ
    elif "raiz" in pastas:
        raiz, origem = _juntar(automacao, _texto("pastas", "raiz", pastas["raiz"])), "clipline.toml"
    else:
        raiz, origem = automacao.parent, "padrão"

    def pasta(chave: str) -> Path:
        if chave not in pastas:
            return raiz / PASTAS_PADRAO[chave]
        return _juntar(raiz, _texto("pastas", chave, pastas[chave]))

    cortes, programas, pasta_identidade = pasta("cortes"), pasta("programas"), pasta("identidade")
    fonte = VARIAVEL_RAIZ if origem == VARIAVEL_RAIZ else "clipline.toml"
    for nome, protegida in (("programas", programas), ("identidade", pasta_identidade)):
        # A esteira grava na pasta de cortes e no repositório: as pastas do dono não podem ficar dentro deles.
        if _dentro(protegida, cortes) or _dentro(protegida, automacao):
            raise ErroPastas(
                f"{fonte}: a pasta de {nome} ({protegida}) não pode ficar dentro da de cortes nem do repositório"
            )
    logo = pasta_identidade / LOGO_PADRAO
    if "logo" in identidade:
        logo = _juntar(pasta_identidade, _texto("identidade", "logo", identidade["logo"]))
    return Pastas(
        raiz=raiz,
        origem_raiz=origem,
        contexto=pasta("contexto"),
        programas=programas,
        cortes=cortes,
        identidade=pasta_identidade,
        encerramentos=_encerramentos(identidade, pasta_identidade),
        logo=logo,
        sobreposicao=_sobreposicao(identidade, pasta_identidade, automacao),
    )


def ler_toml(arquivo: Path = ARQUIVO_CONFIG) -> dict:
    """O clipline.toml como dicionário. Sem o arquivo, {}."""
    try:
        return tomllib.loads(Path(arquivo).read_text("utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as erro:
        raise ErroPastas(f"clipline.toml ilegível: {erro}") from None


def carregar(
    arquivo: Path = ARQUIVO_CONFIG, ambiente: Mapping[str, str] | None = None, automacao: Path = AUTOMACAO
) -> Pastas:
    return resolver(ler_toml(arquivo), os.environ if ambiente is None else ambiente, automacao)


def _na_importacao() -> tuple[Pastas, str | None]:
    try:
        return carregar(), None
    except ErroPastas as erro:
        # Com a configuração quebrada, garantir_escrita recusa tudo e a CLI para; doctor e init ainda rodam.
        return resolver({}, {}), str(erro)


PASTAS, ERRO_CONFIG = _na_importacao()
RAIZ = PASTAS.raiz
CONTEXTO = PASTAS.contexto
PROGRAMAS = PASTAS.programas
CORTES = PASTAS.cortes
IDENTIDADE = PASTAS.identidade
BIN = AUTOMACAO / "bin"
MUSICAS = AUTOMACAO / "musicas"
FONTES = AUTOMACAO / "assets" / "fonts"
ENCERRAMENTOS = list(PASTAS.encerramentos)
SOBREPOSICAO_PADRAO = AUTOMACAO / "assets" / "encerramento.png"
SOBREPOSICAO = PASTAS.sobreposicao
LOGO = PASTAS.logo


def sobreposicao_do_canal(arroba: str, arroba_original: str) -> Path | None:
    """A imagem por cima do encerramento: a de [identidade] sobreposicao ou, sem a chave, a que a esteira gera da logo
    e da arroba. Para a arroba do canal original é o assets/encerramento.png do repositório (como sempre); para as
    outras, assets/encerramento-<arroba>.png, fora do git, para um canal novo nunca herdar a logo do original."""
    if SOBREPOSICAO != SOBREPOSICAO_PADRAO or arroba == arroba_original:
        return SOBREPOSICAO
    sem_acento = unicodedata.normalize("NFKD", arroba).encode("ascii", "ignore").decode()
    nome = re.sub(r"[^a-z0-9]+", "-", sem_acento.lower()).strip("-") or "canal"
    return AUTOMACAO / "assets" / f"encerramento-{nome}.png"


def gravar_atomico(caminho: Path, texto: str, newline: str | None = None) -> None:
    """Grava num .tmp ao lado e troca de uma vez: uma queda no meio nunca deixa o arquivo pela metade."""
    caminho = Path(caminho)
    temporario = caminho.with_name(caminho.name + ".tmp")
    try:
        temporario.write_text(texto, "utf-8", newline=newline)
        temporario.replace(caminho)
    finally:
        temporario.unlink(missing_ok=True)


class EscritaProibida(Exception):
    pass


def garantir_escrita(caminho: Path, base_extra: Path | None = None) -> Path:
    if ERRO_CONFIG:
        raise EscritaProibida(f"{ERRO_CONFIG}. Corrija o clipline.toml: nada foi gravado.")
    resolvido = Path(caminho).resolve()
    bases = [CORTES.resolve(), AUTOMACAO.resolve()]
    if base_extra is not None:
        bases.append(Path(base_extra).resolve())
    if not any(resolvido.is_relative_to(base) for base in bases):
        raise EscritaProibida(f"Escrita fora de {CORTES.name}/ e Automacao/: {resolvido}")
    return resolvido
