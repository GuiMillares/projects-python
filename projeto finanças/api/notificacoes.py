"""Notificações push: transações novas, entradas, saídas e faturas vencendo.

Web Push com VAPID. O navegador de cada aparelho se inscreve (Configurações >
Notificações) e entrega um endpoint do serviço de push do sistema (Apple,
Google, Mozilla). O servidor cifra a mensagem para aquele aparelho
(aes128gcm) e assina o envio com a chave VAPID; o serviço de push só leva o
pacote fechado.

De onde vêm os avisos:
* transações novas: o webhook da Pluggy de cada pessoa avisa, a API importa
  e notifica o que entrou agora (app.py, pluggy_webhook). A rotina diária
  também importa, como rede de segurança;
* faturas vencendo: a rotina diária (cron da Vercel) olha os cartões.

iPhone: só recebe com o app instalado na tela inicial (iOS 16.4+).

Sem FIN_VAPID_PUBLICA e FIN_VAPID_PRIVADA configuradas, nada é enviado e a
tela diz que o servidor ainda não está pronto.
"""

import hashlib
import json
import logging
from decimal import Decimal

import config
from db import buscar_todos, buscar_um, cursor

log = logging.getLogger(__name__)

TIPOS = ("entradas", "saidas", "faturas")


def disponivel() -> bool:
    return bool(config.VAPID_PUBLICA and config.VAPID_PRIVADA)


def _hash(texto: str) -> str:
    return hashlib.sha256(texto.encode()).hexdigest()


# ── Inscrições ───────────────────────────────────────────────
def inscrever(usuario_id: int, inscricao: dict, aparelho: str = "") -> None:
    endpoint = str(inscricao.get("endpoint") or "")
    chaves = inscricao.get("keys") or {}
    p256dh, auth = str(chaves.get("p256dh") or ""), str(chaves.get("auth") or "")
    if not endpoint.startswith("https://") or len(endpoint) > 1000 or not p256dh or not auth:
        raise ValueError("Inscrição de notificação inválida.")
    with cursor(commit=True) as cur:
        # O mesmo aparelho reinscrito (ou passado de uma conta para outra)
        # fica com o dono mais recente: um endpoint, uma pessoa.
        cur.execute(
            "INSERT INTO push_inscricoes (usuario_id, endpoint_hash, endpoint, p256dh, auth, aparelho) "
            "VALUES (%s, %s, %s, %s, %s, %s) "
            "ON DUPLICATE KEY UPDATE usuario_id = VALUES(usuario_id), p256dh = VALUES(p256dh), "
            "auth = VALUES(auth), aparelho = VALUES(aparelho)",
            (usuario_id, _hash(endpoint), endpoint, p256dh[:200], auth[:100], aparelho[:80]),
        )


def desinscrever(usuario_id: int, endpoint: str) -> None:
    with cursor(commit=True) as cur:
        cur.execute(
            "DELETE FROM push_inscricoes WHERE usuario_id = %s AND endpoint_hash = %s",
            (usuario_id, _hash(str(endpoint or ""))),
        )


def aparelhos(usuario_id: int) -> int:
    return buscar_um(
        "SELECT COUNT(*) AS n FROM push_inscricoes WHERE usuario_id = %s", (usuario_id,)
    )["n"]


def inscrito(usuario_id: int, endpoint: str) -> bool:
    return bool(buscar_um(
        "SELECT 1 AS x FROM push_inscricoes WHERE usuario_id = %s AND endpoint_hash = %s",
        (usuario_id, _hash(str(endpoint or ""))),
    ))


# ── Preferências ─────────────────────────────────────────────
def preferencias(usuario_id: int) -> dict:
    p = buscar_um(
        "SELECT entradas, saidas, faturas FROM notif_preferencias WHERE usuario_id = %s",
        (usuario_id,),
    )
    return {t: bool(p[t]) if p else True for t in TIPOS}


def salvar_preferencias(usuario_id: int, novas: dict) -> dict:
    atual = preferencias(usuario_id)
    atual.update({t: bool(novas[t]) for t in TIPOS if t in novas})
    with cursor(commit=True) as cur:
        cur.execute(
            "INSERT INTO notif_preferencias (usuario_id, entradas, saidas, faturas) "
            "VALUES (%s, %s, %s, %s) ON DUPLICATE KEY UPDATE entradas = VALUES(entradas), "
            "saidas = VALUES(saidas), faturas = VALUES(faturas)",
            (usuario_id, int(atual["entradas"]), int(atual["saidas"]), int(atual["faturas"])),
        )
    return atual


# ── Envio ────────────────────────────────────────────────────
def enviar(usuario_id: int, titulo: str, corpo: str, url: str = "/app", tag: str | None = None) -> int:
    """Manda para todos os aparelhos da pessoa. Devolve quantos receberam.
    Aparelho que o serviço de push diz não existir mais (404/410) sai da
    lista. Nunca levanta exceção: notificação não pode derrubar quem chama."""
    if not disponivel():
        return 0
    from py_vapid import Vapid02
    from pywebpush import WebPushException, webpush

    try:
        chave = Vapid02.from_raw(config.VAPID_PRIVADA.encode())
    except Exception:  # noqa: BLE001
        log.error("FIN_VAPID_PRIVADA ilegível: notificações desligadas")
        return 0

    carga = json.dumps({"titulo": titulo, "corpo": corpo, "url": url, "tag": tag})
    entregues = 0
    for i in buscar_todos(
        "SELECT id, endpoint, p256dh, auth FROM push_inscricoes WHERE usuario_id = %s", (usuario_id,)
    ):
        try:
            webpush(
                subscription_info={"endpoint": i["endpoint"], "keys": {"p256dh": i["p256dh"], "auth": i["auth"]}},
                data=carga,
                vapid_private_key=chave,
                vapid_claims={"sub": config.VAPID_CONTATO},
                timeout=6,
                ttl=60 * 60 * 24,
            )
            entregues += 1
        except WebPushException as e:
            status = getattr(getattr(e, "response", None), "status_code", None)
            if status in (404, 410):
                with cursor(commit=True) as cur:
                    cur.execute("DELETE FROM push_inscricoes WHERE id = %s", (i["id"],))
            else:
                log.warning("push falhou (%s) para a inscrição %s", status, i["id"])
        except Exception:  # noqa: BLE001
            log.exception("push falhou para a inscrição %s", i["id"])
    return entregues


def uma_vez(usuario_id: int, chave: str) -> bool:
    """True na primeira vez que a chave aparece para a pessoa (e grava)."""
    with cursor(commit=True) as cur:
        cur.execute(
            "INSERT IGNORE INTO notificacoes_enviadas (usuario_id, chave) VALUES (%s, %s)",
            (usuario_id, chave[:160]),
        )
        return cur.rowcount == 1


# ── Textos ───────────────────────────────────────────────────
def brl(v) -> str:
    texto = f"{Decimal(str(v)):,.2f}"
    return "R$ " + texto.replace(",", "_").replace(".", ",").replace("_", ".")


def avisar_transacoes(usuario_id: int, novas: list) -> int:
    """Notifica o que acabou de ser importado, respeitando as preferências.
    Até 3: uma por lançamento. Mais que isso: um resumo só, para não
    soterrar o celular depois de uma importação grande."""
    if not novas or not aparelhos(usuario_id):
        return 0
    pref = preferencias(usuario_id)
    entradas = [t for t in novas if t["natureza"] == "receita" and pref["entradas"]]
    saidas = [t for t in novas if t["natureza"] == "despesa" and pref["saidas"]]
    lista = sorted(entradas + saidas, key=lambda t: str(t["data"]))
    if not lista:
        return 0

    if len(lista) <= 3:
        for t in lista:
            if t["natureza"] == "receita":
                enviar(usuario_id, f"Entrou {brl(t['valor'])}", t["nome"], "/app/entradas", f"t-{t['origem_id']}")
            else:
                enviar(usuario_id, f"Saída de {brl(t['valor'])}", t["nome"], "/app/saidas", f"t-{t['origem_id']}")
        return len(lista)

    partes = []
    if saidas:
        partes.append(f"{len(saidas)} {'saída' if len(saidas) == 1 else 'saídas'} ({brl(sum(t['valor'] for t in saidas))})")
    if entradas:
        partes.append(f"{len(entradas)} {'entrada' if len(entradas) == 1 else 'entradas'} ({brl(sum(t['valor'] for t in entradas))})")
    enviar(usuario_id, f"{len(lista)} lançamentos novos", " e ".join(partes), "/app", "lote")
    return len(lista)


def avisar_faturas(usuario_id: int, cartoes: list, hoje) -> int:
    """Fatura com valor que vence de hoje a 3 dias. Cada cartão avisa uma
    vez por vencimento em cada marco (3 dias, véspera, no dia)."""
    if not preferencias(usuario_id)["faturas"]:
        return 0
    from datetime import date as _date

    enviados = 0
    for c in cartoes:
        f = c.get("faturaAtual") or {}
        if not f.get("vencimento") or not f.get("valor") or Decimal(str(f["valor"])) <= 0:
            continue
        dias = (_date.fromisoformat(f["vencimento"]) - hoje).days
        if dias not in (0, 1, 3):
            continue
        if not uma_vez(usuario_id, f"fatura:{c.get('id')}:{f['vencimento']}:{dias}"):
            continue
        quando = {0: "vence hoje", 1: "vence amanhã", 3: "vence em 3 dias"}[dias]
        enviar(usuario_id, f"Fatura {quando}", f"{c.get('nome', 'Cartão').strip()}: {brl(f['valor'])}",
               "/app/contas", f"fatura-{c.get('id')}")
        enviados += 1
    return enviados
