"""Contrato dos arquivos que o Claude Code (ou uma pessoa) escreve para a esteira.

Cada problema diz o arquivo, o caminho do campo e o que fazer, numa linha. É a resposta que o agente lê
depois de gravar: precisa ser curta e direta. Os mesmos formatos estão em docs/esquemas/*.schema.json.
"""

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from esteira.pedidos import ARQUIVO as PEDIDOS, TIPOS, Momento

APROVADOS = "aprovados.json"
MUSICAS_DO_EPISODIO = "musicas-do-episodio.json"
NOMES_SUSPEITOS = "nomes-suspeitos.json"

CAMPOS_CORTE = {"numero": int, "titulo": str, "inicio": float, "fim": float, "clima": str, "instagram": bool, "data": str}
OBRIGATORIOS_CORTE = ("numero", "titulo", "inicio", "fim", "clima")
CAMPOS_MOMENTO = set(Momento.__dataclass_fields__) | {"escolha", "numero"}  # os dois últimos: formato antigo
OBRIGATORIOS_MOMENTO = ("inicio", "fim", "fala", "tipo", "nome")
CAMPOS_ORIGEM = {"modelo", "data", "regras", "skill", "observacao"}
FORMATO_DATA = "AAAA-MM-DD HH:MM"


class ErroContrato(ValueError):
    """Arquivo fora do formato. Herda de ValueError: quem já trata ValueError continua tratando."""


@dataclass
class Problema:
    arquivo: str
    campo: str
    mensagem: str

    def __str__(self) -> str:
        return f"{self.arquivo}: {self.campo}: {self.mensagem}" if self.campo else f"{self.arquivo}: {self.mensagem}"

    def como_dict(self) -> dict:
        return asdict(self)


def _tipo_ok(valor, tipo) -> bool:
    if tipo is float:
        return isinstance(valor, (int, float)) and not isinstance(valor, bool)
    if tipo is int:
        return isinstance(valor, int) and not isinstance(valor, bool)
    return isinstance(valor, tipo)


_NOMES_DE_TIPO = {int: "número inteiro", float: "número", str: "texto", bool: "true ou false"}


def _ler_json(caminho: Path, nome: str) -> tuple[object, list[Problema]]:
    try:
        texto = caminho.read_text("utf-8")
    except FileNotFoundError:
        return None, [Problema(nome, "", "arquivo não encontrado")]
    except UnicodeDecodeError:
        return None, [Problema(nome, "", "não está em UTF-8; grave de novo em UTF-8")]
    except OSError as erro:
        return None, [Problema(nome, "", f"não consegui ler ({erro.strerror or erro})")]
    try:
        return json.loads(texto), []
    except json.JSONDecodeError as erro:
        return None, [Problema(nome, f"linha {erro.lineno}, coluna {erro.colno}", f"JSON inválido: {erro.msg}")]


def _origem(dados: dict, nome: str) -> list[Problema]:
    origem = dados.get("origem")
    if origem is None:
        return []
    if not isinstance(origem, dict):
        return [Problema(nome, "origem", "precisa ser um objeto com modelo, data e regras")]
    extras = sorted(set(origem) - CAMPOS_ORIGEM)
    return [Problema(nome, f"origem.{c}", f"campo desconhecido; aceitos: {', '.join(sorted(CAMPOS_ORIGEM))}") for c in extras]


def conferir_aprovados(dados: object, nome: str = APROVADOS, climas: tuple[str, ...] | None = None) -> list[Problema]:
    if not isinstance(dados, dict):
        return [Problema(nome, "", 'precisa ser um objeto: {"cortes": [...]}')]
    problemas = _origem(dados, nome)
    extras = sorted(set(dados) - {"cortes", "origem"})
    problemas += [Problema(nome, c, "campo desconhecido no nível de cima; aceitos: cortes, origem") for c in extras]
    cortes = dados.get("cortes")
    if not isinstance(cortes, list):
        return problemas + [Problema(nome, "cortes", "precisa ser uma lista de cortes")]
    numeros: set[int] = set()
    for i, corte in enumerate(cortes):
        base = f"cortes[{i}]"
        if not isinstance(corte, dict):
            problemas.append(Problema(nome, base, "precisa ser um objeto"))
            continue
        for campo in OBRIGATORIOS_CORTE:
            if campo not in corte:
                problemas.append(Problema(nome, f"{base}.{campo}", "campo obrigatório ausente"))
        for campo, valor in corte.items():
            tipo = CAMPOS_CORTE.get(campo)
            if tipo is None:
                problemas.append(Problema(nome, f"{base}.{campo}", f"campo desconhecido; aceitos: {', '.join(CAMPOS_CORTE)}"))
            elif not _tipo_ok(valor, tipo):
                problemas.append(Problema(nome, f"{base}.{campo}", f"precisa ser {_NOMES_DE_TIPO[tipo]}"))
        numero = corte.get("numero")
        if _tipo_ok(numero, int):
            if numero <= 0:
                problemas.append(Problema(nome, f"{base}.numero", "precisa ser maior que zero"))
            elif numero in numeros:
                problemas.append(Problema(nome, f"{base}.numero", f"número {numero} repetido"))
            numeros.add(numero)
        if _tipo_ok(corte.get("inicio"), float) and _tipo_ok(corte.get("fim"), float) and corte["fim"] <= corte["inicio"]:
            problemas.append(Problema(nome, f"{base}.fim", "precisa ser maior que inicio"))
        if climas and isinstance(corte.get("clima"), str) and corte["clima"] not in climas:
            problemas.append(Problema(nome, f"{base}.clima", f"use um destes: {', '.join(climas)}"))
        if isinstance(corte.get("titulo"), str) and not corte["titulo"].strip():
            problemas.append(Problema(nome, f"{base}.titulo", "não pode ser vazio"))
        data = corte.get("data")
        if isinstance(data, str) and data and not _data_valida(data):
            problemas.append(Problema(nome, f"{base}.data", f"use {FORMATO_DATA} (horário de Brasília)"))
    return problemas


def _data_valida(texto: str) -> bool:
    from datetime import datetime

    try:
        datetime.strptime(texto.strip(), "%Y-%m-%d %H:%M")
    except ValueError:
        return False
    return True


def conferir_pedidos(dados: object, nome: str = PEDIDOS) -> list[Problema]:
    if not isinstance(dados, dict):
        return [Problema(nome, "", 'precisa ser um objeto: {"momentos": [...]}')]
    problemas = _origem(dados, nome)
    momentos = dados.get("momentos")
    if not isinstance(momentos, list):
        return problemas + [Problema(nome, "momentos", "precisa ser uma lista de momentos")]
    for i, m in enumerate(momentos):
        base = f"momentos[{i}]"
        if not isinstance(m, dict):
            problemas.append(Problema(nome, base, "precisa ser um objeto"))
            continue
        for campo in OBRIGATORIOS_MOMENTO:
            if campo not in m:
                problemas.append(Problema(nome, f"{base}.{campo}", "campo obrigatório ausente"))
        for campo in sorted(set(m) - CAMPOS_MOMENTO):
            problemas.append(Problema(nome, f"{base}.{campo}", "campo desconhecido"))
        for campo in ("inicio", "fim"):
            if campo in m and not _tipo_ok(m[campo], float):
                problemas.append(Problema(nome, f"{base}.{campo}", "precisa ser um número (segundos no corte.mp4)"))
        for campo in ("fala", "nome", "busca", "titulo", "veiculo", "data", "prompt"):
            if campo in m and not isinstance(m[campo], str):
                problemas.append(Problema(nome, f"{base}.{campo}", "precisa ser texto"))
        if "tipo" in m and m["tipo"] not in TIPOS:
            problemas.append(Problema(nome, f"{base}.tipo", f"use um destes: {', '.join(TIPOS)}"))
        if "escolhas" in m and not (isinstance(m["escolhas"], list) and all(_tipo_ok(e, int) for e in m["escolhas"])):
            problemas.append(Problema(nome, f"{base}.escolhas", "precisa ser uma lista de números inteiros"))
    return problemas


def conferir_musicas_do_episodio(dados: object, catalogo: set[str] | None, nome: str = MUSICAS_DO_EPISODIO) -> list[Problema]:
    if not isinstance(dados, dict) or not isinstance(dados.get("faixas"), list):
        return [Problema(nome, "faixas", 'precisa ser {"faixas": [{"arquivo": "clima/nome.mp3", "motivo": "..."}]}')]
    problemas = []
    for i, f in enumerate(dados["faixas"]):
        base = f"faixas[{i}]"
        if not isinstance(f, dict) or not isinstance(f.get("arquivo"), str):
            problemas.append(Problema(nome, f"{base}.arquivo", "precisa ser texto no formato clima/nome.mp3"))
            continue
        if catalogo is not None and f["arquivo"] not in catalogo:
            problemas.append(Problema(nome, f"{base}.arquivo", f"faixa fora do musicas/catalogo.json: {f['arquivo']}"))
        if "motivo" in f and not isinstance(f["motivo"], str):
            problemas.append(Problema(nome, f"{base}.motivo", "precisa ser texto"))
    return problemas


def conferir_nomes_suspeitos(dados: object, numeros: set[int], nome: str = NOMES_SUSPEITOS) -> list[Problema]:
    if not isinstance(dados, dict):
        return [Problema(nome, "", 'precisa ser um objeto: {"4": ["Massa: conferir \'Felipe Massa\'"]}')]
    problemas = []
    for chave, lista in dados.items():
        if not str(chave).isdigit() or int(chave) not in numeros:
            problemas.append(Problema(nome, str(chave), "a chave precisa ser o número de um corte do aprovados.json"))
        if not isinstance(lista, list) or not all(isinstance(x, str) for x in lista):
            problemas.append(Problema(nome, str(chave), "precisa ser uma lista de textos"))
    return problemas


def ler_validado(caminho: Path, conferir, nome: str):
    """Lê o JSON e confere o formato; ErroContrato com todos os problemas numa mensagem só."""
    dados, problemas = _ler_json(Path(caminho), nome)
    if not problemas:
        problemas = conferir(dados, nome)
    if problemas:
        raise ErroContrato("; ".join(str(p) for p in problemas[:5]) + (f" (e mais {len(problemas) - 5})" if len(problemas) > 5 else ""))
    return dados


def conferir_episodio(pasta: Path, climas: tuple[str, ...] | None = None, catalogo: set[str] | None = None) -> list[Problema]:
    """Todos os arquivos do agente na pasta do episódio e nas pastas dos cortes."""
    pasta = Path(pasta)
    dados, problemas = _ler_json(pasta / APROVADOS, APROVADOS)
    numeros: set[int] = set()
    if not problemas:
        problemas = conferir_aprovados(dados, climas=climas)
        if not problemas:
            numeros = {c["numero"] for c in dados["cortes"]}
            from esteira.cortar import ler_aprovados, pasta_do_corte

            for corte in ler_aprovados(pasta):
                arquivo = pasta_do_corte(pasta, corte) / "trabalho" / PEDIDOS
                if arquivo.exists():
                    rotulo = f"{arquivo.parent.parent.name}/trabalho/{PEDIDOS}"
                    lidos, erros = _ler_json(arquivo, rotulo)
                    problemas += erros or conferir_pedidos(lidos, rotulo)
    for nome, conferir in (
        (MUSICAS_DO_EPISODIO, lambda d, n: conferir_musicas_do_episodio(d, catalogo, n)),
        (NOMES_SUSPEITOS, lambda d, n: conferir_nomes_suspeitos(d, numeros, n)),
    ):
        if (pasta / nome).exists():
            lidos, erros = _ler_json(pasta / nome, nome)
            problemas += erros or conferir(lidos, nome)
    return problemas
