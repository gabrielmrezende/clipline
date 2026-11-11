import pytest
from fastapi.testclient import TestClient

from esteira.painel.app import CSP, criar_app, recusa_de_origem


@pytest.fixture
def cliente(tmp_path):
    return TestClient(criar_app(tmp_path))


def test_cabecalhos_de_seguranca(cliente):
    resposta = cliente.get("/api/episodios")
    assert resposta.headers["content-security-policy"] == CSP
    assert resposta.headers["x-content-type-options"] == "nosniff"
    assert resposta.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in CSP and "https://upload.wikimedia.org" in CSP


def test_get_de_outra_pagina_e_recusado(cliente):
    # um <img src="http://127.0.0.1:8765/api/.../fotos/resumo"> numa página qualquer
    assert cliente.get("/api/episodios", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert cliente.get("/api/episodios", headers={"Sec-Fetch-Site": "same-site"}).status_code == 403  # outra porta


def test_post_com_origem_diferente_e_recusado(cliente):
    r = cliente.post("/api/entrar", json={"codigo": "x"}, headers={"Origin": "http://malicioso.example"})
    assert r.status_code == 403


def test_mesma_origem_passa(cliente):
    cabecalhos = {"Sec-Fetch-Site": "same-origin", "Origin": "http://testserver"}
    assert cliente.post("/api/entrar", json={"codigo": "x"}, headers=cabecalhos).status_code == 204
    assert cliente.get("/api/episodios", headers={"Sec-Fetch-Site": "none"}).status_code == 200


def test_fora_da_api_nao_se_aplica():
    assert recusa_de_origem("/assets/x.js", "GET", {"sec-fetch-site": "cross-site"}) is None
