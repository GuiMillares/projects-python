import sqlite3

conexao = sqlite3.connect("financas.db")
cursor = conexao.cursor()

cursor.execute("""
    CREATE TABLE IF NOT EXISTS transacoes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        data TEXT,
        nome TEXT,
        valor REAL,
        natureza TEXT,
        categoria TEXT,
        recorrencia TEXT
    )
""")

cursor.execute(
    "INSERT INTO transacoes (data, nome, valor, natureza, categoria, recorrencia) VALUES (?, ?, ?, ?, ?, ?)",
    ("2022-01-01", "Salário", 5000.0, "Receita", "Salário", "Sim")
)

conexao.commit()

cursor.execute("SELECT * FROM transacoes")
resultado = cursor.fetchall()
print(resultado)