"""Backup cifrado do banco e teste de restauração.

    python ops/backup.py fazer
        dump do banco, cifrado com gpg, mais um manifesto com a contagem de
        linhas; apaga os backups mais velhos que FIN_BACKUP_DIAS e, se
        configurado, copia para fora do servidor com rclone.

    python ops/backup.py testar [ARQUIVO]
        restaura o backup mais recente (ou ARQUIVO) num banco temporário,
        confere contagens e órfãos, e apaga o banco temporário.

    python ops/backup.py restaurar ARQUIVO --confirmo
        desastre: testa o arquivo, faz um backup do estado atual e põe o
        backup no lugar do banco de produção. Pare a API antes.

Configuração, além das FIN_DB_* da API (variável de ambiente ou .env):
    FIN_BACKUP_DIR            pasta dos backups (padrão: ~/backups-financas)
    FIN_BACKUP_SENHA_ARQUIVO  arquivo com a frase da cifra (obrigatório)
    FIN_BACKUP_DIAS           dias de retenção (padrão: 30, o que a política
                              de privacidade promete)
    FIN_BACKUP_RCLONE         destino rclone da cópia externa (opcional)
    FIN_BACKUP_AVISO_URL      healthcheck: GET no sucesso, URL/fail na falha
    FIN_MYSQL_BIN             pasta do mysqldump e do mysql, fora do PATH
    FIN_GPG                   caminho do gpg, fora do PATH

O SQL decifrado nunca vai para o disco: o dump entra no gpg por pipe, e a
restauração sai do gpg direto para o mysql. Roteiro completo em
ops/BACKUP.md.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO / "api"))

import pymysql  # noqa: E402

import config  # noqa: E402

PASTA = Path(os.getenv("FIN_BACKUP_DIR") or Path.home() / "backups-financas").expanduser()
DIAS = int(os.getenv("FIN_BACKUP_DIAS", "30"))
RCLONE = os.getenv("FIN_BACKUP_RCLONE", "").strip()
AVISO_URL = os.getenv("FIN_BACKUP_AVISO_URL", "").strip()
GPG = os.getenv("FIN_GPG", "gpg")
BANCO_TESTE = f"{config.DB_NAME}_restauracao"


class Falha(Exception):
    pass


def _bin(nome):
    pasta = os.getenv("FIN_MYSQL_BIN", "").strip()
    return str(Path(pasta) / nome) if pasta else nome


def _args_mysql():
    return ["-h", config.DB_HOST, "-P", str(config.DB_PORT), "-u", config.DB_USER]


def _env_mysql():
    # Senha por variável de ambiente, e não na linha de comando: argumento
    # aparece para qualquer usuário do servidor no `ps`.
    env = dict(os.environ)
    if config.DB_PASS:
        env["MYSQL_PWD"] = config.DB_PASS
    return env


def _frase():
    caminho = os.getenv("FIN_BACKUP_SENHA_ARQUIVO", "").strip()
    if not caminho or not Path(caminho).is_file():
        raise Falha("FIN_BACKUP_SENHA_ARQUIVO não aponta para um arquivo.")
    if os.name == "posix" and Path(caminho).stat().st_mode & 0o077:
        raise Falha(f"{caminho} pode ser lido por outros usuários. Rode: chmod 600 {caminho}")
    return caminho


def _pasta():
    # O repositório é público: backup dentro dele seria um commit de
    # distância de vazar.
    repo = RAIZ_PROJETO.parent
    if PASTA.resolve().is_relative_to(repo.resolve()):
        raise Falha(f"FIN_BACKUP_DIR ({PASTA}) está dentro do repositório. Use uma pasta fora dele.")
    PASTA.mkdir(parents=True, exist_ok=True)
    if os.name == "posix":
        PASTA.chmod(0o700)
    return PASTA


def _conectar(banco=None):
    return pymysql.connect(
        host=config.DB_HOST, port=config.DB_PORT, user=config.DB_USER,
        password=config.DB_PASS, database=banco, charset="utf8mb4", autocommit=True,
    )


def _contar(banco):
    """Linhas por tabela, com COUNT(*) de verdade: o TABLE_ROWS do
    information_schema é estimativa no InnoDB."""
    con = _conectar(banco)
    try:
        with con.cursor() as cur:
            cur.execute("SHOW TABLES")
            tabelas = [t for (t,) in cur.fetchall()]
            contagem = {}
            for t in tabelas:
                cur.execute(f"SELECT COUNT(*) FROM `{t}`")
                contagem[t] = cur.fetchone()[0]
            return contagem
    finally:
        con.close()


def _sha256(arquivo):
    h = hashlib.sha256()
    with open(arquivo, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def _rodar_pipe(origem, destino, rotulos):
    """origem | destino, falhando se qualquer um dos dois falhar."""
    a = subprocess.Popen(origem[0], stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=origem[1])
    b = subprocess.Popen(destino[0], stdin=a.stdout, stderr=subprocess.PIPE, env=destino[1])
    a.stdout.close()  # o destino é o único leitor; sem isto o SIGPIPE não chega
    _, erro_b = b.communicate()
    erro_a = a.stderr.read()
    a.wait()
    for nome, proc, erro in ((rotulos[0], a, erro_a), (rotulos[1], b, erro_b)):
        if proc.returncode != 0:
            raise Falha(f"{nome} falhou: {erro.decode('utf-8', 'replace').strip()}")


def _podar(pasta):
    """Apaga backup e manifesto mais velhos que DIAS, inclusive os
    "antes-de-restaurar": a política promete que dado apagado some das
    cópias em até 30 dias, e isso vale para todas."""
    limite = time.time() - DIAS * 86400
    apagados = 0
    for arquivo in list(pasta.glob("*.sql.gpg")) + list(pasta.glob("*.json")):
        if arquivo.stat().st_mtime < limite:
            arquivo.unlink()
            apagados += arquivo.suffix == ".gpg"
    return apagados


def fazer(rotulo="financas"):
    pasta, frase = _pasta(), _frase()
    nome = f"{rotulo}-{datetime.now():%Y%m%d-%H%M%S}.sql.gpg"
    final = pasta / nome
    parcial = pasta / f"{nome}.parcial"

    # Sem --routines: o schema não tem procedure, e pedir isso exigiria um
    # privilégio a mais para o usuário de backup.
    dump = [_bin("mysqldump"), *_args_mysql(), "--single-transaction", "--quick",
            "--no-tablespaces", "--default-character-set=utf8mb4", config.DB_NAME]
    cifra = [GPG, "--batch", "--yes", "--pinentry-mode", "loopback", "--passphrase-file", frase,
             "--symmetric", "--cipher-algo", "AES256", "-o", str(parcial)]
    try:
        _rodar_pipe((dump, _env_mysql()), (cifra, None), ("mysqldump", "gpg"))
    except Falha:
        parcial.unlink(missing_ok=True)
        raise
    contagem = _contar(config.DB_NAME)
    parcial.rename(final)

    (pasta / f"{final.stem.removesuffix('.sql')}.json").write_text(json.dumps({
        "arquivo": nome,
        "criadoEm": datetime.now().isoformat(timespec="seconds"),
        "banco": config.DB_NAME,
        "sha256": _sha256(final),
        "tabelas": contagem,
    }, indent=2), encoding="utf-8")

    apagados = _podar(pasta)
    if RCLONE:
        for arq in (final, pasta / f"{final.stem.removesuffix('.sql')}.json"):
            subprocess.run(["rclone", "copy", str(arq), RCLONE], check=True)
        subprocess.run(["rclone", "delete", RCLONE, "--min-age", f"{DIAS}d"], check=True)
    print(f"ok: {final} ({final.stat().st_size // 1024} KB, {sum(contagem.values())} linhas); "
          f"{apagados} backups com mais de {DIAS} dias apagados"
          + (f"; copiado para {RCLONE}" if RCLONE else ""))
    return final


def _mais_recente():
    arquivos = sorted(_pasta().glob("financas-*.sql.gpg"))
    if not arquivos:
        raise Falha(f"Nenhum backup em {PASTA}.")
    return arquivos[-1]


def _carregar(arquivo, banco):
    decifra = [GPG, "--batch", "--quiet", "--pinentry-mode", "loopback",
               "--passphrase-file", _frase(), "-d", str(arquivo)]
    mysql = [_bin("mysql"), *_args_mysql(), "--default-character-set=utf8mb4", banco]
    _rodar_pipe((decifra, None), (mysql, _env_mysql()), ("gpg", "mysql"))


def _recriar(banco):
    con = _conectar()
    try:
        with con.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS `{banco}`")
            cur.execute(f"CREATE DATABASE `{banco}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    finally:
        con.close()


def _orfaos(banco):
    """Linhas que apontam para usuário ou meta que não existe. O dump
    desliga a checagem de chave estrangeira ao carregar, então um backup
    torto entraria calado; aqui ele aparece."""
    con = _conectar(banco)
    achados = {}
    try:
        with con.cursor() as cur:
            cur.execute(
                "SELECT TABLE_NAME FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = %s AND COLUMN_NAME = 'usuario_id'", (banco,))
            for (t,) in cur.fetchall():
                cur.execute(f"SELECT COUNT(*) FROM `{t}` x LEFT JOIN usuarios u ON u.id = x.usuario_id "
                            "WHERE u.id IS NULL")
                achados[t] = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM subtarefas s LEFT JOIN metas m ON m.id = s.meta_id "
                        "WHERE m.id IS NULL")
            achados["subtarefas"] = cur.fetchone()[0]
    finally:
        con.close()
    return {t: n for t, n in achados.items() if n}


def _registrar(linha):
    with open(_pasta() / "restauracao.log", "a", encoding="utf-8") as log:
        log.write(f"{datetime.now():%Y-%m-%d %H:%M} {linha}\n")
    print(linha)


def testar(arquivo=None):
    """Teste que falha também fica no log: o log é a prova de que os
    backups funcionam, e um buraco nele esconderia justamente o problema."""
    arquivo = Path(arquivo) if arquivo else _mais_recente()
    try:
        _testar(arquivo)
    except Falha as e:
        _registrar(f"FALHOU {arquivo.name}: {e}")
        raise


def _testar(arquivo):
    manifesto_arq = arquivo.with_name(f"{arquivo.stem.removesuffix('.sql')}.json")
    if not manifesto_arq.is_file():
        raise Falha(f"Sem manifesto para {arquivo.name}.")
    manifesto = json.loads(manifesto_arq.read_text(encoding="utf-8"))
    if _sha256(arquivo) != manifesto["sha256"]:
        raise Falha(f"{arquivo.name} não bate com o sha256 do manifesto: arquivo corrompido.")

    inicio = time.time()
    _recriar(BANCO_TESTE)
    try:
        _carregar(arquivo, BANCO_TESTE)
        restaurado = _contar(BANCO_TESTE)
        orfaos = _orfaos(BANCO_TESTE)
    finally:
        # Uma cópia decifrada do banco não fica para trás, nem se o teste falhar.
        con = _conectar()
        with con.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS `{BANCO_TESTE}`")
        con.close()

    diferencas = {
        t: (manifesto["tabelas"].get(t), restaurado.get(t))
        for t in set(manifesto["tabelas"]) | set(restaurado)
        if manifesto["tabelas"].get(t) != restaurado.get(t)
    }
    if diferencas or orfaos:
        raise Falha("restaurado não bate com o manifesto"
                    + (f"; diferenças {diferencas}" if diferencas else "")
                    + (f"; órfãos {orfaos}" if orfaos else ""))
    _registrar(f"ok {arquivo.name}: {len(restaurado)} tabelas, {sum(restaurado.values())} linhas, "
               f"{time.time() - inicio:.1f}s")


def restaurar(arquivo, confirmo):
    if not confirmo:
        raise Falha("Isto troca o banco de produção pelo backup. Pare a API e repita com --confirmo.")
    testar(arquivo)
    # Servidor novo, depois de perder o antigo, ainda não tem o banco: não
    # há estado atual para guardar.
    con = _conectar()
    with con.cursor() as cur:
        cur.execute("SELECT 1 FROM information_schema.SCHEMATA WHERE SCHEMA_NAME = %s",
                    (config.DB_NAME,))
        existe = cur.fetchone() is not None
    con.close()
    if existe:
        print("Backup do estado atual antes de trocar:")
        fazer(rotulo="antes-de-restaurar")
    _recriar(config.DB_NAME)
    _carregar(Path(arquivo), config.DB_NAME)
    print(f"ok: {config.DB_NAME} restaurado de {Path(arquivo).name}. Suba a API de novo.")


def _avisar(ok):
    if not AVISO_URL:
        return
    try:
        urllib.request.urlopen(AVISO_URL if ok else f"{AVISO_URL.rstrip('/')}/fail", timeout=10)
    except Exception:  # noqa: BLE001 - aviso que falha não pode derrubar o backup
        pass


def main():
    p = argparse.ArgumentParser(description="Backup cifrado e teste de restauração.")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("fazer")
    t = sub.add_parser("testar")
    t.add_argument("arquivo", nargs="?")
    r = sub.add_parser("restaurar")
    r.add_argument("arquivo")
    r.add_argument("--confirmo", action="store_true")
    a = p.parse_args()

    try:
        if a.cmd == "fazer":
            fazer()
        elif a.cmd == "testar":
            testar(a.arquivo)
        else:
            restaurar(a.arquivo, a.confirmo)
    except (Falha, subprocess.CalledProcessError, pymysql.MySQLError, OSError) as e:
        print(f"ERRO: {e}", file=sys.stderr)
        _avisar(False)
        sys.exit(1)
    _avisar(True)


if __name__ == "__main__":
    main()
