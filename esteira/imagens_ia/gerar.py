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


def _momentos(pasta_corte: Path) -> list[Momento]:
    return ler_pedidos(Path(pasta_corte) / TRABALHO)


def _chaves_com_versao(trabalho: Path) -> set[str]:
    return {i["momento"] for i in ler_ia(trabalho) if isinstance(i.get("momento"), str)}


def pendentes(pasta_corte: Path) -> list[Momento]:
    """Momentos de IA aprovados, com prompt e ainda sem nenhuma versão gerada."""
    try:
        momentos = _momentos(pasta_corte)
    except (OSError, ValueError, KeyError, TypeError):
        return []
    geradas = _chaves_com_versao(Path(pasta_corte) / TRABALHO)
    return [
        m for m in momentos
        if m.tipo == "ia" and m.aprovado and not m.descartar and m.prompt.strip() and chave_momento(m) not in geradas
    ]


def orcamento(pastas_corte: list[Path], config: Config) -> dict:
    imagens = sum(len(pendentes(p)) for p in pastas_corte)
    dados = config.provedores[config.provedor]
    return {
        "imagens": imagens,
        "provedor": config.provedor,
        "modelo": dados.get("modelo", ""),
        "custo_usd": round(imagens * dados["preco_usd"], 4),
    }


def _versao_livre(pasta_corte: Path, chave: str) -> int:
    usadas = {i.get("versao") for i in ler_ia(pasta_corte / TRABALHO) if i.get("momento") == chave}
    for k in range(1, MAXIMO_VERSOES + 1):
        if k not in usadas and not (pasta_corte / IMAGENS_SUGERIDAS / f"{chave}-ia-{k}.jpg").exists():
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
    nome = f"{chave}-ia-{versao}.jpg"
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
    registrar_ia(trabalho, {
        "arquivo": nome,
        "momento": chave,
        "versao": versao,
        "provedor": provedor.nome,
        "modelo": config.provedores.get(provedor.nome, {}).get("modelo", ""),
        "prompt": m.prompt,
        "data": agora().isoformat(timespec="seconds"),
    }, base=base)
    escrever_guia(pasta_corte, _momentos_do_guia(pasta_corte, momentos))
    return nome


def gerar_cortes(
    pastas_corte: list[Path],
    provedor: Provedor,
    config: Config,
    pessoas: list[str],
    base: Path | None = None,
    progresso: Callable[[str], None] = lambda _: None,
) -> tuple[list[str], list[str]]:
    lotes = [(Path(p), pendentes(p)) for p in pastas_corte]
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
            except (ErroImagem, OSError, ValueError) as erro:
                avisos.append(f"{pasta.name} {chave}: {erro}")
    return arquivos, avisos
