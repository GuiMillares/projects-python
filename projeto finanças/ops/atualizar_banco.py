"""Deixa um banco existente (TiDB na nuvem ou o MySQL do Laragon) igual ao
db/schema.sql. Pode rodar quantas vezes quiser: só cria o que falta.

    # TiDB (pede a senha sem eco):
    python ops/atualizar_banco.py HOST USUARIO
    # Laragon (root sem senha):
    python ops/atualizar_banco.py local

Rode de dentro de "projeto finanças/". Faz duas coisas:
1. roda o db/schema.sql, que só tem CREATE ... IF NOT EXISTS: tabelas
   novas aparecem, as existentes não são tocadas;
2. acrescenta as COLUNAS e ÍNDICES da lista abaixo que ainda não existem.
   O schema.sql não faz isso (CREATE TABLE IF NOT EXISTS pula a tabela que
   já existe), e o TiDB não roda o PREPARE condicional do db/migrar.sql.

Mudou o banco? Ponha a coluna no schema.sql E uma linha aqui.
"""

import getpass
import re
import ssl
import sys
from pathlib import Path

import pymysql

BANCO = "local_finance"

# (tabela, coluna, definição) e (tabela, índice, definição)
COLUNAS = [
    ("transacoes", "conexao_id", "INT UNSIGNED NULL"),
    ("transacoes", "privada", "TINYINT(1) NOT NULL DEFAULT 0"),
    ("conexoes_bancarias", "privada", "TINYINT(1) NOT NULL DEFAULT 0"),
]
INDICES = [
    ("transacoes", "ix_transacoes_conexao", "(conexao_id)"),
]


def conectar(args):
    if args and args[0] == "local":
        return pymysql.connect(host="127.0.0.1", user="root", password="", charset="utf8mb4",
                               autocommit=True)
    if len(args) < 2:
        sys.exit(__doc__)
    host, usuario = args[0], args[1]
    senha = getpass.getpass("Senha do banco (não aparece ao digitar): ")
    try:
        import certifi
        contexto = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        contexto = ssl.create_default_context()
    return pymysql.connect(host=host, port=4000, user=usuario, password=senha,
                           charset="utf8mb4", ssl=contexto, autocommit=True)


def comandos_do_schema():
    texto = (Path(__file__).resolve().parent.parent / "db" / "schema.sql").read_text(encoding="utf-8")
    sem_comentario = "\n".join(l for l in texto.splitlines() if not l.lstrip().startswith("--"))
    return [c.strip() for c in re.split(r";\s*\n", sem_comentario) if c.strip()]


def main():
    conn = conectar(sys.argv[1:])
    with conn.cursor() as cur:
        cmds = comandos_do_schema()
        for c in cmds:
            cur.execute(c)
        print(f"schema.sql: {len(cmds)} comandos (tabelas que faltavam foram criadas)")

        cur.execute(f"USE {BANCO}")
        for tabela, coluna, definicao in COLUNAS:
            cur.execute(
                "SELECT COUNT(*) FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND COLUMN_NAME = %s",
                (BANCO, tabela, coluna),
            )
            if cur.fetchone()[0]:
                print(f"  {tabela}.{coluna}: já existe")
            else:
                cur.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {definicao}")
                print(f"  {tabela}.{coluna}: CRIADA")

        for tabela, indice, definicao in INDICES:
            cur.execute(
                "SELECT COUNT(*) FROM information_schema.STATISTICS "
                "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND INDEX_NAME = %s",
                (BANCO, tabela, indice),
            )
            if cur.fetchone()[0]:
                print(f"  índice {indice}: já existe")
            else:
                cur.execute(f"ALTER TABLE {tabela} ADD INDEX {indice} {definicao}")
                print(f"  índice {indice}: CRIADO")

        cur.execute("SHOW TABLES")
        print(f"\n{len(cur.fetchall())} tabelas em {BANCO}. Confira em /api/saude.")
    conn.close()


if __name__ == "__main__":
    main()
