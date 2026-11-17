"""Espaço compartilhado: casal, família, até MAX_MEMBROS pessoas.

Como nasce: alguém com conta gera um convite (link de uso único, 7 dias)
e manda para o par. O par cria a conta por esse link, ou entra com a que
já tem, e responde "vincular?". Só no SIM o espaço é criado, com os dois
dentro. Assim nunca existe espaço vazio nem espaço de uma pessoa só.

Regras:
* Cada pessoa está em no máximo um espaço.
* O dono convida e remove. Se ele sair, o membro mais antigo vira dono.
  Se sobrar uma pessoa só, o espaço acaba (não há o que compartilhar).
* O convite guarda só o hash do código, como as sessões. Quem pegou o
  convite (`usado_por`) é o único que pode aceitá-lo depois.

O que os membros veem uns dos outros é a entrega seguinte (visões Eu,
cada pessoa e Juntos). Este módulo só cuida de quem está junto de quem.
"""

import hashlib
import secrets
from datetime import datetime, timedelta

from db import buscar_todos, buscar_um, cursor

MAX_MEMBROS = 6
CONVITE_DIAS = 7


class EspacoErro(Exception):
    """Regra do espaço que a pessoa esbarrou. A mensagem vai para a tela."""

    def __init__(self, mensagem, status=400):
        super().__init__(mensagem)
        self.status = status


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def espaco_de(usuario_id: int):
    """{'id', 'papel'} do espaço da pessoa, ou None."""
    m = buscar_um(
        "SELECT espaco_id, papel FROM espaco_membros WHERE usuario_id = %s", (usuario_id,)
    )
    return {"id": m["espaco_id"], "papel": m["papel"]} if m else None


def membros(espaco_id: int) -> list:
    return buscar_todos(
        "SELECT u.id, u.nome, u.email, m.papel, m.entrou_em "
        "  FROM espaco_membros m JOIN usuarios u ON u.id = m.usuario_id "
        " WHERE m.espaco_id = %s ORDER BY m.entrou_em, u.id",
        (espaco_id,),
    )


# ── Convite ──────────────────────────────────────────────────
def criar_convite(usuario_id: int) -> dict:
    """Gera um link novo. O convite anterior ainda não usado deixa de valer:
    só existe um link solto por pessoa de cada vez."""
    meu = espaco_de(usuario_id)
    if meu:
        if meu["papel"] != "dono":
            raise EspacoErro("Só quem administra o espaço convida pessoas.", 403)
        if len(membros(meu["id"])) >= MAX_MEMBROS:
            raise EspacoErro(f"O espaço já tem {MAX_MEMBROS} pessoas, o máximo.")

    token = secrets.token_urlsafe(24)
    expira = datetime.now() + timedelta(days=CONVITE_DIAS)
    with cursor(commit=True) as cur:
        cur.execute(
            "DELETE FROM convites WHERE criado_por = %s AND usado_por IS NULL", (usuario_id,)
        )
        cur.execute(
            "INSERT INTO convites (token_hash, criado_por, expira_em) VALUES (%s, %s, %s)",
            (_hash(token), usuario_id, expira),
        )
    return {"token": token, "expiraEm": expira.isoformat(timespec="seconds")}


def cancelar_convite(usuario_id: int):
    with cursor(commit=True) as cur:
        cur.execute(
            "DELETE FROM convites WHERE criado_por = %s AND usado_por IS NULL", (usuario_id,)
        )


def convite_aberto(usuario_id: int):
    """O link que a pessoa gerou e ninguém pegou ainda (só a validade:
    o código em si não é guardado e não volta)."""
    c = buscar_um(
        "SELECT expira_em FROM convites WHERE criado_por = %s AND usado_por IS NULL "
        "AND expira_em > %s ORDER BY id DESC LIMIT 1",
        (usuario_id, datetime.now()),
    )
    return {"expiraEm": c["expira_em"].isoformat(timespec="seconds")} if c else None


def _ler_convite(token: str, cur=None, travar=False):
    sql = (
        "SELECT c.id, c.criado_por, c.expira_em, c.usado_por, c.aceito_em, u.nome, u.email "
        "  FROM convites c JOIN usuarios u ON u.id = c.criado_por "
        " WHERE c.token_hash = %s" + (" FOR UPDATE" if travar else "")
    )
    params = (_hash(str(token or "")[:64]),)
    if cur is None:
        return buscar_um(sql, params)
    cur.execute(sql, params)
    return cur.fetchone()


def _primeiro_nome(c) -> str:
    nome = (c["nome"] or "").strip()
    return nome.split()[0] if nome else c["email"].split("@")[0]


def ver_convite(token: str, usuario_id: int | None = None) -> dict:
    """O que a página do convite mostra. Só o primeiro nome de quem
    convidou: o link pode cair em mãos erradas, e e-mail não vai."""
    c = _ler_convite(token)
    if not c or c["expira_em"] < datetime.now():
        raise EspacoErro("Este convite não vale mais. Peça um link novo.", 404)
    if c["aceito_em"]:
        raise EspacoErro("Este convite já foi usado.", 410)
    if c["usado_por"] and c["usado_por"] != usuario_id:
        raise EspacoErro("Este convite já foi usado.", 410)
    return {"convidadoPor": _primeiro_nome(c), "expiraEm": c["expira_em"].isoformat(timespec="seconds")}


def pegar_convite(cur, token: str, usuario_id: int):
    """Prende o convite a esta pessoa (no cadastro ou ao abrir o link com
    a conta já existente). Daí em diante, só ela pode aceitá-lo."""
    c = _ler_convite(token, cur, travar=True)
    if not c or c["expira_em"] < datetime.now() or c["aceito_em"]:
        raise EspacoErro("Este convite não vale mais. Peça um link novo.", 404)
    if c["usado_por"] and c["usado_por"] != usuario_id:
        raise EspacoErro("Este convite já foi usado.", 410)
    if c["criado_por"] == usuario_id:
        raise EspacoErro("Este convite é seu. Mande o link para quem você quer convidar.")
    if not c["usado_por"]:
        cur.execute(
            "UPDATE convites SET usado_por = %s, usado_em = %s WHERE id = %s",
            (usuario_id, datetime.now(), c["id"]),
        )
    return c


def convite_pendente(usuario_id: int):
    """Convite que esta pessoa pegou e ainda não respondeu: é o que faz a
    pergunta "vincular?" aparecer no app."""
    c = buscar_um(
        "SELECT c.id, c.criado_por, c.expira_em, u.nome, u.email "
        "  FROM convites c JOIN usuarios u ON u.id = c.criado_por "
        " WHERE c.usado_por = %s AND c.aceito_em IS NULL AND c.expira_em > %s "
        " ORDER BY c.id DESC LIMIT 1",
        (usuario_id, datetime.now()),
    )
    return {"id": c["id"], "convidadoPor": _primeiro_nome(c)} if c else None


def aceitar(usuario_id: int, convite_id: int):
    """SIM ao vínculo: cria o espaço (se quem convidou ainda não tem) e põe
    os dois dentro, numa transação só."""
    with cursor(commit=True) as cur:
        cur.execute(
            "SELECT id, criado_por, expira_em, usado_por, aceito_em FROM convites "
            "WHERE id = %s FOR UPDATE",
            (convite_id,),
        )
        c = cur.fetchone()
        if (not c or c["usado_por"] != usuario_id or c["aceito_em"]
                or c["expira_em"] < datetime.now()):
            raise EspacoErro("Este convite não vale mais. Peça um link novo.", 404)

        cur.execute("SELECT espaco_id FROM espaco_membros WHERE usuario_id = %s", (usuario_id,))
        if cur.fetchone():
            raise EspacoErro("Você já está num espaço. Saia dele antes de entrar em outro.", 409)

        cur.execute(
            "SELECT espaco_id, papel FROM espaco_membros WHERE usuario_id = %s FOR UPDATE",
            (c["criado_por"],),
        )
        dele = cur.fetchone()
        if dele:
            if dele["papel"] != "dono":
                raise EspacoErro("Quem te convidou não administra mais o espaço. Peça outro link.", 409)
            espaco_id = dele["espaco_id"]
            cur.execute(
                "SELECT COUNT(*) AS n FROM espaco_membros WHERE espaco_id = %s", (espaco_id,)
            )
            if cur.fetchone()["n"] >= MAX_MEMBROS:
                raise EspacoErro(f"O espaço já tem {MAX_MEMBROS} pessoas, o máximo.", 409)
        else:
            cur.execute("INSERT INTO espacos (nome) VALUES ('')")
            espaco_id = cur.lastrowid
            cur.execute(
                "INSERT INTO espaco_membros (usuario_id, espaco_id, papel) VALUES (%s, %s, 'dono')",
                (c["criado_por"], espaco_id),
            )

        cur.execute(
            "INSERT INTO espaco_membros (usuario_id, espaco_id, papel) VALUES (%s, %s, 'membro')",
            (usuario_id, espaco_id),
        )
        cur.execute("UPDATE convites SET aceito_em = %s WHERE id = %s", (datetime.now(), c["id"]))
    return espaco_id


def recusar(usuario_id: int, convite_id: int):
    """NÃO ao vínculo: o convite morre. Quem convidou pode mandar outro."""
    with cursor(commit=True) as cur:
        cur.execute(
            "DELETE FROM convites WHERE id = %s AND usado_por = %s AND aceito_em IS NULL",
            (convite_id, usuario_id),
        )


# ── Saída e remoção ──────────────────────────────────────────
def _tirar(cur, usuario_id: int):
    cur.execute(
        "SELECT espaco_id, papel FROM espaco_membros WHERE usuario_id = %s FOR UPDATE",
        (usuario_id,),
    )
    m = cur.fetchone()
    if not m:
        return
    cur.execute("DELETE FROM espaco_membros WHERE usuario_id = %s", (usuario_id,))
    cur.execute(
        "SELECT usuario_id FROM espaco_membros WHERE espaco_id = %s "
        "ORDER BY entrou_em, usuario_id",
        (m["espaco_id"],),
    )
    restantes = [r["usuario_id"] for r in cur.fetchall()]
    if len(restantes) <= 1:
        # Uma pessoa sozinha não tem com quem compartilhar: o espaço acaba.
        cur.execute("DELETE FROM espacos WHERE id = %s", (m["espaco_id"],))
    elif m["papel"] == "dono":
        cur.execute(
            "UPDATE espaco_membros SET papel = 'dono' WHERE usuario_id = %s", (restantes[0],)
        )


def sair(usuario_id: int):
    with cursor(commit=True) as cur:
        _tirar(cur, usuario_id)


def remover_membro(dono_id: int, membro_id: int):
    if dono_id == membro_id:
        raise EspacoErro("Para sair você mesmo, use Sair do espaço.")
    meu = espaco_de(dono_id)
    if not meu or meu["papel"] != "dono":
        raise EspacoErro("Só quem administra o espaço remove pessoas.", 403)
    dele = espaco_de(membro_id)
    if not dele or dele["id"] != meu["id"]:
        raise EspacoErro("Essa pessoa não está no seu espaço.", 404)
    with cursor(commit=True) as cur:
        _tirar(cur, membro_id)


def resumo(usuario_id: int) -> dict:
    """Tudo o que Configurações mostra sobre o espaço desta pessoa."""
    meu = espaco_de(usuario_id)
    lista = []
    if meu:
        lista = [
            {
                "id": m["id"],
                "nome": m["nome"] or m["email"].split("@")[0],
                "email": m["email"],
                "papel": m["papel"],
                "eu": m["id"] == usuario_id,
                "entrouEm": m["entrou_em"].isoformat(timespec="seconds"),
            }
            for m in membros(meu["id"])
        ]
    return {
        "espaco": {"id": meu["id"], "papel": meu["papel"]} if meu else None,
        "membros": lista,
        "maxMembros": MAX_MEMBROS,
        "conviteAberto": convite_aberto(usuario_id),
        "convitePendente": convite_pendente(usuario_id),
    }
