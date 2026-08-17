"""Traz o financas.db (SQLite) para o local_finance (MySQL).

    python importar_sqlite.py "../financas.db" seu@email.com

Converte na passagem o que o esquema antigo deixava solto:
  data        "DD/MM/AAAA" (ou já ISO) → DATE
  valor       REAL                     → DECIMAL, sempre positivo
  natureza    "Receita"/"despesa"/…    → ENUM('receita','despesa')
  recorrencia texto livre              → ENUM('unica','mensal')

Roda quantas vezes quiser: lançamento igual (mesma data, nome, valor e
natureza) não entra duas vezes.
"""

import sqlite3
import sys
from decimal import Decimal, InvalidOperation

from db import buscar_um, cursor


def para_data(bruto):
    texto = str(bruto or "").strip()
    if not texto:
        return None
    if "/" in texto:
        partes = texto.split("/")
        if len(partes) == 3:
            dia, mes, ano = (p.strip() for p in partes)
            if len(ano) == 2:
                ano = f"20{ano}"
            return f"{ano}-{mes.zfill(2)}-{dia.zfill(2)}"
        return None
    return texto[:10]


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    caminho_sqlite, email = sys.argv[1], sys.argv[2].strip().lower()

    usuario = buscar_um("SELECT id FROM usuarios WHERE email = %s", (email,))
    if not usuario:
        sys.exit(f"Usuário {email} não existe. Rode criar_usuario.py primeiro.")
    uid = usuario["id"]

    con = sqlite3.connect(caminho_sqlite)
    con.row_factory = sqlite3.Row
    linhas = con.execute(
        "SELECT data, nome, valor, natureza, categoria, recorrencia FROM transacoes"
    ).fetchall()
    con.close()

    inseridos = ignorados = invalidos = 0

    with cursor(commit=True) as cur:
        for linha in linhas:
            data = para_data(linha["data"])
            try:
                valor = abs(Decimal(str(linha["valor"] or 0)))
            except InvalidOperation:
                valor = Decimal(0)

            if not data or valor <= 0:
                invalidos += 1
                continue

            natureza = "receita" if str(linha["natureza"] or "").lower().startswith("rec") else "despesa"
            recorrencia = "mensal" if str(linha["recorrencia"] or "").lower().startswith("mens") else "unica"
            nome = (linha["nome"] or "").strip()[:160] or "Sem descrição"
            categoria = (linha["categoria"] or "").strip()[:80] or "Sem categoria"

            cur.execute(
                "SELECT id FROM transacoes WHERE usuario_id = %s AND data = %s "
                "AND nome = %s AND valor = %s AND natureza = %s",
                (uid, data, nome, valor, natureza),
            )
            if cur.fetchone():
                ignorados += 1
                continue

            cur.execute(
                "INSERT INTO transacoes (usuario_id, data, nome, valor, natureza, "
                "categoria, recorrencia) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (uid, data, nome, valor, natureza, categoria, recorrencia),
            )
            inseridos += 1

    print(f"{inseridos} importados · {ignorados} já existiam · {invalidos} inválidos")


if __name__ == "__main__":
    main()
