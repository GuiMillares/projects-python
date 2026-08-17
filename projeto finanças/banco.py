import sqlite3



def criar_tabela():
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
    conexao.commit()
    conexao.close() 

def inserir_transacao(data, nome, valor, natureza, categoria, recorrencia):
    conexao = sqlite3.connect("financas.db")
    cursor = conexao.cursor()
    cursor.execute("INSERT INTO transacoes (data, nome, valor, natureza, categoria, recorrencia) VALUES (?, ?, ?, ?, ?, ?)", (data, nome, valor, natureza, categoria, recorrencia))
    conexao.commit()
    conexao.close() 
    
def calcular_resumo():
    conexao = sqlite3.connect("financas.db")
    cursor = conexao.cursor()
    cursor.execute("SELECT * FROM transacoes")
    resultado = cursor.fetchall()

    saldo = 0
    receita_por_categoria = {}
    despesa_por_categoria = {}
    for transacao in resultado:
            valor = transacao[3]
            natureza = transacao[4]
            categoria = transacao[5]

            if natureza == "Receita":
                saldo = saldo + valor
            elif natureza == "Despesa":
                saldo = saldo - valor
            
            if categoria not in receita_por_categoria:
                receita_por_categoria[categoria] = 0
            if categoria not in despesa_por_categoria:
                despesa_por_categoria[categoria] = 0
            if natureza == "Receita":
                receita_por_categoria[categoria] += valor
            elif natureza == "Despesa":
                despesa_por_categoria[categoria] -= valor
    receita_filtrada = {}
    for categoria, valor in receita_por_categoria.items():
        if valor != 0:
            receita_filtrada[categoria] = valor
    despesa_filtrada = {}
    for categoria, valor in despesa_por_categoria.items():
        if valor != 0:
            despesa_filtrada[categoria] = valor
    conexao.close() 
    return {
        "saldo": saldo,
        "receita_por_categoria": receita_filtrada,
        "despesa_por_categoria": despesa_filtrada
        
    }

def listar_transacoes():
    conexao = sqlite3.connect("financas.db")
    cursor = conexao.cursor()
    cursor.execute("SELECT * FROM transacoes")
    transacoes_formatadas = []
    resultado = cursor.fetchall()
    for transacao in resultado:
        id = transacao[0]
        data = transacao[1]
        nome = transacao[2]
        valor = transacao[3]
        natureza = transacao[4]
        categoria = transacao[5]
        recorrencia = transacao[6]
        transacoes_formatadas.append(
            {
                "id": id,
                "data": data,
                "nome": nome,
                "valor": valor,
                "natureza": natureza,
                "categoria": categoria,
                "recorrencia": recorrencia
            }
        )
    conexao.close() 
    return transacoes_formatadas

