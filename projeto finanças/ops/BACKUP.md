# Backup e restauração

Roteiro para a fase 2, quando o app for para a VPS. Um backup por dia, cifrado,
guardado por 30 dias, com cópia fora do servidor e teste de restauração toda
semana. Tudo pelo `ops/backup.py`.

## O que entra e o que fica de fora

- **Entra:** o banco `local_finance` inteiro, com todas as tabelas.
- **Fica de fora:** o `.env` (chave do Gemini, token da brapi, senha do banco
  e `FIN_CHAVE_CREDENCIAIS`, que abre as credenciais da Pluggy de cada pessoa)
  e a frase da cifra. Os dois vão para o gerenciador de senhas. Sem a frase,
  nenhum backup abre. Sem a `FIN_CHAVE_CREDENCIAIS`, o banco restaurado volta
  inteiro, mas cada pessoa precisa cadastrar de novo a credencial da Pluggy.
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

## TiDB na nuvem (o que está em produção hoje)

O app roda na Vercel com o banco no TiDB Cloud. O backup sai do TiDB por TLS
e fica no seu computador, cifrado, por 30 dias. O teste de restauração usa o
MySQL local (Laragon): nada é criado no TiDB.

### Preparar (uma vez)

1. No TiDB Cloud, abra o **SQL Editor** do cluster e crie um usuário só de
   leitura. No plano Starter todo usuário começa com o prefixo do cluster,
   o mesmo que aparece antes do `.root` no seu usuário:
   ```sql
   CREATE USER '<PREFIXO>.backup'@'%' IDENTIFIED BY 'uma-senha-forte-e-nova';
   GRANT SELECT, SHOW VIEW ON local_finance.* TO '<PREFIXO>.backup'@'%';
   ```
   Se esse arquivo vazar, quem o achar só lê; não apaga nem altera nada.
2. No Git Bash, crie a pasta, a frase da cifra e o arquivo da origem, todos
   fora do repositório:
   ```bash
   mkdir -p ~/backups-financas
   head -c 48 /dev/urandom | base64 > ~/backups-financas/backup.frase
   cat > ~/backups-financas/tidb.env <<'FIM'
   FIN_DB_HOST=<host do TiDB>
   FIN_DB_PORT=4000
   FIN_DB_USER=<PREFIXO>.backup
   FIN_DB_PASS=<a senha do passo 1>
   FIN_DB_NAME=local_finance
   FIN_DB_SSL=1
   FIM
   ```
   Guarde uma cópia da `backup.frase` no gerenciador de senhas **agora**.
   Sem ela, nenhum backup abre.
3. Primeiro backup e teste (o Laragon precisa estar com o MySQL ligado para o
   teste):
   ```bash
   cmd //c ops\backup-tidb.cmd
   tail -3 ~/backups-financas/backup.log
   FIN_BACKUP_DIR=~/backups-financas FIN_BACKUP_SENHA_ARQUIVO=~/backups-financas/backup.frase \
   FIN_MYSQL_BIN="C:/laragon/bin/mysql/mysql-8.4.3-winx64/bin" FIN_GPG=/usr/bin/gpg \
   ../.venv/Scripts/python.exe ops/backup.py testar
   ```

### Agenda

No Prompt de Comando (cmd), uma vez, para rodar todo dia às 21h:
```
schtasks /Create /SC DAILY /ST 21:00 /TN "Lastro backup" /TR "\"F:\projects-python\projeto finanças\ops\backup-tidb.cmd\""
```
O Agendador só roda com o computador ligado. Se ele estiver desligado às
21h, o backup daquele dia não acontece; o seguinte segue normal. Para não
depender só deste computador, configure uma cópia externa (`rclone config`
com o Google Drive, por exemplo) e ponha `set "FIN_BACKUP_RCLONE=gdrive:lastro-backup"`
no `backup-tidb.cmd`. O arquivo já sai cifrado.

Rode o `testar` uma vez por semana (passo 3). A última linha de
`~/backups-financas/restauracao.log` precisa ser `ok` e desta semana.

### Restaurar no TiDB (desastre)

1. Escolha o backup e teste-o no MySQL local, como no passo 3, com o nome do
   arquivo no fim do `testar`.
2. Restaure apontando as `FIN_DB_*` para o TiDB com o usuário **root** (o de
   backup só lê). O script testa o arquivo de novo e guarda um
   `antes-de-restaurar-*` do estado atual antes de trocar:
   ```bash
   FIN_DB_HOST=<host> FIN_DB_PORT=4000 FIN_DB_USER=<PREFIXO>.root FIN_DB_PASS='<senha>' FIN_DB_SSL=1 \
   FIN_BACKUP_DIR=~/backups-financas FIN_BACKUP_SENHA_ARQUIVO=~/backups-financas/backup.frase \
   FIN_MYSQL_BIN="C:/laragon/bin/mysql/mysql-8.4.3-winx64/bin" FIN_GPG=/usr/bin/gpg \
   ../.venv/Scripts/python.exe ops/backup.py restaurar ~/backups-financas/financas-AAAAMMDD-HHMMSS.sql.gpg --confirmo
   ```
3. Rode `ops/atualizar_banco.py` se o backup for de antes de alguma mudança
   no banco, e confira `/api/saude`.

**Testado em 17/11/2026:** `fazer --origem` com um usuário só de leitura e
`testar` no MySQL local, com o arquivo cifrado e as contagens batendo. O
dump contra o próprio TiDB (TLS e as opções `--column-statistics=0` e
`--set-gtid-purged=OFF`) é conferido no primeiro backup de verdade.
