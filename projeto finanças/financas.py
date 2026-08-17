from banco import criar_tabela, inserir_transacao, calcular_resumo
rodando = True

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

        print(f"Saldo atual: R$ {saldo}")
        print("Receitas por categoria:")
        for categoria, valor in receita_por_categoria.items():
            if valor != 0:
                print(f"{categoria}: R$ {valor}")
        print("Despesas por categoria:")
        for categoria, valor in despesa_por_categoria.items():
            if valor != 0:
                print(f"{categoria}: R$ {valor}")

    elif opcao == "3":
        print("Saindo...")
        rodando = False
    else:
        print("Opção inválida")
        