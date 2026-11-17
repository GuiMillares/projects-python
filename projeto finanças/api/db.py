"""Acesso ao MySQL do Laragon.

Sem ORM: as consultas são poucas e diretas. O que importa aqui é que
TODA query passa por parâmetro (%s), nunca por f-string. É o que
mantém injeção de SQL fora da jogada.
"""

import re
import ssl
from contextlib import contextmanager

import pymysql
from pymysql.cursors import DictCursor

import config


def _contexto_ssl():
    """TLS com o certificado do servidor conferido (nome e cadeia).

    Usa o pacote de autoridades do certifi quando ele existe (vem com o
    google-genai); senão, o do sistema.
    """
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def conectar():
    extras = {}
    if config.DB_SSL:
        extras["ssl"] = _contexto_ssl()
    if config.DB_FUSO:
        # init_command não aceita parâmetro, então o valor entra no texto.
        # Por isso só passa o formato exato de deslocamento, ex. -03:00.
        if not re.fullmatch(r"[+-]\d{2}:\d{2}", config.DB_FUSO):
            raise ValueError("FIN_DB_FUSO precisa ser um deslocamento como -03:00.")
        extras["init_command"] = f"SET time_zone = '{config.DB_FUSO}'"
    return pymysql.connect(
        host=config.DB_HOST,
        port=config.DB_PORT,
        user=config.DB_USER,
        password=config.DB_PASS,
        database=config.DB_NAME,
        charset="utf8mb4",
        cursorclass=DictCursor,
        autocommit=False,
        **extras,
    )


@contextmanager
def cursor(commit=False):
    """Abre conexão + cursor e garante commit/rollback e fechamento.

    Uso:
        with cursor() as cur:                 # leitura
            cur.execute("SELECT ...", (x,))
        with cursor(commit=True) as cur:      # escrita
            cur.execute("UPDATE ...", (x,))
    """
    conn = conectar()
    try:
        with conn.cursor() as cur:
            yield cur
        if commit:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def buscar_um(sql, params=()):
    with cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()


def buscar_todos(sql, params=()):
    with cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def executar(sql, params=()):
    with cursor(commit=True) as cur:
        cur.execute(sql, params)
        return cur.rowcount
