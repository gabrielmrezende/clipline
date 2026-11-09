import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from esteira.cortar import TRABALHO, pasta_do_corte
from esteira.modelos import Corte
from esteira.musica import Faixa, ler_uso
from esteira.painel.troca_musica import MARCADOR, Resultado, recuperar_trocas_interrompidas, trocar_musica
from esteira.receita import NOME_ARQUIVO, Musica, ler_receita
from tests.auxiliares_painel import criar_episodio

CORTE = Corte(1, "A Fórmula 1 faz sportswashing", 2.0, 20.0, "")
CREDITO_ANTIGO = "Música: Ice Flow — Kevin MacLeod (incompetech.com), licença CC BY 4.0"
NOVA = Faixa("Nova Faixa", "tensao", 120.0, "nova.mp3", "Música: Nova Faixa — Kevin MacLeod (incompetech.com), licença CC BY 4.0")


@pytest.fixture
def cenario(tmp_path):
    musicas = tmp_path / "musicas"
    musicas.mkdir()
    antiga = Musica(str(musicas / "ice.mp3"), -24.0, "Ice Flow", CREDITO_ANTIGO)
    pasta = criar_episodio(tmp_path / "cortes", "ep1", [CORTE], {1}, musica=antiga)
    corte = pasta_do_corte(pasta, CORTE)
    return pasta, corte, musicas, antiga, tmp_path


def _chamar(cenario, montar, faixa=NOVA, volume=-20.0, **extra):
    pasta, _, musicas, _, tmp = cenario
    return trocar_musica(pasta, 1, faixa, volume, montar, base=tmp, pasta_musicas=musicas, **extra)


def test_troca_ok(cenario):
    pasta, corte, musicas, antiga, _ = cenario
    vistas = []

    def montar(p, n):
        receita = ler_receita(corte / TRABALHO)
        vistas.append((p, n, receita.musica))
        return "ok"

    resultado = _chamar(cenario, montar)
    assert resultado == Resultado("pronto", resultado.mensagem, [], antiga)
    assert vistas == [(pasta, 1, Musica(str(musicas / "nova.mp3"), -20.0, "Nova Faixa", NOVA.credito))]
    post = (corte / "post.md").read_text("utf-8")
    assert NOVA.credito in post and CREDITO_ANTIGO not in post
    uso = ler_uso(musicas)
    assert uso[f"ep1/{corte.name}"]["arquivo"] == "nova.mp3"


def test_troca_erro_restaura(cenario):
    _, corte, musicas, _, _ = cenario
    montagem = corte / TRABALHO / NOME_ARQUIVO
    original, post = montagem.read_bytes(), (corte / "post.md").read_bytes()
    resultado = _chamar(cenario, lambda p, n: "erro: ffmpeg falhou")
    assert resultado.estado == "erro" and resultado.mensagem == "erro: ffmpeg falhou"
    assert montagem.read_bytes() == original
    assert (corte / "post.md").read_bytes() == post
    assert not (musicas / "uso.json").exists()


def test_troca_excecao_restaura(cenario):
    _, corte, _, _, _ = cenario
    montagem = corte / TRABALHO / NOME_ARQUIVO
    original = montagem.read_bytes()

    def montar(p, n):
        raise RuntimeError("x")

    resultado = _chamar(cenario, montar)
    assert resultado.estado == "erro" and "x" in resultado.mensagem
    assert montagem.read_bytes() == original


def test_troca_so_volume(cenario):
    _, corte, musicas, antiga, _ = cenario
    post = (corte / "post.md").read_bytes()
    faixa = Faixa("Ice Flow", "calma", 100.0, "ice.mp3", CREDITO_ANTIGO)
    resultado = _chamar(cenario, lambda p, n: "ok", faixa=faixa, volume=-20.0)
    assert resultado.estado == "pronto" and resultado.avisos == []
    assert ler_receita(corte / TRABALHO).musica.volume_db == -20.0
    assert (corte / "post.md").read_bytes() == post
    assert not (musicas / "uso.json").exists()


def test_troca_sem_musica_antiga(tmp_path):
    musicas = tmp_path / "musicas"
    pasta = criar_episodio(tmp_path / "cortes", "ep1", [CORTE], {1})
    corte = pasta_do_corte(pasta, CORTE)
    assert ler_receita(corte / TRABALHO).musica is None
    resultado = trocar_musica(pasta, 1, NOVA, -20.0, lambda p, n: "ok", base=tmp_path, pasta_musicas=musicas)
    assert resultado.estado == "pronto" and resultado.anterior is None
    assert "youtube: crédito antigo não encontrado; confira o crédito" in resultado.avisos
    assert ler_receita(corte / TRABALHO).musica.titulo == "Nova Faixa"
    assert ler_uso(musicas)


def test_troca_credito_falha(cenario):
    _, corte, _, _, _ = cenario
    post = corte / "post.md"
    post.write_bytes(post.read_bytes().replace(b"## TikTok", b"## Outra"))
    resultado = _chamar(cenario, lambda p, n: "ok")
    assert resultado.estado == "pronto"
    assert "crédito não atualizado: post.md sem a seção ## TikTok" in resultado.avisos


def test_troca_sem_post(cenario):
    _, corte, _, _, _ = cenario
    (corte / "post.md").unlink()
    resultado = _chamar(cenario, lambda p, n: "ok")
    assert resultado.estado == "pronto"
    assert resultado.avisos == ["post.md não encontrado: crédito não atualizado"]


def test_corte_inexistente(cenario):
    pasta, _, musicas, _, tmp = cenario
    resultado = trocar_musica(pasta, 9, NOVA, -20.0, lambda p, n: "ok", base=tmp, pasta_musicas=musicas)
    assert resultado == Resultado("erro", "corte 9 não encontrado", [], None)


def test_erro_preserva_video_e_registro(cenario):
    _, corte, _, _, _ = cenario
    video, registro = corte / "corte.mp4", corte / TRABALHO / "registro.json"
    video.write_bytes(b"velho")
    original = registro.read_bytes()

    def montar(p, n):
        video.unlink()
        registro.write_text('{"resultado": "erro: x"}', "utf-8")
        return "erro: x"

    resultado = _chamar(cenario, montar)
    assert resultado.estado == "erro"
    assert video.read_bytes() == b"velho" and registro.read_bytes() == original
    assert not (corte / TRABALHO / "corte-anterior.mp4").exists()


def test_ok_mantem_video_novo(cenario):
    _, corte, _, _, _ = cenario
    video = corte / "corte.mp4"
    video.write_bytes(b"velho")

    def montar(p, n):
        video.write_bytes(b"novo")
        return "ok"

    assert _chamar(cenario, montar).estado == "pronto"
    assert video.read_bytes() == b"novo"
    assert not (corte / TRABALHO / "corte-anterior.mp4").exists()


def test_resultado_nao_str_restaura(cenario):
    _, corte, _, _, _ = cenario
    original = (corte / TRABALHO / NOME_ARQUIVO).read_bytes()
    assert _chamar(cenario, lambda p, n: None).estado == "erro"
    assert (corte / TRABALHO / NOME_ARQUIVO).read_bytes() == original


def test_credito_oserror_vira_aviso(cenario, monkeypatch):
    def falha(*a, **k):
        raise OSError("arquivo aberto")

    monkeypatch.setattr("esteira.painel.troca_musica.trocar_credito", falha)
    resultado = _chamar(cenario, lambda p, n: "ok")
    assert resultado.estado == "pronto"
    assert "crédito não atualizado: arquivo aberto" in resultado.avisos


def test_uso_falha_vira_aviso(cenario, monkeypatch):
    def falha(*a, **k):
        raise OSError("disco cheio")

    monkeypatch.setattr("esteira.painel.troca_musica.registrar_uso", falha)
    resultado = _chamar(cenario, lambda p, n: "ok")
    assert resultado.estado == "pronto"
    assert "uso da música não registrado: disco cheio" in resultado.avisos


def test_uso_fora_da_base(cenario):
    pasta, _, musicas, _, tmp = cenario
    resultado = trocar_musica(
        pasta, 1, NOVA, -20.0, lambda p, n: "ok", base=tmp / "cortes", pasta_musicas=musicas
    )
    assert resultado.estado == "pronto"
    assert any(a.startswith("uso da música não registrado:") for a in resultado.avisos)
    assert not (musicas / "uso.json").exists()


VIDEO_ABERTO = "O vídeo do corte está aberto num player (talvez em outro aparelho). Feche o vídeo e tente de novo."


class ReplacePreso:
    """os.replace falso: dá PermissionError (WinError 32) nas primeiras `falhas` vezes."""

    def __init__(self, falhas):
        self.falhas = falhas
        self.chamadas = 0

    def __call__(self, origem, destino):
        self.chamadas += 1
        if self.chamadas <= self.falhas:
            raise PermissionError(13, "O arquivo já está sendo usado por outro processo")
        os.replace(origem, destino)


def test_video_aberto_espera_e_tenta_de_novo(cenario):
    _, corte, _, _, _ = cenario
    video = corte / "corte.mp4"
    video.write_bytes(b"velho")
    esperas = []
    substituir = ReplacePreso(falhas=2)

    def montar(p, n):
        assert not video.exists() and (corte / TRABALHO / "corte-anterior.mp4").read_bytes() == b"velho"
        video.write_bytes(b"novo")
        return "ok"

    resultado = _chamar(cenario, montar, substituir=substituir, dormir=esperas.append)
    assert resultado.estado == "pronto"
    assert esperas == [0.25, 0.25]
    assert video.read_bytes() == b"novo"


def test_video_aberto_sempre_vira_erro_sem_tocar_na_montagem(cenario):
    _, corte, _, _, _ = cenario
    video = corte / "corte.mp4"
    video.write_bytes(b"velho")
    montagem = corte / TRABALHO / NOME_ARQUIVO
    original, data = montagem.read_bytes(), montagem.stat().st_mtime_ns
    post = (corte / "post.md").read_bytes()
    esperas = []

    resultado = _chamar(
        cenario, lambda p, n: pytest.fail("não devia montar"), substituir=ReplacePreso(falhas=10**6), dormir=esperas.append
    )
    assert resultado.estado == "erro" and resultado.mensagem == VIDEO_ABERTO
    assert sum(esperas) == pytest.approx(5.0) and set(esperas) == {0.25}
    assert montagem.read_bytes() == original and montagem.stat().st_mtime_ns == data
    assert video.read_bytes() == b"velho" and (corte / "post.md").read_bytes() == post
    assert not (corte / TRABALHO / "corte-anterior.mp4").exists()


RAIZ = Path(__file__).resolve().parent.parent


def _cair_no_meio(pasta, musicas, base, faixa=NOVA, numero=1, video_novo=None):
    """Roda a troca num processo à parte que morre dentro da montagem (o finally não roda)."""
    grava = f"Path({str(video_novo)!r}).write_bytes(b'novo'), " if video_novo else ""
    montar = f"lambda p, n: ({grava}os._exit(3))"
    codigo = (
        "import os\nfrom pathlib import Path\nfrom esteira.musica import Faixa\n"
        "from esteira.painel.troca_musica import trocar_musica\n"
        f"trocar_musica(Path({str(pasta)!r}), {numero}, {faixa!r}, -20.0, {montar}, "
        f"base=Path({str(base)!r}), pasta_musicas=Path({str(musicas)!r}))\n"
    )
    feito = subprocess.run([sys.executable, "-c", codigo], cwd=RAIZ, timeout=60)
    assert feito.returncode == 3


def _estado(corte):
    trabalho = corte / TRABALHO
    return {
        "montagem": (trabalho / NOME_ARQUIVO).read_bytes(),
        "registro": (trabalho / "registro.json").read_bytes(),
        "video": (corte / "corte.mp4").read_bytes() if (corte / "corte.mp4").exists() else None,
        "post": (corte / "post.md").read_bytes(),
    }


@pytest.fixture
def interrompido(cenario):
    pasta, corte, musicas, _, tmp = cenario
    (corte / "corte.mp4").write_bytes(b"velho")
    antes = _estado(corte)
    _cair_no_meio(pasta, musicas, tmp)
    trabalho = corte / TRABALHO
    assert (trabalho / MARCADOR).exists()
    assert not (corte / "corte.mp4").exists() and (trabalho / "corte-anterior.mp4").read_bytes() == b"velho"
    assert ler_receita(trabalho).musica.titulo == "Nova Faixa"
    return antes


def test_marcador_restaura_antes_de_seguir(cenario, interrompido):
    _, corte, _, _, _ = cenario
    vistos = []

    def montar(p, n):
        vistos.append((corte / TRABALHO / "corte-anterior.mp4").read_bytes())
        return "erro: ffmpeg falhou"

    resultado = _chamar(cenario, montar)
    assert resultado.estado == "erro"
    assert resultado.anterior.titulo == "Ice Flow"  # a música de antes da queda, não a Nova Faixa
    assert vistos == [b"velho"]
    assert _estado(corte) == interrompido
    assert not (corte / TRABALHO / MARCADOR).exists()
    assert not (corte / TRABALHO / "corte-anterior.mp4").exists()


def test_remontar_depois_da_queda_troca_o_credito(cenario, interrompido):
    _, corte, _, antiga, _ = cenario

    def montar(p, n):
        (corte / "corte.mp4").write_bytes(b"novo")
        return "ok"

    resultado = _chamar(cenario, montar)
    assert resultado.estado == "pronto" and resultado.anterior == antiga
    post = (corte / "post.md").read_text("utf-8")
    assert NOVA.credito in post and CREDITO_ANTIGO not in post
    assert not (corte / TRABALHO / MARCADOR).exists()


def test_queda_depois_do_video_novo_volta_o_video_antigo(cenario):
    pasta, corte, musicas, _, tmp = cenario
    (corte / "corte.mp4").write_bytes(b"velho")
    antes = _estado(corte)
    _cair_no_meio(pasta, musicas, tmp, video_novo=corte / "corte.mp4")
    assert (corte / "corte.mp4").read_bytes() == b"novo"
    assert recuperar_trocas_interrompidas(tmp / "cortes") == [f"ep1/{corte.name}"]
    assert _estado(corte) == antes


def test_recuperar_trocas_interrompidas(tmp_path):
    musicas = tmp_path / "musicas"
    musicas.mkdir()
    antiga = Musica(str(musicas / "ice.mp3"), -24.0, "Ice Flow", CREDITO_ANTIGO)
    outro = Corte(2, "Outro corte", 30.0, 50.0, "")
    pasta = criar_episodio(tmp_path / "cortes", "ep1", [CORTE, outro], {1, 2}, musica=antiga)
    caido, normal = pasta_do_corte(pasta, CORTE), pasta_do_corte(pasta, outro)
    antes_caido, antes_normal = _estado(caido), _estado(normal)
    _cair_no_meio(pasta, musicas, tmp_path)
    assert recuperar_trocas_interrompidas(tmp_path / "cortes") == [f"ep1/{caido.name}"]
    assert _estado(caido) == antes_caido and _estado(normal) == antes_normal
    assert not (caido / TRABALHO / MARCADOR).exists()
    assert not (caido / TRABALHO / "corte-anterior.mp4").exists()
    assert recuperar_trocas_interrompidas(tmp_path / "cortes") == []


def test_sem_queda_nao_sobra_marcador(cenario):
    _, corte, _, _, _ = cenario
    assert _chamar(cenario, lambda p, n: "ok").estado == "pronto"
    assert not (corte / TRABALHO / MARCADOR).exists()
    assert _chamar(cenario, lambda p, n: "erro: x").estado == "erro"
    assert not (corte / TRABALHO / MARCADOR).exists()
    _chamar(cenario, lambda p, n: "ok", substituir=ReplacePreso(falhas=10**6), dormir=lambda s: None)
    assert not (corte / TRABALHO / MARCADOR).exists()
