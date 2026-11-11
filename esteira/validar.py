from esteira import config
from esteira.modelos import Corte, Palavra
from esteira.musica import CLIMAS_VALIDOS

DURACAO_MIN = 60
DURACAO_MAX = 120
TOLERANCIA = 0.25
INTERVALO_DE_FRASE = 0.7


def _termina_frase(palavra: Palavra) -> bool:
    return palavra.texto.rstrip('"”\'').endswith((".", "?", "!"))


def validar_trecho(palavras: list[Palavra], corte: Corte, duracao_video: float) -> list[str]:
    problemas: list[str] = []
    if corte.inicio < 0 or corte.fim > duracao_video:
        problemas.append("tempos fora da duração do vídeo")
    minimo, maximo = config.atual().duracao_minima, config.atual().duracao_maxima  # padrão: 60 e 120 (clipline.toml)
    if not minimo <= corte.fim - corte.inicio <= maximo:
        problemas.append(f"duração fora de {minimo:g} a {maximo:g} segundos")
    if corte.clima not in CLIMAS_VALIDOS:
        problemas.append(f"clima fora de {', '.join(CLIMAS_VALIDOS)}")

    indices = [
        i for i, p in enumerate(palavras)
        if p.fim > corte.inicio - TOLERANCIA and p.inicio < corte.fim + TOLERANCIA
    ]
    if not indices:
        return problemas + ["trecho sem palavras na transcrição"]

    primeira = min(indices, key=lambda i: abs(palavras[i].inicio - corte.inicio))
    ultima = min(indices, key=lambda i: abs(palavras[i].fim - corte.fim))
    if abs(palavras[primeira].inicio - corte.inicio) > TOLERANCIA:
        problemas.append("início não bate com uma palavra da transcrição")
    elif primeira > 0:
        anterior = palavras[primeira - 1]
        pausa = palavras[primeira].inicio - anterior.fim
        if not _termina_frase(anterior) and pausa <= INTERVALO_DE_FRASE:
            problemas.append("início no meio da frase")

    if abs(palavras[ultima].fim - corte.fim) > TOLERANCIA:
        problemas.append("fim não bate com uma palavra da transcrição")
    elif not _termina_frase(palavras[ultima]):
        pausa = palavras[ultima + 1].inicio - palavras[ultima].fim if ultima + 1 < len(palavras) else 99
        if pausa <= INTERVALO_DE_FRASE:
            problemas.append("fim no meio da frase")
    return problemas
