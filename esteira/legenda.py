import re
import unicodedata
from dataclasses import replace
from pathlib import Path

from esteira.limpeza import remapear
from esteira.modelos import Cue, Palavra

MAX_PALAVRAS = 6
MIN_PALAVRAS = 3
MAX_CARACTERES = 28
PONTUACAO_FINAL = ".,;:!?…"

CABECALHO_ASS = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Montserrat,48,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,3,0,5,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _chave(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^\w-]", "", sem_acento).casefold()


def corrigir_palavras(palavras: list[Palavra], nomes: list[str]) -> list[Palavra]:
    resultado = list(palavras)
    for nome in sorted(nomes, key=lambda n: len(n.split()), reverse=True):
        partes = nome.split()
        alvo = [_chave(p) for p in partes]
        for i in range(len(resultado) - len(partes) + 1):
            janela = resultado[i : i + len(partes)]
            if [_chave(p.texto) for p in janela] == alvo:
                for j, (palavra, parte) in enumerate(zip(janela, partes)):
                    final = re.search(r"[^\w]*$", palavra.texto).group()
                    resultado[i + j] = replace(palavra, texto=parte + final)
    return resultado


def _disposicao(palavras: list[str]) -> list[str] | None:
    texto = " ".join(palavras)
    if len(texto) <= MAX_CARACTERES:
        return [texto]
    opcoes = []
    for corte in range(1, len(palavras)):
        a, b = " ".join(palavras[:corte]), " ".join(palavras[corte:])
        if len(a) <= MAX_CARACTERES and len(b) <= MAX_CARACTERES:
            opcoes.append((abs(len(a) - len(b)), [a, b]))
    return min(opcoes, key=lambda o: o[0])[1] if opcoes else None


def _caixa(texto: str, inicio_de_frase: bool, nomes: set[str]) -> str:
    letras = re.sub(r"[^\w]", "", texto)
    if not inicio_de_frase or _chave(texto) in nomes or (len(letras) >= 2 and letras.isupper()):
        return texto
    return texto[:1].lower() + texto[1:]


def _tamanho_do_bloco(textos: list[str], inicio: int) -> int:
    restantes = len(textos) - inicio
    n = min(MAX_PALAVRAS, restantes)
    while n > 1 and _disposicao(textos[inicio : inicio + n]) is None:
        n -= 1
    for i in range(MIN_PALAVRAS, n):
        if textos[inicio + i - 1][-1:] in PONTUACAO_FINAL:
            n = i
            break
    sobra = restantes - n
    if 0 < sobra < MIN_PALAVRAS:
        n = max(MIN_PALAVRAS, n - (MIN_PALAVRAS - sobra))
        n = min(n, restantes)
    return n


def montar_cues(
    palavras: list[Palavra], faixas: list[tuple[float, float]], nomes: list[str] = ()
) -> list[Cue]:
    conhecidos = {_chave(parte) for nome in nomes for parte in nome.split()}
    visiveis: list[tuple[str, float, float]] = []
    inicio_de_frase = True
    for palavra in palavras:
        meio = remapear((palavra.inicio + palavra.fim) / 2, faixas)
        if meio is None:
            continue
        de = remapear(palavra.inicio, faixas)
        ate = remapear(palavra.fim, faixas)
        visiveis.append(
            (
                _caixa(palavra.texto, inicio_de_frase, conhecidos),
                meio if de is None else de,
                meio if ate is None else ate,
            )
        )
        inicio_de_frase = palavra.texto.endswith((".", "?", "!"))

    textos = [v[0] for v in visiveis]
    cues: list[Cue] = []
    i = 0
    while i < len(textos):
        n = _tamanho_do_bloco(textos, i)
        bloco = textos[i : i + n]
        bloco[-1] = bloco[-1].rstrip(PONTUACAO_FINAL)
        linhas = _disposicao(bloco) or [" ".join(bloco)]
        cues.append(Cue(visiveis[i][1], visiveis[i + n - 1][2], linhas))
        i += n
    return cues


def _tempo_srt(t: float) -> str:
    ms = round(t * 1000)
    return f"{ms // 3600000:02d}:{ms % 3600000 // 60000:02d}:{ms % 60000 // 1000:02d},{ms % 1000:03d}"


def _tempo_ass(t: float) -> str:
    cs = round(t * 100)
    return f"{cs // 360000}:{cs % 360000 // 6000:02d}:{cs % 6000 // 100:02d}.{cs % 100:02d}"


def escrever_srt(cues: list[Cue], caminho: Path) -> None:
    blocos = [
        f"{i}\n{_tempo_srt(c.inicio)} --> {_tempo_srt(c.fim)}\n" + "\n".join(c.linhas)
        for i, c in enumerate(cues, 1)
    ]
    Path(caminho).write_text("\n\n".join(blocos) + "\n", "utf-8", newline="\n")


def _escapar_ass(texto: str) -> str:
    return texto.replace("\\", "\\\\").replace("{", r"\{").replace("}", r"\}")


def escrever_ass(cues: list[Cue], caminho: Path) -> None:
    eventos = [
        f"Dialogue: 0,{_tempo_ass(c.inicio)},{_tempo_ass(c.fim)},Default,,0,0,0,,"
        + r"{\an5\pos(540,1613)}"
        + r"\N".join(_escapar_ass(l) for l in c.linhas)
        for c in cues
    ]
    Path(caminho).write_text(CABECALHO_ASS + "\n".join(eventos) + "\n", "utf-8", newline="\n")
