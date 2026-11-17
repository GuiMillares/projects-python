"""Passkeys: entrar com Face ID, digital ou o desbloqueio do aparelho.

Padrão WebAuthn. O aparelho cria um par de chaves preso ao domínio do app
(config.WEBAUTHN_RP_ID) e só usa a chave privada depois da biometria ou do
PIN dele. O servidor guarda a chave PÚBLICA e confere a assinatura de cada
entrada. Nada de biometria passa por aqui.

Vale como os dois fatores de uma vez: algo que a pessoa tem (o aparelho) e
algo que ela é ou sabe (a biometria ou o PIN, exigidos com
user_verification=REQUIRED). Por isso a entrada por passkey já nasce como
sessão completa, como a senha + código.

O cadastro exige sessão completa: só quem já entrou com senha e código
liga um aparelho novo.

Desafios ficam no banco (desafios_webauthn), um por cerimônia, apagados ao
serem usados: na Vercel duas chamadas seguidas podem cair em instâncias
diferentes, e memória de processo não serve.
"""

import hashlib
import json
import secrets
from datetime import datetime, timedelta

from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

import config
from db import buscar_todos, buscar_um, cursor

DESAFIO_MINUTOS = 5


class PasskeyInvalida(Exception):
    """A resposta do aparelho não confere. A mensagem vai para a tela.

    status 404 = a passkey não existe mais aqui (foi removida): a tela
    esquece a marca local do aparelho. Os demais casos são 401/400.
    """

    def __init__(self, mensagem, status=None):
        super().__init__(mensagem)
        self.status = status


def _handle_do_usuario(usuario_id: int) -> bytes:
    """Identificador opaco da pessoa dentro da passkey.

    Não é o id do banco em claro nem o e-mail: o aparelho guarda esse
    valor, e não há motivo para ele revelar nada.
    """
    return hashlib.sha256(f"lastro-usuario:{usuario_id}".encode()).digest()[:16]


def _guardar_desafio(desafio: bytes, tipo: str, usuario_id: int | None) -> str:
    desafio_id = secrets.token_hex(16)
    with cursor(commit=True) as cur:
        cur.execute("DELETE FROM desafios_webauthn WHERE expira_em < %s", (datetime.now(),))
        cur.execute(
            "INSERT INTO desafios_webauthn (id, desafio, tipo, usuario_id, expira_em) "
            "VALUES (%s, %s, %s, %s, %s)",
            (desafio_id, desafio, tipo, usuario_id,
             datetime.now() + timedelta(minutes=DESAFIO_MINUTOS)),
        )
    return desafio_id


def _consumir_desafio(desafio_id: str, tipo: str, usuario_id: int | None) -> bytes:
    """Devolve o desafio e o apaga na mesma transação: vale uma vez só."""
    with cursor(commit=True) as cur:
        cur.execute(
            "SELECT desafio, usuario_id, expira_em FROM desafios_webauthn "
            "WHERE id = %s AND tipo = %s FOR UPDATE",
            (str(desafio_id or "")[:32], tipo),
        )
        linha = cur.fetchone()
        if not linha:
            raise PasskeyInvalida("O pedido expirou. Tente de novo.")
        cur.execute("DELETE FROM desafios_webauthn WHERE id = %s", (desafio_id,))
    if linha["expira_em"] < datetime.now():
        raise PasskeyInvalida("O pedido expirou. Tente de novo.")
    if linha["usuario_id"] != usuario_id:
        raise PasskeyInvalida("O pedido não é desta sessão.")
    return bytes(linha["desafio"])


# ── Cadastro ─────────────────────────────────────────────────
def opcoes_cadastro(usuario_id: int, email: str, nome: str) -> dict:
    existentes = buscar_todos(
        "SELECT credencial_id FROM passkeys WHERE usuario_id = %s", (usuario_id,)
    )
    opcoes = generate_registration_options(
        rp_id=config.WEBAUTHN_RP_ID,
        rp_name=config.WEBAUTHN_RP_NOME,
        user_id=_handle_do_usuario(usuario_id),
        user_name=email,
        user_display_name=nome or email,
        # O mesmo aparelho não cadastra duas vezes.
        exclude_credentials=[
            PublicKeyCredentialDescriptor(id=bytes(p["credencial_id"])) for p in existentes
        ],
        authenticator_selection=AuthenticatorSelectionCriteria(
            # Passkey "descobrível": entra sem digitar o e-mail.
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
    )
    desafio_id = _guardar_desafio(opcoes.challenge, "cadastro", usuario_id)
    return {"desafioId": desafio_id, "opcoes": json.loads(options_to_json(opcoes))}


def cadastrar(usuario_id: int, desafio_id: str, resposta: dict, apelido: str) -> dict:
    desafio = _consumir_desafio(desafio_id, "cadastro", usuario_id)
    try:
        v = verify_registration_response(
            credential=resposta,
            expected_challenge=desafio,
            expected_rp_id=config.WEBAUTHN_RP_ID,
            expected_origin=config.WEBAUTHN_ORIGENS,
            require_user_verification=True,
        )
    except Exception as e:  # a biblioteca levanta vários tipos; todos = resposta inválida
        raise PasskeyInvalida("O aparelho não confirmou o cadastro.") from e

    apelido = (apelido or "").strip()[:80] or "Aparelho"
    with cursor(commit=True) as cur:
        cur.execute("SELECT 1 FROM passkeys WHERE credencial_id = %s", (v.credential_id,))
        if cur.fetchone():
            raise PasskeyInvalida("Este aparelho já está cadastrado.")
        cur.execute(
            "INSERT INTO passkeys (usuario_id, credencial_id, chave_publica, contador, apelido) "
            "VALUES (%s, %s, %s, %s, %s)",
            (usuario_id, v.credential_id, v.credential_public_key, v.sign_count, apelido),
        )
        novo_id = cur.lastrowid
    return {"id": novo_id, "apelido": apelido}


# ── Entrada ──────────────────────────────────────────────────
def opcoes_entrada() -> dict:
    opcoes = generate_authentication_options(
        rp_id=config.WEBAUTHN_RP_ID,
        # Lista vazia: o aparelho oferece as passkeys que tem para o domínio.
        allow_credentials=[],
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    desafio_id = _guardar_desafio(opcoes.challenge, "entrada", None)
    return {"desafioId": desafio_id, "opcoes": json.loads(options_to_json(opcoes))}


def entrar(desafio_id: str, resposta: dict) -> int:
    """Confere a assinatura e devolve o id da pessoa. Nunca confia no
    que o navegador diz sobre quem é: o dono sai da credencial no banco."""
    desafio = _consumir_desafio(desafio_id, "entrada", None)
    try:
        credencial_id = base64url_to_bytes(str(resposta.get("rawId") or resposta.get("id") or ""))
    except Exception as e:
        raise PasskeyInvalida("Resposta do aparelho ilegível.") from e

    p = buscar_um(
        "SELECT id, usuario_id, chave_publica, contador FROM passkeys WHERE credencial_id = %s",
        (credencial_id,),
    )
    if not p:
        raise PasskeyInvalida(
            "Esta passkey não está cadastrada (pode ter sido removida). Entre com senha e código.",
            status=404,
        )

    try:
        v = verify_authentication_response(
            credential=resposta,
            expected_challenge=desafio,
            expected_rp_id=config.WEBAUTHN_RP_ID,
            expected_origin=config.WEBAUTHN_ORIGENS,
            credential_public_key=bytes(p["chave_publica"]),
            credential_current_sign_count=int(p["contador"]),
            require_user_verification=True,
        )
    except Exception as e:
        raise PasskeyInvalida("O aparelho não confirmou a entrada.") from e

    with cursor(commit=True) as cur:
        cur.execute(
            "UPDATE passkeys SET contador = %s, usado_em = %s WHERE id = %s",
            (v.new_sign_count, datetime.now(), p["id"]),
        )
    return int(p["usuario_id"])


# ── Lista e remoção ──────────────────────────────────────────
def listar(usuario_id: int) -> list:
    linhas = buscar_todos(
        "SELECT id, apelido, criado_em, usado_em FROM passkeys "
        "WHERE usuario_id = %s ORDER BY criado_em DESC",
        (usuario_id,),
    )
    return [
        {
            "id": r["id"],
            "apelido": r["apelido"],
            "criadoEm": r["criado_em"].isoformat(timespec="seconds"),
            "usadoEm": r["usado_em"].isoformat(timespec="seconds") if r["usado_em"] else None,
        }
        for r in linhas
    ]


def remover(usuario_id: int, passkey_id: int) -> bool:
    with cursor(commit=True) as cur:
        cur.execute(
            "DELETE FROM passkeys WHERE id = %s AND usuario_id = %s", (passkey_id, usuario_id)
        )
        return cur.rowcount == 1
