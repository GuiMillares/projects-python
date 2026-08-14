import sqlite3

conexao = sqlite3.connect("financas.db")
cursor = conexao.cursor()
rodando = True

def criar_tabela():
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

def inserir_transacao(data, nome, valor, natureza, categoria, recorrencia):
    cursor.execute(
        "INSERT INTO transacoes (data, nome, valor, natureza, categoria, recorrencia) VALUES (?, ?, ?, ?, ?, ?)",
        (data, nome, valor, natureza, categoria, recorrencia)
    )
    conexao.commit()

# Garante que a tabela exista antes de qualquer operação
criar_tabela()

while rodando:
    print("\n1 - Adicionar transação")
    print("2 - Ver resumo")
    print("3 - Sair")
    opcao = input("Escolha uma opção: ")
    if opcao == "1":
        data = input("Qual a data? (DD/MM/AAAA): ")
        nome = input("Qual o nome? ")
        valor = float(input("Qual o valor? "))
        natureza = input("Qual a natureza? ")
        categoria = input("Qual a categoria? ")
        recorrencia = input("Qual a recorrencia? ")
    
        inserir_transacao(data, nome, valor, natureza, categoria, recorrencia)
        print("Transação inserida com sucesso!")

    elif opcao == "2":
        cursor.execute("SELECT * FROM transacoes")
        resultado = cursor.fetchall()

        saldo = 0
        for transacao in resultado:
            valor = transacao[3]
            natureza = transacao[4]

            if natureza == "Receita":
                saldo = saldo + valor
            elif natureza == "Despesa":
                saldo = saldo - valor

        print(f"Saldo atual: R$ {saldo}")

    elif opcao == "3":
        print("Saindo...")
        rodando = False
    else:
        print("Opção inválida")
        