"""Cria (ou atualiza a senha de) o usuário do painel.

    python criar_usuario.py

A senha é pedida sem eco e nunca vai por argumento de linha de comando:
argumento fica no histórico do shell e na lista de processos.

O 2FA não é configurado aqui: o cadastro acontece na primeira vez que
você entra na tela de login, que é onde o QR code aparece.
"""

import getpass
import sys

import seguranca
from db import buscar_um, cursor


def main():
    email = input("E-mail: ").strip().lower()
    if "@" not in email:
        sys.exit("E-mail inválido.")

    nome = input("Nome (opcional): ").strip()

    senha = getpass.getpass("Senha (mín. 8 caracteres): ")
    if len(senha) < 8:
        sys.exit("Senha curta demais.")
    if senha != getpass.getpass("Repita a senha: "):
        sys.exit("As senhas não coincidem.")

    existente = buscar_um("SELECT id FROM usuarios WHERE email = %s", (email,))
    with cursor(commit=True) as cur:
        if existente:
            cur.execute(
                "UPDATE usuarios SET senha_hash = %s, nome = COALESCE(NULLIF(%s, ''), nome), "
                "tentativas = 0, bloqueado_ate = NULL WHERE id = %s",
                (seguranca.hash_senha(senha), nome, existente["id"]),
            )
            # Trocou a senha por fora: derruba tudo que estava aberto.
            cur.execute("DELETE FROM sessoes WHERE usuario_id = %s", (existente["id"],))
            print(f"\nSenha de {email} atualizada.")
        else:
            cur.execute(
                "INSERT INTO usuarios (email, senha_hash, nome) VALUES (%s, %s, %s)",
                (email, seguranca.hash_senha(senha), nome),
            )
            print(f"\nUsuário {email} criado.")

    print("O 2FA é configurado no primeiro login, na própria tela.")


if __name__ == "__main__":
    main()
