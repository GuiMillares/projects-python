"""Gera o par de chaves VAPID das notificações push.

    python ops/gerar_vapid.py

Imprime as duas variáveis para colar na Vercel (Settings > Environment
Variables) e no .env de quem roda local:

    FIN_VAPID_PUBLICA  vai para o navegador; não é segredo
    FIN_VAPID_PRIVADA  assina cada envio; É SEGREDO, guarde no gerenciador

Trocar o par depois invalida as inscrições de todos os aparelhos: cada
pessoa precisa ativar as notificações de novo. Gere uma vez só.
"""

import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


chave = ec.generate_private_key(ec.SECP256R1())
privada = chave.private_numbers().private_value.to_bytes(32, "big")
publica = chave.public_key().public_bytes(
    serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
)
print(f"FIN_VAPID_PUBLICA={b64url(publica)}")
print(f"FIN_VAPID_PRIVADA={b64url(privada)}")
