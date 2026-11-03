"""Cifra dos segredos que o app guarda por pessoa (hoje, o Client Secret
da aplicação de cada um na Pluggy).

Fernet, do pacote cryptography (AES com HMAC: quem mexer no texto cifrado
é pego na leitura). A chave mora em FIN_CHAVE_CREDENCIAIS, no .env, fora do
banco: um dump vazado não leva os segredos junto. Se a chave se perder,
cada pessoa cadastra a credencial de novo; nenhum dado financeiro some.
"""

from cryptography.fernet import Fernet, InvalidToken

import config


def _fernet():
    return Fernet(config.CHAVE_CREDENCIAIS.encode())


def disponivel() -> bool:
    """Chave presente E no formato certo: chave torta vira aviso na tela,
    não erro 500 na primeira credencial gravada."""
    if not config.CHAVE_CREDENCIAIS:
        return False
    try:
        _fernet()
    except ValueError:
        return False
    return True


def cifrar(texto: str) -> str:
    return _fernet().encrypt(texto.encode("utf-8")).decode("ascii")


def decifrar(cifrado: str) -> str | None:
    """None quando não abre: chave trocada ou texto adulterado."""
    try:
        return _fernet().decrypt(cifrado.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        return None
