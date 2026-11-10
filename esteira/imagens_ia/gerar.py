import tempfile
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from esteira import caminhos
from esteira.cortar import IMAGENS_SUGERIDAS, TRABALHO
from esteira.fluxo_imagens import _ajustados, chave_momento, escrever_guia, ler_ia, registrar_ia
from esteira.imagens import preparar_foto
from esteira.imagens_ia.config import Config
from esteira.imagens_ia.provedor import ErroImagem, Provedor
from esteira.pedidos import Momento, _pessoa_citada, ler_pedidos
from esteira.receita import duracao_principal, ler_receita

MAXIMO_VERSOES = 3
JA_TEM_TODAS = f"Este momento já tem {MAXIMO_VERSOES} versões"


class ErroPrompt(ErroImagem):
    """O momento não pode gerar imagem (regra da esteira, antes de chamar o provedor)."""


class RegistroIncompleto(Exception):
    """A imagem foi paga e salva, mas o ia.json ou o guia não foram atualizados.

    Não é erro do momento: quem chama trata como aviso e conta o `arquivo` como gerado."""

    def __init__(self, arquivo: str, motivo: str) -> None:
        super().__init__(f"imagem salva, mas não consegui atualizar o registro: {motivo}")
        self.arquivo = arquivo


def _momentos(pasta_corte: Path) -> list[Momento]:
    return ler_pedidos(Path(pasta_corte) / TRABALHO)


def arquivo_de_versao(chave: str, versao: int) -> str:
    return f"{chave}-ia-{versao}.jpg"


def _tem_versao(pasta_corte: Path, chave: str, registradas: set[str]) -> bool:
    """Versão no ia.json ou arquivo no disco (R11): um arquivo sem registro também foi pago."""
    imagens = Path(pasta_corte) / IMAGENS_SUGERIDAS
    return chave in registradas or any(
        (imagens / arquivo_de_versao(chave, k)).exists() for k in range(1, MAXIMO_VERSOES + 1)
    )


def pendentes(pasta_corte: Path) -> list[Momento]:
    """Momentos de IA aprovados, com prompt e ainda sem nenhuma versão gerada."""
    try:
        momentos = _momentos(pasta_corte)
    except (OSError, ValueError, KeyError, TypeError):
        return []
    registradas = {i["momento"] for i in ler_ia(Path(pasta_corte) / TRABALHO) if isinstance(i.get("momento"), str)}
    return [
        m for m in momentos
        if m.tipo == "ia" and m.aprovado and not m.descartar and m.prompt.strip()
        and not _tem_versao(pasta_corte, chave_momento(m), registradas)
    ]


def _preco(imagens: int, config: Config) -> dict:
    dados = config.provedores[config.provedor]
    return {
        "imagens": imagens,
        "provedor": config.provedor,
        "modelo": dados.get("modelo", ""),
        "custo_usd": round(imagens * dados["preco_usd"], 4),
    }


def orcamento(pastas_corte: list[Path], config: Config) -> dict:
    return _preco(sum(len(pendentes(p)) for p in pastas_corte), config)


def orcamento_com_itens(cortes: list[tuple[int, Path]], config: Config) -> dict:
    """O orçamento e os itens contados (corte, chave): a lista exata que o dono confirma no painel."""
    itens = [{"corte": numero, "chave": chave_momento(m)} for numero, pasta in cortes for m in pendentes(pasta)]
    return {**_preco(len(itens), config), "itens": itens}


def _versao_livre(pasta_corte: Path, chave: str) -> int:
    usadas = {i.get("versao") for i in ler_ia(pasta_corte / TRABALHO) if i.get("momento") == chave}
    for k in range(1, MAXIMO_VERSOES + 1):
        if k not in usadas and not (pasta_corte / IMAGENS_SUGERIDAS / arquivo_de_versao(chave, k)).exists():
            return k
    raise ErroPrompt(JA_TEM_TODAS)


def _conferir(m: Momento | None, pessoas: list[str]) -> Momento:
    if m is None:
        raise ErroPrompt("Momento não encontrado")
    if m.tipo != "ia":
        raise ErroPrompt("Momento não é de IA")
    if m.descartar:
        raise ErroPrompt("Momento descartado")
    if not m.prompt.strip():
        raise ErroPrompt("Momento sem prompt")
    pessoa = _pessoa_citada(m.prompt, pessoas)
    if pessoa:
        raise ErroPrompt(f"Cita pessoa real ({pessoa}): não pode gerar")
    if not m.aprovado:
        raise ErroPrompt("Prompt não aprovado")
    return m


def _momentos_do_guia(pasta_corte: Path, momentos: list[Momento]) -> list[Momento]:
    try:
        duracao = duracao_principal(ler_receita(pasta_corte / TRABALHO))
    except (OSError, ValueError, KeyError, TypeError):
        return momentos
    return _ajustados(momentos, duracao)[0]


def gerar_momento(
    pasta_corte: Path,
    chave: str,
    provedor: Provedor,
    config: Config,
    pessoas: list[str],
    base: Path | None = None,
    agora: Callable[[], datetime] = datetime.now,
) -> str:
    pasta_corte = Path(pasta_corte)
    trabalho = pasta_corte / TRABALHO
    momentos = _momentos(pasta_corte)
    m = _conferir(next((x for x in momentos if chave_momento(x) == chave), None), pessoas)
    versao = _versao_livre(pasta_corte, chave)
    nome = arquivo_de_versao(chave, versao)
    saida = caminhos.garantir_escrita(pasta_corte / IMAGENS_SUGERIDAS / nome, base_extra=base)

    conteudo = provedor.gerar(m.prompt)
    saida.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temporaria:
        bruto = Path(temporaria) / "bruto"
        bruto.write_bytes(conteudo)
        try:
            preparar_foto(bruto, saida)
        except Exception:  # Pillow levanta vários tipos para bytes que não são imagem
            saida.unlink(missing_ok=True)
            raise ErroImagem("O provedor devolveu algo que não é uma imagem; nada foi guardado.") from None
    # A imagem já foi paga e está salva: daqui em diante nenhuma falha vira erro do momento.
    motivos = []
    try:
        registrar_ia(trabalho, {
            "arquivo": nome,
            "momento": chave,
            "versao": versao,
            "provedor": provedor.nome,
            "modelo": config.provedores.get(provedor.nome, {}).get("modelo", ""),
            "prompt": m.prompt,
            "data": agora().isoformat(timespec="seconds"),
        }, base=base)
    except Exception as erro:  # fronteira: o arquivo no disco já conta como versão (pendentes, R11)
        motivos.append(str(erro) or type(erro).__name__)
    try:
        escrever_guia(pasta_corte, momentos, _momentos_do_guia(pasta_corte, momentos))
    except Exception as erro:  # fronteira: o guia é refeito na próxima rodada
        motivos.append(str(erro) or type(erro).__name__)
    if motivos:
        raise RegistroIncompleto(nome, "; ".join(motivos))
    return nome


def gerar_cortes(
    pastas_corte: list[Path],
    provedor: Provedor,
    config: Config,
    pessoas: list[str],
    base: Path | None = None,
    progresso: Callable[[str], None] = lambda _: None,
    permitidos: set[tuple[Path, str]] | None = None,
) -> tuple[list[str], list[str]]:
    """Gera os pendentes; com `permitidos` (pasta do corte, chave), só os que o dono confirmou.

    `progresso` é chamado antes de cada imagem: se ele levantar, a próxima geração paga não começa."""
    lotes = [
        (Path(p), [m for m in pendentes(p) if permitidos is None or (Path(p), chave_momento(m)) in permitidos])
        for p in pastas_corte
    ]
    total = sum(len(ms) for _, ms in lotes)
    arquivos: list[str] = []
    avisos: list[str] = []
    i = 0
    for pasta, momentos in lotes:
        for m in momentos:
            i += 1
            progresso(f"Gerando {i} de {total}…")
            chave = chave_momento(m)
            try:
                arquivos.append(gerar_momento(pasta, chave, provedor, config, pessoas, base))
            except RegistroIncompleto as aviso:
                arquivos.append(aviso.arquivo)
                avisos.append(f"{pasta.name} {chave}: {aviso}")
            except (ErroImagem, OSError, ValueError) as erro:
                avisos.append(f"{pasta.name} {chave}: {erro}")
    return arquivos, avisos
