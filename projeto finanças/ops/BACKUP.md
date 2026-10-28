# Backup e restauração

Roteiro para a fase 2, quando o app for para a VPS. Um backup por dia, cifrado,
guardado por 30 dias, com cópia fora do servidor e teste de restauração toda
semana. Tudo pelo `ops/backup.py`.

## O que entra e o que fica de fora

- **Entra:** o banco `local_finance` inteiro, com todas as tabelas.
- **Fica de fora:** o `.env` (chaves da Pluggy, do Gemini e da brapi, senha do
  banco) e a frase da cifra. Os dois vão para o gerenciador de senhas. Sem a
  frase, nenhum backup abre. Sem o `.env`, o app sobe mas não fala com a
  Pluggy nem com o Gemini.
- **O código** está no GitHub.

O SQL decifrado nunca toca o disco: o dump entra no `gpg` por pipe, e a
restauração sai do `gpg` direto para o `mysql`.

## Preparar a VPS (uma vez)

1. Instale as ferramentas:
   ```bash
   sudo apt install gnupg mysql-client rclone
   ```
2. Crie um usuário do MySQL só para o backup. Ele lê o banco de produção e
   mexe apenas no banco temporário do teste:
   ```sql
   CREATE USER 'backup'@'localhost' IDENTIFIED BY 'uma-senha-forte';
   GRANT SELECT, SHOW VIEW, TRIGGER, LOCK TABLES ON local_finance.* TO 'backup'@'localhost';
   GRANT ALL ON local_finance_restauracao.* TO 'backup'@'localhost';
   ```
3. Gere a frase da cifra e guarde uma cópia no gerenciador de senhas **agora**:
   ```bash
   sudo mkdir -p /etc/financas
   head -c 48 /dev/urandom | base64 | sudo tee /etc/financas/backup.frase > /dev/null
   sudo chmod 600 /etc/financas/backup.frase
   ```
   O script recusa a frase se outro usuário do servidor puder lê-la.
4. Configure a cópia externa com `rclone config`, usando Backblaze B2, Google
   Drive ou outro provedor. O arquivo já sai cifrado, então o provedor não vê
   os dados.
5. Escreva `/etc/financas/backup.env` (com `chmod 600`):
   ```
   FIN_DB_USER=backup
   FIN_DB_PASS=uma-senha-forte
   FIN_BACKUP_DIR=/var/backups/financas
   FIN_BACKUP_SENHA_ARQUIVO=/etc/financas/backup.frase
   FIN_BACKUP_RCLONE=remoto:financas-backup
   FIN_BACKUP_AVISO_URL=https://hc-ping.com/seu-id   # opcional
   ```
   O aviso é opcional, mas é ele que conta quando o backup **para** de rodar.
   Um serviço como o healthchecks.io manda e-mail se o ping não chegar.

## Agenda

No crontab do usuário que roda o app:

```
0 3 * * * cd "/srv/financas/projeto finanças" && set -a && . /etc/financas/backup.env && set +a && ../.venv/bin/python ops/backup.py fazer >> /var/log/financas-backup.log 2>&1
0 4 * * 0 cd "/srv/financas/projeto finanças" && set -a && . /etc/financas/backup.env && set +a && ../.venv/bin/python ops/backup.py testar >> /var/log/financas-backup.log 2>&1
```

- `fazer`, todo dia às 3h: gera `financas-AAAAMMDD-HHMMSS.sql.gpg` e um
  manifesto `.json` com o sha256 e a contagem de linhas por tabela. Depois
  apaga o que tem mais de 30 dias, aqui e na cópia externa. É o prazo que a
  política de privacidade promete para o dado apagado sumir das cópias.
- `testar`, todo domingo às 4h: restaura o backup mais recente num banco
  temporário e confere o sha256, a contagem de cada tabela e se sobrou alguma
  linha apontando para usuário ou meta que não existe. No fim, apaga o banco
  temporário. O resultado, bom ou ruim, vai para `restauracao.log`.

**Para saber se está tudo bem:** a última linha de
`/var/backups/financas/restauracao.log` precisa ser `ok` e desta semana.

## Restaurar de verdade

Quem usa o app perde o que fez desde o último backup, ou seja, até 24 horas.
Avise as pessoas.

**Banco apagado ou corrompido, mesmo servidor:**

1. Pare a API.
2. Escolha um backup de antes do problema e teste:
   ```bash
   python ops/backup.py testar /var/backups/financas/financas-AAAAMMDD-HHMMSS.sql.gpg
   ```
3. Restaure com um usuário do MySQL que possa apagar e criar o
   `local_finance` (o root). O script testa o arquivo de novo e guarda um
   backup `antes-de-restaurar-*` do estado atual antes de trocar:
   ```bash
   FIN_DB_USER=root python ops/backup.py restaurar /var/backups/financas/financas-AAAAMMDD-HHMMSS.sql.gpg --confirmo
   ```
4. Se o backup for de antes de alguma migração, rode `db/migrar.sql`.
5. Suba a API e confira o login e uma tela.

**Servidor perdido:** numa VPS nova, siga os passos 1 e 2 da preparação.
Depois clone o repositório, traga o `.env` e a frase do gerenciador de senhas
e baixe o backup e o manifesto com
`rclone copy remoto:financas-backup/ARQUIVO /var/backups/financas/`.
Em seguida, rode o `restaurar --confirmo` como acima. Com o banco ainda vazio,
ele pula o backup do estado atual.

## O que já foi testado (28/10/2026, contra o MySQL local)

- O backup do banco inteiro saiu cifrado em AES-256, sem nenhum `INSERT`
  legível no arquivo.
- A restauração no banco temporário bateu com o manifesto em todas as tabelas,
  sem órfãos, em 2 a 3 segundos. O banco temporário foi apagado no fim.
- Três falhas foram detectadas e ficaram no log: frase errada, arquivo
  corrompido (sha256 diferente) e contagem diferente do manifesto.
- A poda apagou um backup com 40 dias.
- O script recusou uma pasta de backup dentro do repositório e um `restaurar`
  sem `--confirmo`.
- `restaurar --confirmo` foi ensaiado num banco descartável, com a mesma
  estrutura do de produção e dados falsos (`FIN_DB_NAME=local_finance_ensaio`):
  - **Banco estragado depois do backup:** voltou exatamente ao estado do
    backup e deixou um `antes-de-restaurar-*` do estado estragado.
  - **Banco apagado, como num servidor perdido:** foi recriado do zero.

  O banco de produção não foi tocado.

**Ainda não testado:** a cópia com `rclone`, que não está instalado aqui. Na
VPS, antes de abrir o app para outras pessoas, rode um `fazer`, confira o
arquivo no provedor e repita o ensaio de restauração a partir da cópia
externa.
