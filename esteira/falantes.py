"""Quem fala cada palavra: junta a transcrição (palavras.json) com a diarização (vozes.json).

Lógica pura. Serve à transcrição com falantes (texto-falantes.md) e ao comando `trecho`, que entrega ao agente
só o intervalo que ele precisa, em vez do palavras.json inteiro.
"""

from bisect import bisect_right

from esteira.enquadrar import TrechoVoz
from esteira.modelos import Palavra

PAUSA_MARCADA = 1.0  # segundos entre palavras para marcar [pausa]


def _tempo(segundos: float) -> str:
    decimos = round(segundos * 10)
    s, d = divmod(decimos, 10)
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}.{d}"


def rotular(palavras: list[Palavra], trechos: list[TrechoVoz]) -> list[str | None]:
    """A voz de cada palavra: a que mais se sobrepõe a ela (None se nenhuma)."""
    ordenados = sorted(trechos, key=lambda t: t.inicio)
    inicios = [t.inicio for t in ordenados]
    rotulos: list[str | None] = []
    for p in palavras:
        melhor, sobra = None, 0.0
        i = max(0, bisect_right(inicios, p.inicio) - 1)
        while i < len(ordenados) and ordenados[i].inicio < p.fim + 1e-9:
            t = ordenados[i]
            dentro = min(p.fim, t.fim) - max(p.inicio, t.inicio)
            if dentro > sobra:
                melhor, sobra = t.voz, dentro
            i += 1
        if melhor is None:  # palavra de duração zero ou fora de todo trecho: o trecho que contém o meio
            meio = (p.inicio + p.fim) / 2
            melhor = next((t.voz for t in ordenados if t.inicio <= meio <= t.fim), None)
        rotulos.append(melhor)
    return rotulos


def nome_da_voz(voz: str | None, ligacao: dict[str, str], nomes: dict[str, str]) -> str:
    if voz is None:
        return "?"
    pessoa = ligacao.get(voz)
    if pessoa and nomes.get(pessoa):
        return f"{voz} ({nomes[pessoa]})"
    return f"{voz} ({pessoa})" if pessoa else voz


def texto_com_falantes(
    palavras: list[Palavra], trechos: list[TrechoVoz], ligacao: dict[str, str] | None = None,
    nomes: dict[str, str] | None = None,
) -> str:
    """Uma linha por fala contínua: `[hh:mm:ss.d] V2 (Nome): texto`, com [pausa X s] onde há silêncio longo."""
    ligacao, nomes = ligacao or {}, nomes or {}
    rotulos = rotular(palavras, trechos)
    linhas: list[str] = []
    atual: list[str] = []
    voz_atual: object = object()
    for i, (p, voz) in enumerate(zip(palavras, rotulos)):
        if i and p.inicio - palavras[i - 1].fim >= PAUSA_MARCADA:
            atual.append(f"[pausa {p.inicio - palavras[i - 1].fim:.1f} s]".replace(".", ","))
        if voz != voz_atual:
            if atual:
                linhas.append(" ".join(atual))
            atual = [f"[{_tempo(p.inicio)}] {nome_da_voz(voz, ligacao, nomes)}:"]
            voz_atual = voz
        atual.append(p.texto)
    if atual:
        linhas.append(" ".join(atual))
    return "\n".join(linhas) + "\n"


def palavras_do_intervalo(palavras: list[Palavra], de: float, ate: float) -> list[tuple[int, Palavra]]:
    return [(i, p) for i, p in enumerate(palavras) if p.fim > de and p.inicio < ate]
