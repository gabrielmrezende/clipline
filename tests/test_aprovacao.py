import json
import os

import pytest

from esteira.aprovacao import (
    ARQUIVO_APROVADO, Aprovacao, ErroAprovacao, aprovar, da_esteira, estado_aprovacao, imagens_aprovadas,
)
from esteira.caminhos import EscritaProibida

IMAGENS = [{
    "inicio": 1.0, "fim": 3.0, "arquivo": "imagens-sugeridas/0001-placa-1.jpg", "tipo": "foto",
    "momento": "0001-placa", "modificado_ns": 1,
}]
DO_DONO = "video-final/ já tem um vídeo seu (Corte 1.mp4). Para aprovar o corte da esteira, tire esse vídeo de lá."


def _corte(tmp_path, imagens=IMAGENS, resultado="ok"):
    corte = tmp_path / "Tudo é Política" / "01-corte"
    (corte / "trabalho").mkdir(parents=True)
    (corte / "corte.mp4").write_bytes(b"corte montado")
    dados = {"resultado": resultado, "alertas": []}
    if imagens is not None:
        dados["imagens"] = imagens
    (corte / "trabalho" / "registro.json").write_text(json.dumps(dados), "utf-8")
    return corte


def _mais_novo(caminho, segundos=10):
    t = caminho.stat().st_mtime + segundos
    os.utime(caminho, (t, t))


def _nomes(pasta):
    return sorted(p.name for p in pasta.iterdir())


def test_aprovar_copia_e_registra(tmp_path):
    corte = _corte(tmp_path)
    assert estado_aprovacao(corte) == Aprovacao("aprovar")
    assert aprovar(corte, base=tmp_path) == Aprovacao("aprovado")
    copia = corte / "video-final" / ARQUIVO_APROVADO
    assert ARQUIVO_APROVADO == "corte-aprovado.mp4" and copia.read_bytes() == b"corte montado"
    registro = json.loads((corte / "trabalho" / "aprovado.json").read_text("utf-8"))
    assert registro["arquivo"] == "corte-aprovado.mp4" and registro["tamanho"] == len(b"corte montado")
    assert registro["modificado_ns"] == copia.stat().st_mtime_ns and registro["imagens"] == IMAGENS
    assert registro["data"]
    assert _nomes(corte / "video-final") == ["corte-aprovado.mp4"]
    assert da_esteira(corte)["arquivo"] == "corte-aprovado.mp4"


def test_aprovar_em_dia_nao_copia_de_novo(tmp_path):
    corte = _corte(tmp_path)
    aprovar(corte, base=tmp_path)
    copia = corte / "video-final" / ARQUIVO_APROVADO
    antes = copia.stat().st_mtime_ns
    assert aprovar(corte, base=tmp_path) == Aprovacao("aprovado")
    assert copia.stat().st_mtime_ns == antes


def test_corte_remontado_pede_aprovar_de_novo_e_substitui_so_a_copia(tmp_path):
    corte = _corte(tmp_path)
    aprovar(corte, base=tmp_path)
    (corte / "corte.mp4").write_bytes(b"corte novo")
    _mais_novo(corte / "corte.mp4")
    assert estado_aprovacao(corte) == Aprovacao("aprovar de novo")
    assert aprovar(corte, base=tmp_path) == Aprovacao("aprovado")
    assert (corte / "video-final" / ARQUIVO_APROVADO).read_bytes() == b"corte novo"
    assert _nomes(corte / "video-final") == ["corte-aprovado.mp4"]


def test_video_do_dono_bloqueia(tmp_path):
    corte = _corte(tmp_path)
    (corte / "video-final").mkdir()
    (corte / "video-final" / "Corte 1.mp4").write_bytes(b"capcut")
    assert estado_aprovacao(corte) == Aprovacao("bloqueado", DO_DONO)
    with pytest.raises(ErroAprovacao) as erro:
        aprovar(corte, base=tmp_path)
    assert (erro.value.status, str(erro.value)) == (409, DO_DONO)
    assert _nomes(corte / "video-final") == ["Corte 1.mp4"]
    assert not (corte / "trabalho" / "aprovado.json").exists()


def test_dono_trocou_o_corte_aprovado_e_dele(tmp_path):
    corte = _corte(tmp_path)
    aprovar(corte, base=tmp_path)
    copia = corte / "video-final" / ARQUIVO_APROVADO
    copia.write_bytes(b"editado no capcut, com outro tamanho")
    assert da_esteira(corte) is None
    assert estado_aprovacao(corte).estado == "bloqueado"
    with pytest.raises(ErroAprovacao):
        aprovar(corte, base=tmp_path)
    assert copia.read_bytes() == b"editado no capcut, com outro tamanho"


def test_sem_corte_422(tmp_path):
    corte = _corte(tmp_path)
    (corte / "corte.mp4").unlink()
    assert estado_aprovacao(corte) == Aprovacao("bloqueado", "corte não montado")
    with pytest.raises(ErroAprovacao) as erro:
        aprovar(corte, base=tmp_path)
    assert erro.value.status == 422


def test_montando_bloqueia_409(tmp_path):
    corte = _corte(tmp_path)
    assert estado_aprovacao(corte, montando=True) == Aprovacao("bloqueado", "o corte está sendo montado")
    with pytest.raises(ErroAprovacao) as erro:
        aprovar(corte, montando=True, base=tmp_path)
    assert erro.value.status == 409 and not (corte / "video-final" / ARQUIVO_APROVADO).exists()


def test_aprovado_json_ilegivel_trata_como_do_dono(tmp_path):
    corte = _corte(tmp_path)
    aprovar(corte, base=tmp_path)
    (corte / "trabalho" / "aprovado.json").write_text("{quebrado", "utf-8")
    assert da_esteira(corte) is None and estado_aprovacao(corte).estado == "bloqueado"


def test_imagens_aprovadas_so_da_copia_da_esteira(tmp_path):
    corte = _corte(tmp_path)
    aprovar(corte, base=tmp_path)
    assert imagens_aprovadas(corte, corte / "video-final" / ARQUIVO_APROVADO) == IMAGENS
    outro = corte / "video-final" / "Outro.mp4"
    outro.write_bytes(b"x")
    assert imagens_aprovadas(corte, outro) is None


def test_registro_antigo_sem_imagens(tmp_path):
    corte = _corte(tmp_path, imagens=None)
    aprovar(corte, base=tmp_path)
    assert json.loads((corte / "trabalho" / "aprovado.json").read_text("utf-8"))["imagens"] is None
    assert imagens_aprovadas(corte, corte / "video-final" / ARQUIVO_APROVADO) is None


def test_aprovar_fora_das_pastas_permitidas_e_recusado(tmp_path):
    corte = _corte(tmp_path)
    with pytest.raises(EscritaProibida):
        aprovar(corte)  # tmp_path não é 2 - Cortes/ nem Automacao/
    assert not (corte / "video-final").exists()
