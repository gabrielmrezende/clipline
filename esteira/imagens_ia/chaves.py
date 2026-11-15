from esteira import config

SERVICO = "tudo-e-politica-imagens"  # o nome padrão; o que vale é servico(), que segue [credenciais] prefixo


def servico() -> str:
    return config.servico_de_credenciais("imagens")


def _keyring():
    import keyring  # importado aqui: os testes não precisam do pacote

    return keyring


def ler_chave(provedor: str) -> str | None:
    return _keyring().get_password(servico(), f"{provedor}:chave")


def gravar_chave(provedor: str, chave: str) -> None:
    _keyring().set_password(servico(), f"{provedor}:chave", chave)


def tem_chave(provedor: str) -> bool:
    return bool(ler_chave(provedor))
