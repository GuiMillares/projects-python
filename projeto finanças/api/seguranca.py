"""Senha, sessão e TOTP.

INVARIANTE DO PROJETO: o segredo TOTP existe só aqui e na coluna
`usuarios.totp_secret`. Ele nunca é serializado numa resposta da API.
O frontend recebe, uma única vez e apenas no cadastro, o `otpauth://`
que vira QR code, e nem esse URI é guardado do lado do cliente.

Antes era Cloud Function; agora é este módulo. O que não mudou é a
regra: quem valida o código é o servidor.
"""

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta

import pyotp

import config
from db import buscar_um, cursor

# ── Senha ────────────────────────────────────────────────────
# scrypt da stdlib. Parâmetros do RFC 7914 para uso interativo:
# n=2^15 gasta ~100ms e 32MB por tentativa, o que torna força bruta
# offline cara mesmo com o dump do banco na mão.
#
# `maxmem` precisa ser declarado: o OpenSSL corta em 32MB por padrão e
# n=2^15 encosta exatamente nesse teto (128·n·r = 32MiB), estourando com
# "memory limit exceeded". 64MB dá a folga.
_SCRYPT = dict(n=2**15, r=8, p=1, dklen=32, maxmem=64 * 1024 * 1024)


def hash_senha(senha: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(senha.encode("utf-8"), salt=salt, **_SCRYPT)
    return f"scrypt${salt.hex()}${dk.hex()}"


def conferir_senha(senha: str, guardado: str) -> bool:
    try:
        algo, salt_hex, dk_hex = guardado.split("$")
        if algo != "scrypt":
            return False
        dk = hashlib.scrypt(senha.encode("utf-8"), salt=bytes.fromhex(salt_hex), **_SCRYPT)
    except (ValueError, AttributeError):
        return False
    # compare_digest: a comparação leva o mesmo tempo acertando ou
    # errando, então o tempo de resposta não vaza o hash.
    return hmac.compare_digest(dk.hex(), dk_hex)


# ── Sessão ───────────────────────────────────────────────────
def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def criar_sessao(usuario_id: int, dois_fatores_ok: bool = False) -> str:
    """Devolve o token em claro; no banco fica só o hash dele."""
    token = secrets.token_urlsafe(32)
    minutos = (
        config.SESSAO_HORAS * 60 if dois_fatores_ok else config.SESSAO_PARCIAL_MINUTOS
    )
    with cursor(commit=True) as cur:
        cur.execute(
            "INSERT INTO sessoes (usuario_id, token_hash, dois_fatores_ok, expira_em) "
            "VALUES (%s, %s, %s, %s)",
            (usuario_id, _hash_token(token), int(dois_fatores_ok),
             datetime.now() + timedelta(minutes=minutos)),
        )
    return token


def ler_sessao(token: str):
    if not token:
        return None
    return buscar_um(
        "SELECT s.id, s.usuario_id, s.dois_fatores_ok, "
        "       u.email, u.nome, u.totp_secret IS NOT NULL AS tem_segredo, "
        "       u.totp_confirmado "
        "  FROM sessoes s "
        "  JOIN usuarios u ON u.id = s.usuario_id "
        " WHERE s.token_hash = %s AND s.expira_em > NOW()",
        (_hash_token(token),),
    )


def promover_sessao(sessao_id: int):
    """2FA validado: a sessão vira completa e ganha a validade cheia."""
    with cursor(commit=True) as cur:
        cur.execute(
            "UPDATE sessoes SET dois_fatores_ok = 1, expira_em = %s WHERE id = %s",
            (datetime.now() + timedelta(hours=config.SESSAO_HORAS), sessao_id),
        )


def encerrar_sessao(token: str):
    with cursor(commit=True) as cur:
        cur.execute("DELETE FROM sessoes WHERE token_hash = %s", (_hash_token(token),))


def encerrar_sessoes_do_usuario(usuario_id: int, exceto_id: int | None = None):
    """Usado ao trocar senha ou mexer no 2FA: derruba as outras sessões."""
    sql = "DELETE FROM sessoes WHERE usuario_id = %s"
    params = [usuario_id]
    if exceto_id:
        sql += " AND id <> %s"
        params.append(exceto_id)
    with cursor(commit=True) as cur:
        cur.execute(sql, params)


def limpar_sessoes_expiradas():
    with cursor(commit=True) as cur:
        cur.execute("DELETE FROM sessoes WHERE expira_em < NOW()")


# ── TOTP ─────────────────────────────────────────────────────
INTERVALO = 30
JANELA = 1  # aceita ±30s de desvio de relógio


def gerar_segredo(usuario_id: int, email: str) -> str:
    """Cria segredo novo e devolve o otpauth://. O segredo em si fica.

    Enquanto `totp_confirmado` for 0, o segredo está apenas provisório:
    o login continua exigindo o cadastro até alguém acertar um código.
    """
    segredo = pyotp.random_base32()
    with cursor(commit=True) as cur:
        cur.execute(
            "UPDATE usuarios SET totp_secret = %s, totp_confirmado = 0, "
            "totp_ultimo_step = NULL WHERE id = %s",
            (segredo, usuario_id),
        )
    return pyotp.TOTP(segredo, interval=INTERVALO).provisioning_uri(
        name=email, issuer_name=config.EMISSOR_TOTP
    )


def conferir_codigo(usuario_id: int, codigo: str) -> bool:
    """Valida o código e queima a janela usada.

    Sem a checagem de `totp_ultimo_step`, o mesmo código de 6 dígitos
    valeria por 30 segundos inteiros, tempo de sobra para alguém que
    tenha visto a tela reutilizá-lo.
    """
    codigo = "".join(ch for ch in str(codigo) if ch.isdigit())
    if len(codigo) != 6:
        return False

    linha = buscar_um(
        "SELECT totp_secret, totp_ultimo_step FROM usuarios WHERE id = %s",
        (usuario_id,),
    )
    if not linha or not linha["totp_secret"]:
        return False

    totp = pyotp.TOTP(linha["totp_secret"], interval=INTERVALO)
    agora = int(datetime.now().timestamp())
    step_atual = agora // INTERVALO
    ultimo = linha["totp_ultimo_step"]

    for desvio in range(-JANELA, JANELA + 1):
        step = step_atual + desvio
        if ultimo is not None and step <= ultimo:
            continue  # janela já usada
        if hmac.compare_digest(totp.at(step * INTERVALO), codigo):
            with cursor(commit=True) as cur:
                cur.execute(
                    "UPDATE usuarios SET totp_ultimo_step = %s, totp_confirmado = 1 "
                    "WHERE id = %s",
                    (step, usuario_id),
                )
            return True
    return False


def remover_2fa(usuario_id: int):
    with cursor(commit=True) as cur:
        cur.execute(
            "UPDATE usuarios SET totp_secret = NULL, totp_confirmado = 0, "
            "totp_ultimo_step = NULL WHERE id = %s",
            (usuario_id,),
        )


# ── Anti-força-bruta ─────────────────────────────────────────
def esta_bloqueado(usuario) -> bool:
    ate = usuario.get("bloqueado_ate")
    return bool(ate and ate > datetime.now())


def registrar_falha(usuario_id: int):
    """Na enésima falha seguida, tranca a conta por alguns minutos."""
    with cursor(commit=True) as cur:
        cur.execute(
            "UPDATE usuarios SET tentativas = tentativas + 1, "
            "bloqueado_ate = CASE WHEN tentativas + 1 >= %s "
            "                     THEN DATE_ADD(NOW(), INTERVAL %s MINUTE) "
            "                     ELSE bloqueado_ate END "
            "WHERE id = %s",
            (config.MAX_TENTATIVAS, config.BLOQUEIO_MINUTOS, usuario_id),
        )


def limpar_falhas(usuario_id: int):
    with cursor(commit=True) as cur:
        cur.execute(
            "UPDATE usuarios SET tentativas = 0, bloqueado_ate = NULL WHERE id = %s",
            (usuario_id,),
        )
