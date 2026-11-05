"""Comando `planos`: vozes + rostos -> ligação voz/pessoa -> enquadramento de cada corte.

Grava `transcricao/pessoas.json`, `transcricao/pessoas.jpg` e, por corte,
`trabalho/enquadramento.json`, `trabalho/alertas-planos.json` e `trabalho/planos.jpg`.
Os tempos dos alertas são relativos ao início do corte (linha do episódio, antes da
limpeza de pausas).
"""

import json
from pathlib import Path

from esteira import rostos
from esteira.cortar import TRABALHO, ler_aprovados, pasta_de_trabalho, pasta_do_corte
from esteira.enquadrar import Cena, Rosto, TrechoVoz, _mmss, enquadrar_cena, falante_em
from esteira.midia import ErroMidia
from esteira.modelos import Corte, Palavra
from esteira.pessoas import folha_pessoas, gravar_pessoas, ler_pessoas, ligar
from esteira.planos import Plano, gerar_folha, gravar_planos, ler_planos, limites_de_cena
from esteira.transcrever import ler_palavras
from esteira.vozes import ErroVozes, ler_vozes

ALERTAS = "alertas-planos.json"
MANTIDO = "mantido (já existe)"
PALAVRAS_NO_ROTULO = 6
TOLERANCIA_CAIXA = 0.05  # distância horizontal máxima entre o plano e o rosto da caixa
ERROS = (ErroMidia, OSError, ValueError)


def _tempo_de_fala(vozes: list[TrechoVoz], cortes: list[Corte]) -> dict[str, float]:
    tempos: dict[str, float] = {}
    for corte in cortes:
        for trecho in vozes:
            dentro = min(corte.fim, trecho.fim) - max(corte.inicio, trecho.inicio)
            if dentro > 0:
                tempos[trecho.voz] = tempos.get(trecho.voz, 0.0) + dentro
    return tempos


def _amostras(deteccoes: list[rostos.Deteccao], pessoas: list[str]) -> dict[str, tuple[float, Rosto]]:
    """Por pessoa, a detecção de maior altura (rosto mais nítido)."""
    melhores: dict[str, rostos.Deteccao] = {}
    for det, pessoa in zip(deteccoes, pessoas):
        if pessoa not in melhores or det.altura > melhores[pessoa].altura:
            melhores[pessoa] = det
    return {
        p: (d.tempo, Rosto(p, d.x, d.y, d.largura, d.altura)) for p, d in melhores.items()
    }


def _relativo_ao_corte(alerta: str, deslocamento: float) -> str:
    """'MM:SS texto' relativo à cena -> relativo ao corte."""
    tempo, _, texto = alerta.partition(" ")
    minutos, segundos = tempo.split(":")
    return f"{_mmss(int(minutos) * 60 + int(segundos) + deslocamento)} {texto}"


def _caixa(plano: Plano, cenas: list[Cena]) -> tuple[float, float, float, float] | None:
    meio = (plano.inicio + plano.fim) / 2
    cena = next((c for c in cenas if c.inicio <= meio < c.fim), None)
    if cena is None or not cena.rostos or plano.zoom <= 1.0 and len(cena.rostos) > 1:
        return None
    rosto = min(cena.rostos, key=lambda r: abs(r.x - plano.x))
    if abs(rosto.x - plano.x) > TOLERANCIA_CAIXA:
        return None
    return rosto.x, rosto.y, rosto.largura, rosto.altura


def _rotulo(
    numero: int, plano: Plano, vozes: list[TrechoVoz], ligacao: dict[str, str],
    nomes: dict[str, str], palavras: list[Palavra],
) -> str:
    voz = falante_em(vozes, plano.inicio, plano.fim)
    pessoa = ligacao.get(voz) if voz else None
    quem = nomes.get(pessoa) or pessoa or voz or "sem voz"
    texto = [p.texto for p in palavras if plano.inicio <= p.inicio < plano.fim][:PALAVRAS_NO_ROTULO]
    return f"{numero} {quem} · {' '.join(texto)}".rstrip(" ·")


def _ligacao(
    vozes: list[TrechoVoz], cenas: list[Cena], existente, assinaturas: dict[str, list[float]], forcar: bool,
) -> tuple[dict[str, str], dict[str, list[float]], dict[str, str]]:
    """Sem `forcar`, um pessoas.json existente manda: ligação, nomes e assinaturas dele
    ficam como estão e só entram as assinaturas de pessoas novas. Com `forcar`, a
    ligação é recalculada; os nomes continuam (as pessoas guardam o mesmo código)."""
    if existente is None:
        return ligar(vozes, cenas), assinaturas, {}
    ligacao_antiga, assinaturas_antigas, nomes = existente
    if forcar:
        return ligar(vozes, cenas), assinaturas, nomes
    novas = {p: s for p, s in assinaturas.items() if p not in assinaturas_antigas}
    return ligacao_antiga, {**assinaturas_antigas, **novas}, nomes


def _alertas_de_ligacao(vozes: list[TrechoVoz], corte: Corte, ligacao: dict[str, str]) -> list[str]:
    if not ligacao:
        return ["nenhuma voz ligada a uma pessoa, confira pessoas.jpg"]
    faltando = sorted(v for v in _tempo_de_fala(vozes, [corte]) if v not in ligacao)
    return [f"vozes sem pessoa: {', '.join(faltando)}, confira pessoas.jpg"] if faltando else []


def _enquadrar_corte(
    corte: Corte, cenas: list[Cena], vozes: list[TrechoVoz], ligacao: dict[str, str]
) -> tuple[list[Plano], list[str]]:
    planos: list[Plano] = []
    alertas: list[str] = []
    for cena in cenas:
        novos, avisos = enquadrar_cena(cena, vozes, ligacao)
        planos += novos
        alertas += [_relativo_ao_corte(a, cena.inicio - corte.inicio) for a in avisos]
    return planos, alertas + _alertas_de_ligacao(vozes, corte, ligacao)


def planejar_episodio(
    pasta: Path, numeros: set[int] | None, forcar: bool = False, detectar=rostos.detectar
) -> dict[int, str]:
    pasta = Path(pasta)
    video = Path(json.loads((pasta / "episodio.json").read_text("utf-8"))["video"])
    try:
        vozes = ler_vozes(pasta)
    except ErroVozes as erro:
        return {0: f"erro: {erro}"}
    try:
        palavras = ler_palavras(pasta)
    except FileNotFoundError:
        palavras = []

    cortes = [c for c in ler_aprovados(pasta) if numeros is None or c.numero in numeros]
    resultados: dict[int, str] = {}
    lidos: list[tuple[Corte, list[float], list[rostos.Deteccao]]] = []
    for corte in cortes:
        try:
            limites = limites_de_cena(video, corte.inicio, corte.fim)
            lidos.append((corte, limites, detectar(video, corte.inicio, corte.fim)))
        except ERROS as erro:
            resultados[corte.numero] = f"erro: {erro}"

    existente = ler_pessoas(pasta)
    todas = [d for _, _, deteccoes in lidos for d in deteccoes]
    pessoas, assinaturas = rostos.agrupar(todas, existente[1] if existente else {})
    cenas_por_corte: dict[int, list[Cena]] = {}
    inicio = 0
    for corte, limites, deteccoes in lidos:
        fim = inicio + len(deteccoes)
        cenas_por_corte[corte.numero] = rostos.cenas_com_rostos(deteccoes, pessoas[inicio:fim], limites)
        inicio = fim

    todas_as_cenas = [c for cenas in cenas_por_corte.values() for c in cenas]
    ligacao, assinaturas, nomes = _ligacao(vozes, todas_as_cenas, existente, assinaturas, forcar)
    gravar_pessoas(pasta, ligacao, assinaturas, nomes)
    amostras = _amostras(todas, pessoas)
    if amostras:
        tempo_de_fala = _tempo_de_fala(vozes, [corte for corte, _, _ in lidos])
        folha_pessoas(video, amostras, ligacao, tempo_de_fala, nomes, pasta / "transcricao" / "pessoas.jpg")

    for corte, _, _ in lidos:
        cenas = cenas_por_corte[corte.numero]
        destino = pasta_do_corte(pasta, corte)
        try:
            if (destino / TRABALHO / "enquadramento.json").exists() and not forcar:
                planos = ler_planos(destino / TRABALHO)
                resultado = MANTIDO
            else:
                planos, alertas = _enquadrar_corte(corte, cenas, vozes, ligacao)
                trabalho = pasta_de_trabalho(destino)
                gravar_planos(trabalho, planos)
                (trabalho / ALERTAS).write_text(json.dumps(alertas, ensure_ascii=False, indent=1), "utf-8")
                resultado = f"ok com alertas: {'; '.join(alertas)}" if alertas else "ok"
            rotulos = [_rotulo(i + 1, p, vozes, ligacao, nomes, palavras) for i, p in enumerate(planos)]
            caixas = [_caixa(p, cenas) for p in planos]
            gerar_folha(video, planos, pasta_de_trabalho(destino) / "planos.jpg", rotulos, caixas)
        except ERROS as erro:
            resultado = f"erro: {erro}"
        resultados[corte.numero] = resultado
    return dict(sorted(resultados.items()))
