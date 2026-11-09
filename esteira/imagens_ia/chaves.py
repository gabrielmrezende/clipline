SERVICO = "tudo-e-politica-imagens"


def _keyring():
    import keyring  # importado aqui: os testes não precisam do pacote

    return keyring


def ler_chave(provedor: str) -> str | None:
    return _keyring().get_password(SERVICO, f"{provedor}:chave")


def gravar_chave(provedor: str, chave: str) -> None:
    _keyring().set_password(SERVICO, f"{provedor}:chave", chave)


def tem_chave(provedor: str) -> bool:
    return bool(ler_chave(provedor))
