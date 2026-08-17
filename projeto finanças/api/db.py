"""Acesso ao MySQL do Laragon.

Sem ORM: as consultas são poucas e diretas. O que importa aqui é que
TODA query passa por parâmetro (%s), nunca por f-string. É o que
mantém injeção de SQL fora da jogada.
"""

from contextlib import contextmanager

import pymysql
from pymysql.cursors import DictCursor

import config


def conectar():
    return pymysql.connect(
        host=config.DB_HOST,
        port=config.DB_PORT,
        user=config.DB_USER,
        password=config.DB_PASS,
        database=config.DB_NAME,
        charset="utf8mb4",
        cursorclass=DictCursor,
        autocommit=False,
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
