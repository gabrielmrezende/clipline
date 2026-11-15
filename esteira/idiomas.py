"""Listas que dependem do idioma falado no canal.

O idioma é o `[transcricao] idioma` do clipline.toml (padrão "pt"): o mesmo código vai para o Whisper e escolhe as
listas abaixo. Sem o arquivo, valem as listas em português, exatamente as de sempre.

Idioma sem lista aqui ainda transcreve. A limpeza então só corta pausas e repetições (não reconhece hesitação nem
protege repetição de propósito), e o filtro de pessoa real usa os cargos de todos os idiomas conhecidos.
"""

PADRAO = "pt"

# Sons de hesitação que a limpeza corta. Palavras que também têm sentido ficam ("é", "né", "tipo"; "like",
# "you know"; "este", "pues"): cortá-las poderia mudar a fala.
HESITACOES: dict[str, frozenset[str]] = {
    "pt": frozenset({"hum", "hã", "ahn", "éé", "hmm", "ãh", "eh"}),
    "en": frozenset({"um", "umm", "uh", "uhm", "er", "erm", "hmm", "mm"}),
    "es": frozenset({"eh", "ehm", "em", "mmm", "hmm", "mm"}),
}

# Palavras cuja repetição costuma ser de propósito ("não, não", "very very", "sí, sí"): a limpeza não corta.
PROTEGIDAS: dict[str, frozenset[str]] = {
    "pt": frozenset({"né", "tá", "não", "muito", "nunca", "sim", "isso"}),
    "en": frozenset({"no", "not", "very", "never", "yes", "yeah", "really", "so", "that", "had"}),
    "es": frozenset({"no", "sí", "si", "muy", "nunca", "eso", "ya"}),
}

# Cargos que, num canal de política, apontam para uma pessoa real ("o presidente" é o presidente de agora).
# Sem acento: a comparação normaliza.
CARGOS: dict[str, tuple[str, ...]] = {
    "pt": (
        "presidente", "presidenta", "vice-presidente", "ex-presidente", "primeiro-ministro", "primeira-ministra",
        "ministro", "ministra", "senador", "senadora", "deputado", "deputada", "governador", "governadora",
        "prefeito", "prefeita", "vereador", "vereadora", "chanceler", "papa", "rei", "rainha", "principe", "princesa",
        "candidato", "candidata", "ditador", "ditadora", "stf",
    ),
    "en": (
        "president", "vice president", "prime minister", "minister", "senator", "congressman", "congresswoman",
        "member of congress", "governor", "mayor", "chancellor", "pope", "king", "queen", "prince", "princess",
        "dictator", "candidate", "head of state", "supreme court justice",
    ),
    "es": (
        "presidente", "presidenta", "vicepresidente", "vicepresidenta", "expresidente", "expresidenta",
        "primer ministro", "primera ministra", "ministro", "ministra", "senador", "senadora", "diputado", "diputada",
        "gobernador", "gobernadora", "alcalde", "alcaldesa", "concejal", "concejala", "canciller", "papa", "rey",
        "reina", "principe", "princesa", "candidato", "candidata", "dictador", "dictadora", "jefe de estado",
        "jefa de estado",
    ),
}


def hesitacoes(idioma: str) -> frozenset[str]:
    return HESITACOES.get(idioma, frozenset())


def protegidas(idioma: str) -> frozenset[str]:
    return PROTEGIDAS.get(idioma, frozenset())


def cargos(idioma: str) -> tuple[str, ...]:
    """Os cargos do idioma do canal e os do inglês (os prompts de imagem costumam ir em inglês).

    Idioma sem lista: os de todos os idiomas conhecidos, porque no filtro de pessoa real sobrar é melhor que faltar."""
    grupos = [CARGOS[idioma], CARGOS["en"]] if idioma in CARGOS else list(CARGOS.values())
    return tuple(dict.fromkeys(cargo for grupo in grupos for cargo in grupo))


# Textos fixos que a esteira escreve na imagem: a linha da fonte do cartão de notícia e o convite do encerramento.
# Idioma sem tradução usa o português, como antes.
TEXTOS_FIXOS: dict[str, dict[str, str]] = {
    "pt": {"fonte": "Fonte", "siga": "SIGA"},
    "en": {"fonte": "Source", "siga": "FOLLOW"},
    "es": {"fonte": "Fuente", "siga": "SIGUE"},
}


def texto_fixo(idioma: str, chave: str) -> str:
    return TEXTOS_FIXOS.get(idioma, TEXTOS_FIXOS[PADRAO])[chave]
