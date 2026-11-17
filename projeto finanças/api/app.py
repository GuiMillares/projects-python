"""API local do painel financeiro.

Escuta só em 127.0.0.1: é o processo com quem o webview do Tauri
conversa. Substitui o par Firebase Auth + Cloud Functions: o login
virou senha com scrypt neste processo, e o 2FA que antes rodava na
Cloud Function roda em seguranca.py. A regra que valia lá continua
valendo aqui: o segredo TOTP não sai do servidor.

Rodar:
    python app.py
"""

import hashlib
import hmac
import re
import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from decimal import Decimal
from functools import wraps

from flask import Flask, g, jsonify, request
from werkzeug.exceptions import HTTPException

import cofre
import config
import cotacoes
import documentos
import gamificacao
import ia
import espacos
import notificacoes
import openfinance
import passkeys
import seguranca
import visao
from db import buscar_todos, buscar_um, cursor

app = Flask(__name__)

# Teto de corpo de requisição. A maior coisa que trafega aqui é a foto de
# perfil (algumas dezenas de KB); 2MB é folga suficiente e evita que um
# POST gigante ocupe memória do processo.
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024


# ── CORS ─────────────────────────────────────────────────────
# Lista fechada de origens. Sem `*`: a API responde com credencial
# de sessão, e liberar geral deixaria qualquer página aberta no
# navegador falar com ela.
@app.after_request
def cors(resp):
    origem = request.headers.get("Origin")
    if origem in config.ORIGENS_PERMITIDAS:
        resp.headers["Access-Control-Allow-Origin"] = origem
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
        resp.headers["Vary"] = "Origin"
    return resp


@app.route("/api/<path:_qualquer>", methods=["OPTIONS"])
def preflight(_qualquer):
    return ("", 204)


# ── Erros ────────────────────────────────────────────────────
def erro(mensagem, status=400):
    return jsonify({"erro": mensagem}), status


@app.errorhandler(Exception)
def erro_inesperado(e):
    # HTTPException precisa passar direto. Sem esta linha, o handler
    # engole 404, 405 e 413 e devolve todos como 500 "Erro interno.":
    # rota errada vira falha de servidor e some o motivo real.
    if isinstance(e, HTTPException):
        return erro(e.description, e.code)

    # Log completo no terminal, mensagem genérica na resposta: detalhe
    # de exceção em API é mapa para quem estiver sondando.
    app.logger.exception("falha não tratada", exc_info=e)
    return erro("Erro interno.", 500)


# ── Autenticação das rotas ───────────────────────────────────
def _token_do_header():
    cabecalho = request.headers.get("Authorization", "")
    return cabecalho[7:].strip() if cabecalho.startswith("Bearer ") else ""


def exige_sessao(completa=True, sem_aceite=False):
    """Protege a rota.

    completa=True   → exige 2FA já validado (rotas de dado).
    completa=False  → aceita a sessão parcial (só as rotas de 2FA).
    sem_aceite=True → dispensa o aceite da versão atual dos termos. Só nas
                      rotas que a tela de aceite usa e nas que exercem
                      direito do titular (exportar, apagar a conta): quem
                      não aceita os termos ainda pode levar ou apagar o
                      que é dele.
    """
    def decorador(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            sessao = seguranca.ler_sessao(_token_do_header())
            if not sessao:
                return erro("Sessão inválida ou expirada.", 401)
            if completa and not sessao["dois_fatores_ok"]:
                return erro("Verificação em duas etapas pendente.", 403)
            if completa and not sem_aceite and sessao["aceite_versao"] != documentos.VERSAO:
                return erro("Aceite os termos de uso e a política de privacidade para continuar.", 428)
            g.sessao = sessao
            return fn(*a, **kw)
        return wrapper
    return decorador


# ── Login ────────────────────────────────────────────────────
@app.post("/api/auth/login")
def login():
    dados = request.get_json(silent=True) or {}
    email = (dados.get("email") or "").strip().lower()
    senha = dados.get("senha") or ""

    usuario = buscar_um(
        "SELECT id, email, senha_hash, totp_confirmado, tentativas, bloqueado_ate "
        "FROM usuarios WHERE email = %s",
        (email,),
    )

    if usuario and seguranca.esta_bloqueado(usuario):
        return erro(
            f"Muitas tentativas. Tente de novo em alguns minutos.", 429
        )

    # Mesma resposta para e-mail inexistente e senha errada, senão a
    # tela vira um oráculo de quais e-mails têm conta.
    if not usuario or not seguranca.conferir_senha(senha, usuario["senha_hash"]):
        if usuario:
            seguranca.registrar_falha(usuario["id"])
        return erro("E-mail ou senha incorretos.", 401)

    seguranca.limpar_falhas(usuario["id"])
    seguranca.limpar_sessoes_expiradas()

    # Sessão nasce PARCIAL. Só o 2FA a promove. Não existe caminho
    # daqui para as rotas de dado sem passar pelo código.
    token = seguranca.criar_sessao(usuario["id"], dois_fatores_ok=False)
    return jsonify({
        "token": token,
        "etapa": "2fa" if usuario["totp_confirmado"] else "setup2fa",
    })


@app.post("/api/auth/logout")
@exige_sessao(completa=False)
def logout():
    seguranca.encerrar_sessao(_token_do_header())
    return jsonify({"ok": True})


# ── 2FA ──────────────────────────────────────────────────────
@app.post("/api/auth/2fa/setup")
@exige_sessao(completa=False)
def setup_2fa():
    """Devolve o otpauth:// do cadastro (QR code, link e chave na tela).

    Recusa quem já tem 2FA confirmado: trocar o autenticador exige a sessão
    completa e passa por desativar o 2FA em Configurações, com o código.
    """
    sessao = g.sessao
    uri = seguranca.gerar_segredo(sessao["usuario_id"], sessao["email"])
    if uri is None:
        return erro("A verificação em duas etapas já está ativa nesta conta.", 409)
    return jsonify({"otpauthUri": uri})


@app.post("/api/auth/2fa/verify")
@exige_sessao(completa=False)
def verificar_2fa():
    sessao = g.sessao
    codigo = (request.get_json(silent=True) or {}).get("codigo", "")

    # O mesmo bloqueio do login vale aqui. Sem ele, quem tem só a senha
    # chutava códigos de 6 dígitos à vontade enquanto a sessão parcial
    # durasse: registrar a falha sem conferir o bloqueio não trava nada.
    usuario = buscar_um("SELECT bloqueado_ate FROM usuarios WHERE id = %s", (sessao["usuario_id"],))
    if usuario and seguranca.esta_bloqueado(usuario):
        return erro("Muitas tentativas. Tente de novo em alguns minutos.", 429)

    if not seguranca.conferir_codigo(sessao["usuario_id"], codigo):
        seguranca.registrar_falha(sessao["usuario_id"])
        return erro("Código incorreto ou expirado.", 401)

    seguranca.limpar_falhas(sessao["usuario_id"])
    seguranca.promover_sessao(sessao["id"])
    return jsonify({"ok": True})


# ── Espaço compartilhado e convites (api/espacos.py) ─────────
_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,120}\.[^@\s]{2,}$")


def _erro_espaco(e):
    return erro(str(e), e.status)


@app.get("/api/convites/<token>")
def convite_ver(token):
    """Público: a página do convite mostra quem convidou. Com sessão, a
    própria pessoa que já pegou o convite também consegue ver."""
    sessao = seguranca.ler_sessao(_token_do_header())
    uid = sessao["usuario_id"] if sessao and sessao["dois_fatores_ok"] else None
    try:
        return jsonify(espacos.ver_convite(token, uid))
    except espacos.EspacoErro as e:
        return _erro_espaco(e)


@app.post("/api/convites/<token>/cadastro")
def convite_cadastro(token):
    """Cria a conta por um convite. Não existe cadastro aberto: sem link
    válido, não há conta nova. A conta e a captura do convite acontecem na
    mesma transação. A sessão nasce parcial, como num login com senha: o
    próximo passo é cadastrar o 2FA."""
    d = request.get_json(silent=True) or {}
    email = str(d.get("email") or "").strip().lower()
    nome = str(d.get("nome") or "").strip()[:120]
    senha = str(d.get("senha") or "")
    if len(email) > 190 or not _EMAIL.match(email):
        return erro("Confira o e-mail.")
    if not 8 <= len(senha) <= 200:
        return erro("A senha precisa ter pelo menos 8 caracteres.")

    try:
        with cursor(commit=True) as cur:
            cur.execute("SELECT id FROM usuarios WHERE email = %s", (email,))
            if cur.fetchone():
                return erro(
                    "Já existe uma conta com esse e-mail. Entre com ela e abra o link de novo.", 409
                )
            cur.execute(
                "INSERT INTO usuarios (email, senha_hash, nome) VALUES (%s, %s, %s)",
                (email, seguranca.hash_senha(senha), nome),
            )
            uid = cur.lastrowid
            espacos.pegar_convite(cur, token, uid)
    except espacos.EspacoErro as e:
        return _erro_espaco(e)

    token_sessao = seguranca.criar_sessao(uid, dois_fatores_ok=False)
    return jsonify({"token": token_sessao, "etapa": "setup2fa"}), 201


@app.post("/api/convites/<token>/pegar")
@exige_sessao()
def convite_pegar(token):
    """Quem já tem conta abre o link: o convite fica preso a ela e a
    pergunta "vincular?" aparece."""
    try:
        with cursor(commit=True) as cur:
            espacos.pegar_convite(cur, token, g.sessao["usuario_id"])
    except espacos.EspacoErro as e:
        return _erro_espaco(e)
    return jsonify(espacos.convite_pendente(g.sessao["usuario_id"]))


@app.get("/api/espaco")
@exige_sessao()
def espaco_ler():
    return jsonify(espacos.resumo(g.sessao["usuario_id"]))


@app.post("/api/espaco/convite")
@exige_sessao()
def espaco_convidar():
    try:
        return jsonify(espacos.criar_convite(g.sessao["usuario_id"])), 201
    except espacos.EspacoErro as e:
        return _erro_espaco(e)


@app.delete("/api/espaco/convite")
@exige_sessao()
def espaco_cancelar_convite():
    espacos.cancelar_convite(g.sessao["usuario_id"])
    return jsonify({"ok": True})


@app.post("/api/espaco/aceitar")
@exige_sessao()
def espaco_aceitar():
    convite_id = (request.get_json(silent=True) or {}).get("conviteId")
    if not isinstance(convite_id, int):
        return erro("Convite inválido.")
    try:
        espacos.aceitar(g.sessao["usuario_id"], convite_id)
    except espacos.EspacoErro as e:
        return _erro_espaco(e)
    return jsonify(espacos.resumo(g.sessao["usuario_id"]))


@app.post("/api/espaco/recusar")
@exige_sessao()
def espaco_recusar():
    convite_id = (request.get_json(silent=True) or {}).get("conviteId")
    if isinstance(convite_id, int):
        espacos.recusar(g.sessao["usuario_id"], convite_id)
    return jsonify({"ok": True})


@app.post("/api/espaco/sair")
@exige_sessao()
def espaco_sair():
    espacos.sair(g.sessao["usuario_id"])
    return jsonify(espacos.resumo(g.sessao["usuario_id"]))


@app.delete("/api/espaco/membros/<int:membro_id>")
@exige_sessao()
def espaco_remover(membro_id):
    try:
        espacos.remover_membro(g.sessao["usuario_id"], membro_id)
    except espacos.EspacoErro as e:
        return _erro_espaco(e)
    return jsonify(espacos.resumo(g.sessao["usuario_id"]))


# ── Notificações push (api/notificacoes.py) ──────────────────
def _garantir_webhook(uid):
    """Webhook da Pluggy desta pessoa, criado com a credencial DELA. Sem
    credencial ou sem endereço público (rodando no PC), não há webhook: a
    rotina diária cobre. Devolve um texto curto do estado para a tela."""
    cred, _ = _credencial(uid)
    if not cred:
        return "semCredencial"
    if not config.URL_PUBLICA.startswith("https://"):
        return "semEnderecoPublico"
    atual = buscar_um("SELECT webhook_id, client_id FROM webhooks_pluggy WHERE usuario_id = %s", (uid,))
    if atual and atual["webhook_id"] and atual["client_id"] == cred.client_id:
        return "ok"
    if atual:
        _desligar_webhook(uid, cred)

    rota, segredo = secrets.token_hex(16), secrets.token_urlsafe(32)
    webhook_id, aviso = openfinance.criar_webhook(
        cred, f"{config.URL_PUBLICA}/api/pluggy/webhook/{rota}", segredo
    )
    if aviso:
        app.logger.warning("webhook da Pluggy não criado: %s", aviso)
        return "falhou"
    with cursor(commit=True) as cur:
        cur.execute(
            "INSERT INTO webhooks_pluggy (usuario_id, rota, segredo_hash, webhook_id, client_id) "
            "VALUES (%s, %s, %s, %s, %s) ON DUPLICATE KEY UPDATE rota = VALUES(rota), "
            "segredo_hash = VALUES(segredo_hash), webhook_id = VALUES(webhook_id), "
            "client_id = VALUES(client_id)",
            (uid, rota, hashlib.sha256(segredo.encode()).hexdigest(), webhook_id, cred.client_id),
        )
    return "ok"


def _desligar_webhook(uid, cred):
    linha = buscar_um("SELECT webhook_id FROM webhooks_pluggy WHERE usuario_id = %s", (uid,))
    if not linha:
        return
    openfinance.apagar_webhook(cred, linha["webhook_id"])
    with cursor(commit=True) as cur:
        cur.execute("DELETE FROM webhooks_pluggy WHERE usuario_id = %s", (uid,))


@app.get("/api/push")
@exige_sessao()
def push_estado():
    uid = g.sessao["usuario_id"]
    endpoint = request.args.get("endpoint") or ""
    return jsonify({
        "disponivel": notificacoes.disponivel(),
        "chavePublica": config.VAPID_PUBLICA or None,
        "aparelhos": notificacoes.aparelhos(uid),
        "esteAparelho": notificacoes.inscrito(uid, endpoint) if endpoint else False,
        "preferencias": notificacoes.preferencias(uid),
        "bancosAvisam": bool(buscar_um(
            "SELECT 1 AS x FROM webhooks_pluggy WHERE usuario_id = %s AND webhook_id IS NOT NULL", (uid,)
        )),
    })


@app.post("/api/push/inscricao")
@exige_sessao()
def push_inscrever():
    if not notificacoes.disponivel():
        return erro("O servidor ainda não está pronto para notificações.", 503)
    d = request.get_json(silent=True) or {}
    try:
        notificacoes.inscrever(g.sessao["usuario_id"], d.get("inscricao") or {}, str(d.get("aparelho") or ""))
    except ValueError as e:
        return erro(str(e))
    return jsonify({"ok": True, "bancos": _garantir_webhook(g.sessao["usuario_id"])}), 201


@app.delete("/api/push/inscricao")
@exige_sessao()
def push_desinscrever():
    notificacoes.desinscrever(g.sessao["usuario_id"], (request.get_json(silent=True) or {}).get("endpoint"))
    return jsonify({"ok": True})


@app.put("/api/push/preferencias")
@exige_sessao()
def push_preferencias():
    return jsonify(notificacoes.salvar_preferencias(g.sessao["usuario_id"], request.get_json(silent=True) or {}))


@app.post("/api/push/teste")
@exige_sessao()
def push_teste():
    n = notificacoes.enviar(
        g.sessao["usuario_id"], "Notificações ligadas",
        "É assim que o Lastro vai te avisar de entradas, saídas e faturas.", "/app", "teste",
    )
    if not n:
        return erro("Nenhum aparelho recebeu. Ative as notificações neste aparelho primeiro.", 409)
    return jsonify({"ok": True, "aparelhos": n})


@app.post("/api/pluggy/webhook/<rota>")
def pluggy_webhook(rota):
    """Aviso da Pluggy de transações novas. Só vale com o segredo que foi
    combinado na criação do webhook (a Pluggy não assina os avisos). O
    corpo é só um sinal: o que entra vem da importação normal, relida da
    Pluggy, como a própria documentação dela recomenda.

    A Pluggy espera 2XX em até 10 s; se passar disso ela tenta de novo mais
    tarde, e a importação não duplica nada (nem a notificação, que só sai
    para o que entrou agora)."""
    w = buscar_um(
        "SELECT usuario_id, segredo_hash FROM webhooks_pluggy WHERE rota = %s", (str(rota)[:32],)
    )
    segredo = request.headers.get("X-Lastro-Segredo", "")
    if not w or not hmac.compare_digest(hashlib.sha256(segredo.encode()).hexdigest(), w["segredo_hash"]):
        return erro("Não autorizado.", 401)

    d = request.get_json(silent=True) or {}
    if d.get("event") != "transactions/created":
        return jsonify({"ok": True})
    uid = w["usuario_id"]
    if not buscar_um(
        "SELECT 1 AS x FROM conexoes_bancarias WHERE usuario_id = %s AND item_id = %s",
        (uid, str(d.get("itemId") or "")[:36]),
    ):
        return jsonify({"ok": True})

    hoje = date.today()
    desde = hoje - timedelta(days=7)
    try:
        minima = date.fromisoformat(str(d.get("transactionsMinDate") or "")[:10])
        desde = max(min(desde, minima), hoje - timedelta(days=35))
    except ValueError:
        pass
    try:
        resultado, aviso = importar_para(uid, desde)
        if resultado:
            notificacoes.avisar_transacoes(uid, resultado["_novas"])
    except Exception:  # noqa: BLE001
        app.logger.exception("webhook da Pluggy: falha ao importar")
    return jsonify({"ok": True})


@app.get("/api/cron/diario")
def cron_diario():
    """Rotina diária (cron da Vercel, 8h de Brasília): faturas vencendo e,
    como rede de segurança do webhook, a importação da última semana de
    quem tem notificações ligadas."""
    esperado = f"Bearer {config.CRON_SEGREDO}"
    if not config.CRON_SEGREDO or not hmac.compare_digest(request.headers.get("Authorization", ""), esperado):
        return erro("Não autorizado.", 401)

    hoje = date.today()
    pessoas = [r["usuario_id"] for r in buscar_todos("SELECT DISTINCT usuario_id FROM push_inscricoes")]
    resumo = {"pessoas": len(pessoas), "transacoes": 0, "faturas": 0}
    for uid in pessoas:
        try:
            conexoes = _conexoes(uid)
            cred, _ = _credencial(uid)
            if not conexoes or not cred:
                continue
            resultado, _ = importar_para(uid, hoje - timedelta(days=7))
            if resultado:
                resumo["transacoes"] += notificacoes.avisar_transacoes(uid, resultado["_novas"])
            with ThreadPoolExecutor(max_workers=max(1, min(5, len(conexoes)))) as ex:
                lidas = list(ex.map(lambda c: openfinance.panorama(cred, c["item_id"]), conexoes))
            cartoes = [k for dados, _ in lidas if dados for k in dados.get("cartoes", [])]
            resumo["faturas"] += notificacoes.avisar_faturas(uid, cartoes, hoje)
        except Exception:  # noqa: BLE001
            app.logger.exception("rotina diária falhou para uma pessoa")
    return jsonify({"ok": True, **resumo})


# ── Passkeys (Face ID / digital) ─────────────────────────────
# Entrar: público, como o login com senha. A assinatura do aparelho é
# conferida contra a chave pública guardada, e a sessão já nasce completa
# (ver o porquê em passkeys.py). Cadastrar, listar e remover: só com
# sessão completa.
@app.post("/api/auth/passkey/opcoes")
def passkey_opcoes_entrada():
    return jsonify(passkeys.opcoes_entrada())


@app.post("/api/auth/passkey/entrar")
def passkey_entrar():
    d = request.get_json(silent=True) or {}
    resposta = d.get("resposta")
    if not isinstance(resposta, dict):
        return erro("Resposta do aparelho ausente.")
    try:
        usuario_id = passkeys.entrar(d.get("desafioId"), resposta)
    except passkeys.PasskeyInvalida as e:
        return erro(str(e), e.status or 401)

    seguranca.limpar_sessoes_expiradas()
    token = seguranca.criar_sessao(usuario_id, dois_fatores_ok=True)
    return jsonify({"token": token})


@app.get("/api/passkeys")
@exige_sessao()
def passkeys_listar():
    return jsonify({"passkeys": passkeys.listar(g.sessao["usuario_id"])})


@app.post("/api/passkeys/opcoes")
@exige_sessao()
def passkeys_opcoes_cadastro():
    s = g.sessao
    return jsonify(passkeys.opcoes_cadastro(s["usuario_id"], s["email"], s["nome"]))


@app.post("/api/passkeys")
@exige_sessao()
def passkeys_cadastrar():
    d = request.get_json(silent=True) or {}
    resposta = d.get("resposta")
    if not isinstance(resposta, dict):
        return erro("Resposta do aparelho ausente.")
    try:
        nova = passkeys.cadastrar(
            g.sessao["usuario_id"], d.get("desafioId"), resposta, d.get("apelido") or ""
        )
    except passkeys.PasskeyInvalida as e:
        return erro(str(e), 400)
    return jsonify(nova), 201


@app.delete("/api/passkeys/<int:passkey_id>")
@exige_sessao()
def passkeys_remover(passkey_id):
    if not passkeys.remover(g.sessao["usuario_id"], passkey_id):
        return erro("Passkey não encontrada.", 404)
    return jsonify({"ok": True})


@app.post("/api/auth/2fa/disable")
@exige_sessao()
def desativar_2fa():
    """Desativar também exige um código válido, senão a segunda etapa
    cairia com dois cliques em qualquer sessão deixada aberta."""
    sessao = g.sessao
    codigo = (request.get_json(silent=True) or {}).get("codigo", "")

    if not seguranca.conferir_codigo(sessao["usuario_id"], codigo):
        return erro("Código incorreto. O 2FA continua ativo.", 401)

    seguranca.remover_2fa(sessao["usuario_id"])
    return jsonify({"ok": True})


# ── Perfil ───────────────────────────────────────────────────
@app.get("/api/perfil")
@exige_sessao(sem_aceite=True)
def ler_perfil():
    """Também é como o front descobre que falta o aceite: `aceitePendente`
    manda para a tela de aceite em vez de para o login."""
    s = g.sessao
    # A foto não vem no JOIN da sessão de propósito: ler_sessao roda em
    # toda requisição, e arrastar dezenas de KB de imagem junto seria
    # desperdício em cada chamada de dado.
    linha = buscar_um("SELECT foto FROM usuarios WHERE id = %s", (s["usuario_id"],))
    aceite = buscar_um(
        "SELECT versao, aceito_em FROM aceites WHERE usuario_id = %s ORDER BY id DESC LIMIT 1",
        (s["usuario_id"],),
    )
    return jsonify({
        "email": s["email"],
        "nome": s["nome"],
        "foto": (linha or {}).get("foto"),
        "twoFactorEnrolled": bool(s["totp_confirmado"]),
        "aceite": {
            "versao": aceite["versao"],
            "em": aceite["aceito_em"].isoformat(timespec="minutes"),
        } if aceite else None,
        "aceitePendente": s["aceite_versao"] != documentos.VERSAO,
    })


@app.put("/api/perfil")
@exige_sessao()
def salvar_perfil():
    nome = ((request.get_json(silent=True) or {}).get("nome") or "").strip()[:120]
    with cursor(commit=True) as cur:
        cur.execute("UPDATE usuarios SET nome = %s WHERE id = %s", (nome, g.sessao["usuario_id"]))
    return jsonify({"ok": True, "nome": nome})


# Foto de perfil. Chega pronta do navegador: já recortada em quadrado e
# reduzida para 256px, como data URL.
FOTO_MAX_BYTES = 400 * 1024
FOTO_PREFIXOS = ("data:image/jpeg;base64,", "data:image/png;base64,", "data:image/webp;base64,")


@app.put("/api/perfil/foto")
@exige_sessao()
def salvar_foto():
    foto = (request.get_json(silent=True) or {}).get("foto") or ""

    # Validar o prefixo importa: sem isso dá para gravar
    # "data:text/html,<script>" aqui e o <img src> vira vetor de injeção
    # na hora em que a foto voltar para a tela.
    if not foto.startswith(FOTO_PREFIXOS):
        return erro("Envie uma imagem JPEG, PNG ou WebP.")
    if len(foto) > FOTO_MAX_BYTES:
        return erro("Imagem grande demais.")

    with cursor(commit=True) as cur:
        cur.execute("UPDATE usuarios SET foto = %s WHERE id = %s", (foto, g.sessao["usuario_id"]))
    return jsonify({"ok": True})


@app.delete("/api/perfil/foto")
@exige_sessao()
def remover_foto():
    with cursor(commit=True) as cur:
        cur.execute("UPDATE usuarios SET foto = NULL WHERE id = %s", (g.sessao["usuario_id"],))
    return jsonify({"ok": True})


@app.put("/api/perfil/senha")
@exige_sessao()
def trocar_senha():
    dados = request.get_json(silent=True) or {}
    atual = dados.get("senhaAtual") or ""
    nova = dados.get("senhaNova") or ""

    if len(nova) < 8:
        return erro("A senha nova precisa de pelo menos 8 caracteres.")

    usuario = buscar_um(
        "SELECT senha_hash FROM usuarios WHERE id = %s", (g.sessao["usuario_id"],)
    )
    if not seguranca.conferir_senha(atual, usuario["senha_hash"]):
        return erro("Senha atual incorreta.", 401)

    with cursor(commit=True) as cur:
        cur.execute(
            "UPDATE usuarios SET senha_hash = %s WHERE id = %s",
            (seguranca.hash_senha(nova), g.sessao["usuario_id"]),
        )
    # Trocou a senha: as outras sessões caem. Se a troca foi porque a
    # senha vazou, deixar sessão antiga viva anula o efeito.
    seguranca.encerrar_sessoes_do_usuario(g.sessao["usuario_id"], exceto_id=g.sessao["id"])
    return jsonify({"ok": True})


# ── LGPD: termos, aceite, exportar, apagar a conta ───────────
@app.get("/api/documentos")
def ler_documentos():
    """Termos e política, sem sessão: o login também mostra os links."""
    return jsonify(documentos.documentos())


@app.post("/api/aceite")
@exige_sessao(sem_aceite=True)
def aceitar_documentos():
    """Registra o aceite da versão que a pessoa leu. Se a versão mudou
    entre abrir a tela e clicar, recusa: ela aceitaria um texto que não viu."""
    versao = (request.get_json(silent=True) or {}).get("versao")
    if versao != documentos.VERSAO:
        return erro("Os documentos mudaram enquanto você lia. Recarregue a página.", 409)
    with cursor(commit=True) as cur:
        cur.execute(
            "INSERT INTO aceites (usuario_id, versao) VALUES (%s, %s)",
            (g.sessao["usuario_id"], versao),
        )
    return jsonify({"ok": True})


def _exportavel(linha, sem=("usuario_id",)):
    saida = {}
    for chave, v in linha.items():
        if chave in sem:
            continue
        if isinstance(v, (date, datetime)):
            v = v.isoformat()
        elif isinstance(v, Decimal):
            v = float(v)
        saida[chave] = v
    return saida


# Tudo o que tem usuario_id. SELECT * de propósito: coluna nova entra na
# exportação sem ninguém lembrar de vir aqui.
_TABELAS_DO_USUARIO = (
    "transacoes", "orcamentos", "investimentos", "metas", "conexoes_bancarias",
    "regras_categoria", "descartes", "aceites",
)


@app.get("/api/conta/exportar")
@exige_sessao(sem_aceite=True)
def exportar_conta():
    """Tudo o que o app guarda sobre a pessoa, em JSON (LGPD, art. 18).

    Ficam de fora só os segredos de segurança (resumo da senha, segredo do
    TOTP, sessões): não são dado que se leve para outro lugar, e um arquivo
    baixado com eles abriria a conta para quem o achasse.
    """
    uid = g.sessao["usuario_id"]
    conta = buscar_um(
        "SELECT email, nome, foto, totp_confirmado, criado_em, atualizado_em "
        "FROM usuarios WHERE id = %s",
        (uid,),
    )
    dados = {
        "exportadoEm": datetime.now().isoformat(timespec="seconds"),
        "sobre": "Exportação dos seus dados no Lastro (LGPD, art. 18). "
                 "Datas em ISO 8601 e valores em reais.",
        "conta": _exportavel(conta),
    }
    for tabela in _TABELAS_DO_USUARIO:
        dados[tabela] = [
            _exportavel(l) for l in buscar_todos(
                f"SELECT * FROM {tabela} WHERE usuario_id = %s", (uid,)
            )
        ]
    dados["subtarefas"] = [
        _exportavel(l) for l in buscar_todos(
            "SELECT s.* FROM subtarefas s JOIN metas m ON m.id = s.meta_id "
            "WHERE m.usuario_id = %s ORDER BY s.meta_id, s.ordem",
            (uid,),
        )
    ]
    # credenciais_pluggy fica fora da lista de tabelas de propósito: o
    # Client Secret é segredo como a senha. Só o Client ID vai.
    credencial = buscar_um(
        "SELECT client_id, atualizado_em FROM credenciais_pluggy WHERE usuario_id = %s", (uid,)
    )
    dados["credencialPluggy"] = _exportavel(credencial) if credencial else None
    # Passkeys: só apelido e datas. A chave pública não serve para nada fora
    # daqui, e o id da credencial é detalhe técnico.
    dados["passkeys"] = passkeys.listar(uid)
    # Do espaço, só o que é desta pessoa: o papel e quando entrou. Nome e
    # e-mail dos outros membros são dados deles, não vão no arquivo dela.
    meu = buscar_um(
        "SELECT papel, entrou_em FROM espaco_membros WHERE usuario_id = %s", (uid,)
    )
    dados["espaco"] = _exportavel(meu) if meu else None
    return jsonify(dados)


@app.delete("/api/conta")
@exige_sessao(sem_aceite=True)
def apagar_conta():
    """Apaga a conta e tudo dela: as chaves estrangeiras levam o resto em
    cascata, sessões inclusive.

    Pede a senha, e o código quando o 2FA está ativo. Com uma sessão
    esquecida aberta, dois cliques não podem apagar a vida financeira de
    alguém. Erro conta tentativa, como no login.
    """
    d = request.get_json(silent=True) or {}
    uid = g.sessao["usuario_id"]
    usuario = buscar_um(
        "SELECT senha_hash, totp_confirmado, bloqueado_ate FROM usuarios WHERE id = %s", (uid,)
    )
    if seguranca.esta_bloqueado(usuario):
        return erro("Muitas tentativas. Tente de novo em alguns minutos.", 429)
    if not seguranca.conferir_senha(d.get("senha") or "", usuario["senha_hash"]):
        seguranca.registrar_falha(uid)
        return erro("Senha incorreta.", 401)
    if usuario["totp_confirmado"] and not seguranca.conferir_codigo(uid, d.get("codigo") or ""):
        seguranca.registrar_falha(uid)
        return erro("Código incorreto ou expirado.", 401)

    cred, _ = _credencial(uid)
    # Sai do espaço antes: se era quem administrava, outro membro herda; se
    # sobrar uma pessoa só, o espaço acaba. A cascata sozinha deixaria um
    # espaço sem dono.
    espacos.sair(uid)
    with cursor(commit=True) as cur:
        cur.execute("DELETE FROM usuarios WHERE id = %s", (uid,))
    if cred:
        openfinance.esquecer_credencial(cred)
    return jsonify({"ok": True})


# ── Transações ───────────────────────────────────────────────
def _serializar(t):
    return {
        "id": t["id"],
        "data": t["data"].isoformat() if isinstance(t["data"], date) else str(t["data"]),
        "nome": t["nome"],
        # float só na borda de saída: o cálculo com dinheiro acontece
        # em DECIMAL no MySQL, nunca em ponto flutuante.
        "valor": float(t["valor"]),
        "natureza": t["natureza"],
        "categoria": t["categoria"],
        "recorrencia": t["recorrencia"],
        "importada": t.get("origem_id") is not None,
        "ignorada": bool(t.get("ignorada")),
        "meio": t.get("meio"),
    }


def _serializar_visao(t, eu):
    """Linha vista por `eu`: diz de quem é e, se for dele, o cadeado.
    Do outro só chega o que já é compartilhado, então o cadeado dele nem
    viaja (seria sempre falso)."""
    s = _serializar(t)
    minha = t["usuario_id"] == eu
    s["dono"] = t["usuario_id"]
    s["minha"] = minha
    if minha:
        s["privada"] = bool(t.get("privada"))
        s["privadaPelaConta"] = bool(t.get("conexao_privada"))
    if t.get("entre_membros"):
        s["entreMembros"] = True
    return s


@app.get("/api/transacoes")
@exige_sessao()
def listar_transacoes():
    """Devolve o histórico do usuário, mais antigo primeiro.

    O recorte de período fica no cliente: são poucos milhares de linhas
    num app pessoal, e o dashboard precisa do histórico inteiro para o
    saldo acumulado bater.
    """
    eu = g.sessao["usuario_id"]
    try:
        linhas = visao.transacoes(eu, request.args.get("visao"))
    except visao.VisaoInvalida as e:
        return erro(str(e), 404)
    return jsonify([_serializar_visao(t, eu) for t in linhas])


@app.get("/api/visao")
@exige_sessao()
def visao_membros():
    """Quem aparece no seletor de visão: a pessoa e os membros do espaço."""
    eu = g.sessao["usuario_id"]
    return jsonify({
        "membros": [{**m, "eu": m["id"] == eu} for m in visao.membros(eu)],
    })


@app.post("/api/transacoes")
@exige_sessao()
def criar_transacao():
    d = request.get_json(silent=True) or {}
    try:
        valor = Decimal(str(d.get("valor", "0")))
    except Exception:
        return erro("Valor inválido.")
    if valor <= 0:
        return erro("O valor precisa ser maior que zero.")

    natureza = str(d.get("natureza", "")).lower()
    if natureza not in ("receita", "despesa"):
        return erro("Natureza deve ser 'receita' ou 'despesa'.")

    recorrencia = "mensal" if str(d.get("recorrencia", "")).lower() == "mensal" else "unica"
    nome = (d.get("nome") or "").strip()[:160] or "Sem descrição"
    categoria = (d.get("categoria") or "").strip()[:80] or "Sem categoria"

    with cursor(commit=True) as cur:
        cur.execute(
            "INSERT INTO transacoes (usuario_id, data, nome, valor, natureza, "
            "categoria, recorrencia) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (g.sessao["usuario_id"], d.get("data"), nome, valor, natureza,
             categoria, recorrencia),
        )
        novo_id = cur.lastrowid
    return jsonify({"ok": True, "id": novo_id}), 201


@app.patch("/api/transacoes/<int:transacao_id>")
@exige_sessao()
def editar_transacao(transacao_id):
    """Troca a categoria e/ou marca o lançamento como "não conta".

    Categoria escolhida aqui vira categoria_manual: regra de categoria
    criada depois não passa por cima da escolha do usuário.
    """
    d = request.get_json(silent=True) or {}
    campos, valores = [], []
    if "categoria" in d:
        categoria = str(d.get("categoria") or "").strip()[:80]
        if not categoria:
            return erro("Informe a categoria.")
        campos += ["categoria = %s", "categoria_manual = 1"]
        valores.append(categoria)
    if "privada" in d:
        campos.append("privada = %s")
        valores.append(1 if d.get("privada") else 0)
    if "ignorada" in d:
        campos.append("ignorada = %s")
        valores.append(1 if d.get("ignorada") else 0)
        # Voltar a contar desfaz o "era o mesmo dinheiro" da conferência.
        if not d.get("ignorada"):
            campos.append("conferencia = IF(conferencia = 'errado', NULL, conferencia)")
    if not campos:
        return erro("Nada para alterar.")

    with cursor(commit=True) as cur:
        cur.execute(
            f"UPDATE transacoes SET {', '.join(campos)} WHERE id = %s AND usuario_id = %s",
            (*valores, transacao_id, g.sessao["usuario_id"]),
        )
        # rowcount 0 também quando nada mudou; confere a existência à parte.
        if cur.rowcount == 0 and not buscar_um(
            "SELECT id FROM transacoes WHERE id = %s AND usuario_id = %s",
            (transacao_id, g.sessao["usuario_id"]),
        ):
            return erro("Lançamento não encontrado.", 404)
    return jsonify({"ok": True})


@app.delete("/api/transacoes/<int:transacao_id>")
@exige_sessao()
def apagar_transacao(transacao_id):
    # O usuario_id no WHERE não é redundante: sem ele, um id chutado
    # apagaria lançamento de outra conta.
    with cursor(commit=True) as cur:
        cur.execute(
            "DELETE FROM transacoes WHERE id = %s AND usuario_id = %s",
            (transacao_id, g.sessao["usuario_id"]),
        )
        if cur.rowcount == 0:
            return erro("Lançamento não encontrado.", 404)
    return jsonify({"ok": True})


# ── Orçamentos ───────────────────────────────────────────────
@app.get("/api/orcamentos")
@exige_sessao()
def listar_orcamentos():
    linhas = buscar_todos(
        "SELECT categoria, teto FROM orcamentos WHERE usuario_id = %s",
        (g.sessao["usuario_id"],),
    )
    return jsonify({l["categoria"]: float(l["teto"]) for l in linhas})


@app.put("/api/orcamentos")
@exige_sessao()
def salvar_orcamentos():
    """Substitui o conjunto inteiro: o que não vier no corpo é apagado.

    A tela manda todas as categorias de uma vez, então tratar como
    substituição evita teto órfão de categoria que deixou de existir.
    """
    enviados = request.get_json(silent=True) or {}
    if not isinstance(enviados, dict):
        return erro("Envie um objeto categoria → teto.")

    validos = {}
    for categoria, teto in enviados.items():
        try:
            v = Decimal(str(teto))
        except Exception:
            continue
        if v > 0:
            validos[str(categoria)[:80]] = v

    uid = g.sessao["usuario_id"]
    with cursor(commit=True) as cur:
        cur.execute("DELETE FROM orcamentos WHERE usuario_id = %s", (uid,))
        if validos:
            cur.executemany(
                "INSERT INTO orcamentos (usuario_id, categoria, teto) VALUES (%s, %s, %s)",
                [(uid, c, t) for c, t in validos.items()],
            )
    return jsonify({c: float(t) for c, t in validos.items()})


# ── Investimentos ────────────────────────────────────────────
@app.get("/api/cotacoes/<ticker>")
@exige_sessao()
def obter_cotacao(ticker):
    """Cotação de um único ticker, usada pelo formulário para sugerir o
    preço atual enquanto o usuário digita. Segue a mesma regra de
    cotacoes.buscar: nunca vira 500, só volta cotação nula com aviso.
    """
    ticker = re.sub(r"[^A-Za-z0-9]", "", ticker).upper()[:16]
    if not ticker:
        return erro("Informe o ticker.")

    precos, aviso = cotacoes.buscar([ticker])
    return jsonify({"cotacao": precos.get(ticker), "aviso": aviso})


@app.get("/api/investimentos")
@exige_sessao()
def listar_investimentos():
    """Posições do usuário, com a cotação de mercado anexada quando dá.

    A cotação é acessório: se a brapi falhar, `cotacao` vem nula em cada
    item e `aviso` explica o motivo, mas a lista sai completa do mesmo
    jeito. A tela nunca fica sem os dados que estão no banco.
    """
    linhas = buscar_todos(
        "SELECT id, ticker, quantidade, preco_medio, data FROM investimentos "
        "WHERE usuario_id = %s ORDER BY ticker, data",
        (g.sessao["usuario_id"],),
    )

    precos, aviso = cotacoes.buscar(l["ticker"] for l in linhas)

    itens = []
    for l in linhas:
        quantidade = float(l["quantidade"])
        preco_medio = float(l["preco_medio"])
        itens.append({
            "id": l["id"],
            "ticker": l["ticker"],
            "quantidade": quantidade,
            "precoMedio": preco_medio,
            "investido": round(quantidade * preco_medio, 2),
            "data": l["data"].isoformat() if isinstance(l["data"], date) else str(l["data"]),
            "cotacao": precos.get(l["ticker"]),
        })

    return jsonify({"itens": itens, "aviso": aviso, "temToken": bool(config.BRAPI_TOKEN)})


@app.post("/api/investimentos")
@exige_sessao()
def criar_investimento():
    d = request.get_json(silent=True) or {}

    # Só letras e números: o ticker entra numa URL da brapi, e deixar
    # passar barra ou interrogação aqui viraria injeção de caminho.
    ticker = re.sub(r"[^A-Za-z0-9]", "", str(d.get("ticker", ""))).upper()[:16]
    if not ticker:
        return erro("Informe o ticker (ex: PETR4).")

    try:
        quantidade = Decimal(str(d.get("quantidade", "0")))
        preco_medio = Decimal(str(d.get("precoMedio", "0")))
    except Exception:
        return erro("Quantidade e preço médio precisam ser números.")

    if quantidade <= 0:
        return erro("A quantidade precisa ser maior que zero.")
    if preco_medio <= 0:
        return erro("O preço médio precisa ser maior que zero.")

    with cursor(commit=True) as cur:
        cur.execute(
            "INSERT INTO investimentos (usuario_id, ticker, quantidade, preco_medio, data) "
            "VALUES (%s, %s, %s, %s, %s)",
            (g.sessao["usuario_id"], ticker, quantidade, preco_medio, d.get("data")),
        )
        novo_id = cur.lastrowid
    return jsonify({"ok": True, "id": novo_id}), 201


@app.delete("/api/investimentos/<int:investimento_id>")
@exige_sessao()
def apagar_investimento(investimento_id):
    with cursor(commit=True) as cur:
        cur.execute(
            "DELETE FROM investimentos WHERE id = %s AND usuario_id = %s",
            (investimento_id, g.sessao["usuario_id"]),
        )
        if cur.rowcount == 0:
            return erro("Investimento não encontrado.", 404)
    return jsonify({"ok": True})


# ── Metas e subtarefas ───────────────────────────────────────
def _carregar_metas(usuario_id):
    """Metas do usuário com as subtarefas embutidas.

    Duas consultas em vez de um JOIN: o JOIN devolveria a meta repetida uma
    vez por subtarefa e a montagem em Python daria no mesmo trabalho.
    """
    metas = buscar_todos(
        "SELECT id, titulo, descricao, alvo, guardado, prazo, concluida, "
        "       concluida_em, multiplicador, criado_em "
        "  FROM metas WHERE usuario_id = %s "
        " ORDER BY concluida, COALESCE(prazo, '9999-12-31'), id",
        (usuario_id,),
    )
    if not metas:
        return []
    renda = _renda_mensal(usuario_id)

    ids = [m["id"] for m in metas]
    marcadores = ",".join(["%s"] * len(ids))
    subs = buscar_todos(
        "SELECT id, meta_id, titulo, concluida, xp, ordem, gerada_por_ia "
        f"  FROM subtarefas WHERE meta_id IN ({marcadores}) "
        " ORDER BY meta_id, ordem, id",
        tuple(ids),
    )

    por_meta = {i: [] for i in ids}
    for s in subs:
        por_meta[s["meta_id"]].append(s)

    hoje = date.today()
    saida = []
    for m in metas:
        dif = _dificuldade_da_meta(m, renda)
        mult = dif["multiplicador"]
        prazo = m["prazo"]
        # Concluída: pontual se fechou até o prazo. Aberta: o bônus mostrado
        # já conta a pontualidade enquanto o prazo ainda não passou, porque
        # é o que ela vai render se for concluída agora.
        if m["concluida"]:
            pontual = bool(prazo and m["concluida_em"] and m["concluida_em"].date() <= prazo)
        else:
            pontual = bool(prazo and hoje <= prazo)
        base = [int(s["xp"]) for s in por_meta[m["id"]]]

        saida.append({
            "id": m["id"],
            "titulo": m["titulo"],
            "descricao": m["descricao"],
            "alvo": float(m["alvo"]) if m["alvo"] is not None else None,
            "guardado": float(m["guardado"]),
            "prazo": prazo.isoformat() if isinstance(prazo, date) else prazo,
            "concluida": bool(m["concluida"]),
            "dificuldade": dif,
            "pontual": pontual,
            # `xp` já vem com a dificuldade: a tela soma direto. `xpBase` é
            # o que a IA (ou a pessoa) deu, antes do multiplicador.
            "subtarefas": [{
                "id": s["id"],
                "titulo": s["titulo"],
                "concluida": bool(s["concluida"]),
                "xp": gamificacao.xp_com_dificuldade(int(s["xp"]), mult),
                "xpBase": int(s["xp"]),
                "ordem": int(s["ordem"]),
                "geradaPorIa": bool(s["gerada_por_ia"]),
            } for s in por_meta[m["id"]]],
            "bonusXp": gamificacao.bonus_da_meta(sum(base), mult, pontual),
        })
    return saida


def _renda_mensal(usuario_id):
    """Média das entradas nos últimos 3 meses fechados, só dos meses em que
    o app foi usado (com algum lançamento). Dividir por 3 sempre puniria
    quem começou a usar há um mês. Sem nada registrado, devolve None e a
    dificuldade cai na escala em reais."""
    hoje = date.today()
    fim = hoje.replace(day=1)
    inicio = fim
    for _ in range(3):
        inicio = (inicio - timedelta(days=1)).replace(day=1)

    linhas = buscar_todos(
        "SELECT data, natureza, valor FROM transacoes "
        "WHERE usuario_id = %s AND ignorada = 0 AND data >= %s AND data < %s",
        (usuario_id, inicio, fim),
    )
    meses = {(l["data"].year, l["data"].month) for l in linhas}
    entradas = sum(float(l["valor"]) for l in linhas if l["natureza"] == "receita")
    return entradas / len(meses) if meses and entradas > 0 else None


def _dificuldade_da_meta(m, renda):
    """Congelada na conclusão; calculada na hora enquanto a meta está aberta.
    Concluída antes de existir o multiplicador (NULL) vale x1."""
    if m["concluida"]:
        congelado = float(m["multiplicador"]) if m["multiplicador"] is not None else 1.0
        nome = next((f[3] for f in gamificacao.FAIXAS if f[2] == congelado), "simples")
        return {"nome": nome, "multiplicador": congelado, "parcelaMensal": None, "peso": None, "base": None}
    return gamificacao.dificuldade(m["alvo"], m["prazo"], m["criado_em"], renda)


def _meta_do_usuario(meta_id, usuario_id):
    """Confere posse. O usuario_id no WHERE é o que impede um id chutado
    de alcançar meta de outra conta."""
    return buscar_um(
        "SELECT id FROM metas WHERE id = %s AND usuario_id = %s",
        (meta_id, usuario_id),
    )


@app.get("/api/metas")
@exige_sessao()
def listar_metas():
    metas = _carregar_metas(g.sessao["usuario_id"])
    return jsonify({
        "metas": metas,
        # O personagem é derivado das metas, não guardado. Ver gamificacao.py.
        "personagem": gamificacao.progresso(gamificacao.calcular_xp(metas)),
        "iaDisponivel": ia.disponivel(),
    })


@app.post("/api/metas")
@exige_sessao()
def criar_meta():
    """Cria a meta e, se pedido, já sugere os passos via IA.

    A geração NUNCA impede a criação: se a IA falhar, a meta é gravada do
    mesmo jeito e o `aviso` explica por que veio sem subtarefas.
    """
    d = request.get_json(silent=True) or {}
    titulo = (d.get("titulo") or "").strip()[:160]
    if not titulo:
        return erro("Informe o título da meta.")

    descricao = (d.get("descricao") or "").strip() or None

    alvo = None
    if d.get("alvo") not in (None, ""):
        try:
            alvo = Decimal(str(d["alvo"]))
        except Exception:
            return erro("Valor alvo inválido.")
        if alvo <= 0:
            return erro("O valor alvo precisa ser maior que zero.")

    with cursor(commit=True) as cur:
        cur.execute(
            "INSERT INTO metas (usuario_id, titulo, descricao, alvo, prazo) "
            "VALUES (%s, %s, %s, %s, %s)",
            (g.sessao["usuario_id"], titulo, descricao, alvo, d.get("prazo") or None),
        )
        meta_id = cur.lastrowid

    aviso = None
    if d.get("gerarSubtarefas"):
        subtarefas, aviso = ia.gerar_subtarefas(titulo, descricao, alvo, d.get("prazo"))
        if subtarefas:
            _inserir_subtarefas(meta_id, subtarefas, por_ia=True)

    return jsonify({"ok": True, "id": meta_id, "aviso": aviso}), 201


def _inserir_subtarefas(meta_id, subtarefas, por_ia):
    with cursor(commit=True) as cur:
        cur.executemany(
            "INSERT INTO subtarefas (meta_id, titulo, xp, ordem, gerada_por_ia) "
            "VALUES (%s, %s, %s, %s, %s)",
            [(meta_id, s["titulo"], s["xp"], s.get("ordem", i), int(por_ia))
             for i, s in enumerate(subtarefas)],
        )


@app.post("/api/metas/<int:meta_id>/subtarefas/gerar")
@exige_sessao()
def gerar_subtarefas_da_meta(meta_id):
    """Gera passos para uma meta que já existe (ou gera de novo)."""
    if not _meta_do_usuario(meta_id, g.sessao["usuario_id"]):
        return erro("Meta não encontrada.", 404)

    meta = buscar_um(
        "SELECT titulo, descricao, alvo, prazo FROM metas WHERE id = %s", (meta_id,)
    )
    # Os títulos existentes vão junto: o modelo complementa o caminho em vez
    # de recomeçar do zero, e o filtro em ia.py barra repetição literal.
    existentes = [
        s["titulo"] for s in buscar_todos(
            "SELECT titulo FROM subtarefas WHERE meta_id = %s ORDER BY ordem", (meta_id,)
        )
    ]
    subtarefas, aviso = ia.gerar_subtarefas(
        meta["titulo"], meta["descricao"], meta["alvo"], meta["prazo"],
        existentes=existentes,
    )
    if subtarefas:
        _inserir_subtarefas(meta_id, subtarefas, por_ia=True)

    return jsonify({"ok": bool(subtarefas), "criadas": len(subtarefas), "aviso": aviso})


@app.post("/api/metas/<int:meta_id>/subtarefas")
@exige_sessao()
def criar_subtarefa(meta_id):
    """Passo escrito à mão."""
    if not _meta_do_usuario(meta_id, g.sessao["usuario_id"]):
        return erro("Meta não encontrada.", 404)

    d = request.get_json(silent=True) or {}
    titulo = (d.get("titulo") or "").strip()[:200]
    if not titulo:
        return erro("Informe o título da subtarefa.")

    ultima = buscar_um(
        "SELECT COALESCE(MAX(ordem), -1) AS u FROM subtarefas WHERE meta_id = %s",
        (meta_id,),
    )
    with cursor(commit=True) as cur:
        cur.execute(
            "INSERT INTO subtarefas (meta_id, titulo, xp, ordem) VALUES (%s, %s, %s, %s)",
            (meta_id, titulo, max(1, min(int(d.get("xp", 10) or 10), 100)), ultima["u"] + 1),
        )
        return jsonify({"ok": True, "id": cur.lastrowid}), 201


@app.patch("/api/subtarefas/<int:subtarefa_id>")
@exige_sessao()
def alternar_subtarefa(subtarefa_id):
    """Marca ou desmarca. É daqui que sai o XP."""
    concluida = bool((request.get_json(silent=True) or {}).get("concluida"))

    # O JOIN em metas é a checagem de posse: subtarefas não guardam
    # usuario_id, a dona é a meta.
    with cursor(commit=True) as cur:
        cur.execute(
            "UPDATE subtarefas s JOIN metas m ON m.id = s.meta_id "
            "   SET s.concluida = %s, s.concluida_em = %s "
            " WHERE s.id = %s AND m.usuario_id = %s",
            (int(concluida), datetime.now() if concluida else None,
             subtarefa_id, g.sessao["usuario_id"]),
        )
        if cur.rowcount == 0:
            # rowcount 0 também acontece quando o valor já era esse; conferir
            # a existência separa "não é sua" de "não mudou nada".
            existe = buscar_um(
                "SELECT s.id FROM subtarefas s JOIN metas m ON m.id = s.meta_id "
                " WHERE s.id = %s AND m.usuario_id = %s",
                (subtarefa_id, g.sessao["usuario_id"]),
            )
            if not existe:
                return erro("Subtarefa não encontrada.", 404)

    metas = _carregar_metas(g.sessao["usuario_id"])
    # Devolve o personagem recalculado para a tela animar o ganho de XP sem
    # precisar de uma segunda chamada.
    return jsonify({
        "ok": True,
        "personagem": gamificacao.progresso(gamificacao.calcular_xp(metas)),
    })


@app.delete("/api/subtarefas/<int:subtarefa_id>")
@exige_sessao()
def apagar_subtarefa(subtarefa_id):
    with cursor(commit=True) as cur:
        cur.execute(
            "DELETE s FROM subtarefas s JOIN metas m ON m.id = s.meta_id "
            " WHERE s.id = %s AND m.usuario_id = %s",
            (subtarefa_id, g.sessao["usuario_id"]),
        )
        if cur.rowcount == 0:
            return erro("Subtarefa não encontrada.", 404)
    return jsonify({"ok": True})


@app.patch("/api/metas/<int:meta_id>")
@exige_sessao()
def atualizar_meta(meta_id):
    """Conclui/reabre a meta ou atualiza quanto já foi guardado."""
    if not _meta_do_usuario(meta_id, g.sessao["usuario_id"]):
        return erro("Meta não encontrada.", 404)

    d = request.get_json(silent=True) or {}
    campos, valores = [], []

    if "concluida" in d:
        concluida = bool(d["concluida"])
        # Congela o multiplicador de agora; reabrir solta, e ele volta a
        # ser calculado pela renda do momento.
        multiplicador = None
        if concluida:
            m = buscar_um(
                "SELECT alvo, prazo, criado_em FROM metas WHERE id = %s", (meta_id,)
            )
            multiplicador = gamificacao.dificuldade(
                m["alvo"], m["prazo"], m["criado_em"], _renda_mensal(g.sessao["usuario_id"])
            )["multiplicador"]
        campos += ["concluida = %s", "concluida_em = %s", "multiplicador = %s"]
        valores += [int(concluida), datetime.now() if concluida else None, multiplicador]

    if "guardado" in d:
        try:
            guardado = Decimal(str(d["guardado"]))
        except Exception:
            return erro("Valor guardado inválido.")
        if guardado < 0:
            return erro("O valor guardado não pode ser negativo.")
        campos.append("guardado = %s")
        valores.append(guardado)

    if not campos:
        return erro("Nada para atualizar.")

    with cursor(commit=True) as cur:
        cur.execute(
            f"UPDATE metas SET {', '.join(campos)} WHERE id = %s AND usuario_id = %s",
            (*valores, meta_id, g.sessao["usuario_id"]),
        )

    metas = _carregar_metas(g.sessao["usuario_id"])
    return jsonify({
        "ok": True,
        "personagem": gamificacao.progresso(gamificacao.calcular_xp(metas)),
    })


@app.delete("/api/metas/<int:meta_id>")
@exige_sessao()
def apagar_meta(meta_id):
    # As subtarefas somem junto pelo ON DELETE CASCADE da chave estrangeira.
    with cursor(commit=True) as cur:
        cur.execute(
            "DELETE FROM metas WHERE id = %s AND usuario_id = %s",
            (meta_id, g.sessao["usuario_id"]),
        )
        if cur.rowcount == 0:
            return erro("Meta não encontrada.", 404)
    return jsonify({"ok": True})


# ── Open Finance (Pluggy) ────────────────────────────────────
def _conexoes(usuario_id):
    return buscar_todos(
        "SELECT id, item_id, instituicao, importado_ate FROM conexoes_bancarias "
        "WHERE usuario_id = %s ORDER BY id",
        (usuario_id,),
    )


def _conexao_do_usuario(conexao_id, usuario_id):
    return buscar_um(
        "SELECT id, item_id, privada FROM conexoes_bancarias WHERE id = %s AND usuario_id = %s",
        (conexao_id, usuario_id),
    )


_SEM_CHAVE = (
    "O servidor está sem a chave que cifra as credenciais da Pluggy (FIN_CHAVE_CREDENCIAIS). "
    "Fale com quem mantém o app."
)


def _credencial(usuario_id):
    """A credencial da Pluggy DESTA pessoa, decifrada, e a situação dela.

    @return (Credencial ou None, {"clientId", "situacao"}). situacao é "ok",
            "ausente", "semChave" (o servidor não tem a chave) ou "ilegivel"
            (a chave do servidor mudou e o segredo não abre mais).
    """
    linha = buscar_um(
        "SELECT client_id, client_secret FROM credenciais_pluggy WHERE usuario_id = %s",
        (usuario_id,),
    )
    if not cofre.disponivel():
        return None, {"clientId": linha and linha["client_id"], "situacao": "semChave"}
    if not linha:
        return None, {"clientId": None, "situacao": "ausente"}
    segredo = cofre.decifrar(linha["client_secret"])
    if not segredo:
        return None, {"clientId": linha["client_id"], "situacao": "ilegivel"}
    return (
        openfinance.Credencial(linha["client_id"], segredo),
        {"clientId": linha["client_id"], "situacao": "ok"},
    )


def _aviso_credencial(info):
    return {
        "ok": None,
        "semChave": _SEM_CHAVE,
        "ilegivel": "Não consegui abrir a sua credencial da Pluggy: a chave do servidor mudou. "
                    "Cadastre de novo.",
    }.get(info["situacao"], openfinance.sem_credencial())


@app.get("/api/openfinance/situacao")
@exige_sessao()
def situacao_openfinance():
    """Rápida, só banco local: quantas conexões a pessoa tem. A tela inicial
    usa para saber, antes de a Pluggy responder, que o saldo virá dos bancos
    e não deve ser calculado pelos lançamentos enquanto isso."""
    eu = g.sessao["usuario_id"]
    try:
        ids = visao.ids_da_visao(eu, request.args.get("visao"))
    except visao.VisaoInvalida as e:
        return erro(str(e), 404)
    marcadores = ", ".join(["%s"] * len(ids))
    n = buscar_um(
        f"SELECT COUNT(*) AS n FROM conexoes_bancarias WHERE usuario_id IN ({marcadores}) "
        "AND (usuario_id = %s OR privada = 0)",
        (*ids, eu),
    )["n"]
    return jsonify({"conexoes": int(n)})


@app.get("/api/openfinance")
@exige_sessao()
def ler_openfinance():
    """Saldos, cartões e faturas de cada conexão, lidos da Pluggy agora.

    Uma conexão que falha não derruba as outras: ela volta com `dados` nulo
    e o próprio `aviso`, e a tela mostra o resto.
    """
    eu = g.sessao["usuario_id"]
    try:
        ids = visao.ids_da_visao(eu, request.args.get("visao"))
    except visao.VisaoInvalida as e:
        return erro(str(e), 404)
    cred, info = _credencial(eu)
    nomes = {m["id"]: m["nome"] for m in visao.membros(eu)}

    # As suas, todas; as dos outros membros, só as sem cadeado. Cada uma é
    # lida com a credencial Pluggy DO DONO dela: ninguém usa a de outro.
    marcadores = ", ".join(["%s"] * len(ids))
    conexoes = buscar_todos(
        "SELECT id, usuario_id, item_id, instituicao, importado_ate, privada "
        f"  FROM conexoes_bancarias WHERE usuario_id IN ({marcadores}) "
        "   AND (usuario_id = %s OR privada = 0) ORDER BY usuario_id <> %s, id",
        (*ids, eu, eu),
    )
    credenciais = {eu: cred}
    for dono in {c["usuario_id"] for c in conexoes} - {eu}:
        credenciais[dono] = _credencial(dono)[0]

    # Conexões lidas em paralelo (cada uma também paraleliza por dentro).
    # A ordem da resposta segue a da lista.
    with ThreadPoolExecutor(max_workers=max(1, min(6, len(conexoes)))) as ex:
        lidas = list(ex.map(
            lambda c: openfinance.panorama(credenciais.get(c["usuario_id"]), c["item_id"]),
            conexoes,
        ))

    saida = []
    for c, (dados, aviso) in zip(conexoes, lidas):
        minha = c["usuario_id"] == eu
        saida.append({
            "dono": c["usuario_id"],
            "donoNome": nomes.get(c["usuario_id"], ""),
            "minha": minha,
            "privada": bool(c["privada"]) if minha else False,
            "id": c["id"],
            "itemId": c["item_id"],
            "instituicao": (dados or {}).get("instituicao") or c["instituicao"] or "Conexão",
            "importadoAte": c["importado_ate"].isoformat() if c["importado_ate"] else None,
            "dados": dados,
            "aviso": aviso,
        })

    # A primeira importação pega os 12 meses que o Open Finance costuma
    # guardar. As seguintes recomeçam 35 dias antes da última: compra no
    # cartão fica pendente até a fatura fechar e, quando compensa, mantém a
    # data da compra. Com uma semana só, ela caía fora da janela para
    # sempre. A chave única barra o repetido.
    hoje = date.today()
    minhas = [c for c in conexoes if c["usuario_id"] == eu]
    ultimas = [c["importado_ate"] for c in minhas if c["importado_ate"]]
    if minhas and len(ultimas) == len(minhas):
        desde = min(ultimas) - timedelta(days=35)
    else:
        desde = hoje - timedelta(days=365)

    return jsonify({
        "disponivel": cred is not None,
        "aviso": _aviso_credencial(info),
        # Só o Client ID: o segredo nunca volta numa resposta.
        "credencial": info,
        "conexoes": saida,
        "importarDesde": desde.isoformat(),
    })


@app.put("/api/openfinance/credencial")
@exige_sessao()
def salvar_credencial():
    """Grava o Client ID e o Client Secret da aplicação da pessoa na Pluggy,
    depois de testar o par lá. O segredo vai cifrado e não volta mais."""
    if not cofre.disponivel():
        return erro(_SEM_CHAVE, 503)
    d = request.get_json(silent=True) or {}
    client_id = str(d.get("clientId") or "").strip().lower()
    segredo = str(d.get("clientSecret") or "").strip()
    if not openfinance.ID_VALIDO.match(client_id):
        return erro("O Client ID tem o formato 8-4-4-4-12, como aparece no painel da Pluggy.")
    if not 8 <= len(segredo) <= 200:
        return erro("Cole o Client Secret inteiro, como aparece no painel da Pluggy.")

    nova = openfinance.Credencial(client_id, segredo)
    # 422, e não 401: 401 é "sua sessão caiu" para o front.
    aviso = openfinance.validar(nova)
    if aviso:
        return erro(aviso, 422)

    uid = g.sessao["usuario_id"]
    anterior, _ = _credencial(uid)
    with cursor(commit=True) as cur:
        cur.execute(
            "INSERT INTO credenciais_pluggy (usuario_id, client_id, client_secret) "
            "VALUES (%s, %s, %s) "
            "ON DUPLICATE KEY UPDATE client_id = VALUES(client_id), client_secret = VALUES(client_secret)",
            (uid, client_id, cofre.cifrar(segredo)),
        )
    if anterior and anterior != nova:
        _desligar_webhook(uid, anterior)
        openfinance.esquecer_credencial(anterior)
    if notificacoes.aparelhos(uid):
        _garantir_webhook(uid)
    return jsonify({"ok": True, "clientId": client_id})


@app.delete("/api/openfinance/credencial")
@exige_sessao()
def apagar_credencial():
    """Tira a credencial do app. As conexões continuam gravadas, mas param de
    ser lidas até entrar outra credencial; o consentimento segue no Meu Pluggy."""
    uid = g.sessao["usuario_id"]
    anterior, _ = _credencial(uid)
    _desligar_webhook(uid, anterior)
    with cursor(commit=True) as cur:
        cur.execute("DELETE FROM credenciais_pluggy WHERE usuario_id = %s", (uid,))
    if anterior:
        openfinance.esquecer_credencial(anterior)
    return jsonify({"ok": True})


@app.post("/api/openfinance/connect-token")
@exige_sessao()
def token_do_widget():
    """Token para o widget Pluggy Connect. Com `conexaoId`, o widget abre
    para reconectar aquela conexão (consentimento expirado, por exemplo)."""
    conexao_id = (request.get_json(silent=True) or {}).get("conexaoId")
    item_id = None
    if conexao_id:
        conexao = _conexao_do_usuario(conexao_id, g.sessao["usuario_id"])
        if not conexao:
            return erro("Conexão não encontrada.", 404)
        item_id = conexao["item_id"]

    cred, _ = _credencial(g.sessao["usuario_id"])
    token, aviso = openfinance.token_do_widget(cred, g.sessao["usuario_id"], item_id)
    if not token:
        return erro(aviso, 502)
    return jsonify({"accessToken": token})


@app.post("/api/openfinance/conexoes")
@exige_sessao()
def criar_conexao():
    item_id = str((request.get_json(silent=True) or {}).get("itemId") or "").strip().lower()

    # Confere na Pluggy antes de gravar: id digitado errado vira erro aqui,
    # e não uma conexão quebrada para sempre na tela. Com a credencial da
    # própria pessoa, um item de outra aplicação nem chega a ser achado.
    cred, _ = _credencial(g.sessao["usuario_id"])
    item, aviso = openfinance.conferir(cred, item_id)
    if not item:
        return erro(aviso or "Conexão não encontrada.")

    with cursor(commit=True) as cur:
        cur.execute(
            "INSERT INTO conexoes_bancarias (usuario_id, item_id, instituicao) "
            "VALUES (%s, %s, %s) "
            "ON DUPLICATE KEY UPDATE instituicao = VALUES(instituicao)",
            (g.sessao["usuario_id"], item_id, item["instituicao"][:120]),
        )
    return jsonify({"ok": True, "instituicao": item["instituicao"]}), 201


@app.delete("/api/openfinance/conexoes/<int:conexao_id>")
@exige_sessao()
def apagar_conexao(conexao_id):
    """Tira a conexão do app. As transações já importadas ficam: são
    histórico, e apagar lançamento junto seria surpresa ruim."""
    conexao = _conexao_do_usuario(conexao_id, g.sessao["usuario_id"])
    if not conexao:
        return erro("Conexão não encontrada.", 404)

    with cursor(commit=True) as cur:
        # Conta com cadeado: sem a conexão, o cadeado dela deixaria de valer
        # para os lançamentos que vieram de lá. Cada um ganha o próprio.
        if conexao.get("privada"):
            cur.execute(
                "UPDATE transacoes SET privada = 1 WHERE conexao_id = %s AND usuario_id = %s",
                (conexao_id, g.sessao["usuario_id"]),
            )
        cur.execute(
            "DELETE FROM conexoes_bancarias WHERE id = %s AND usuario_id = %s",
            (conexao_id, g.sessao["usuario_id"]),
        )
    cred, _ = _credencial(g.sessao["usuario_id"])
    if cred:
        openfinance.esquecer(cred, conexao["item_id"])
    return jsonify({"ok": True})


@app.patch("/api/openfinance/conexoes/<int:conexao_id>")
@exige_sessao()
def editar_conexao(conexao_id):
    """Cadeado da conta inteira: privada some da visão do espaço, com tudo
    o que foi importado dela."""
    d = request.get_json(silent=True) or {}
    if "privada" not in d:
        return erro("Nada para alterar.")
    if not _conexao_do_usuario(conexao_id, g.sessao["usuario_id"]):
        return erro("Conexão não encontrada.", 404)
    with cursor(commit=True) as cur:
        cur.execute(
            "UPDATE conexoes_bancarias SET privada = %s WHERE id = %s AND usuario_id = %s",
            (1 if d.get("privada") else 0, conexao_id, g.sessao["usuario_id"]),
        )
    return jsonify({"ok": True, "privada": bool(d.get("privada"))})


@app.post("/api/openfinance/conexoes/<int:conexao_id>/atualizar")
@exige_sessao()
def atualizar_conexao(conexao_id):
    """Pede à Pluggy para buscar os dados no banco agora. A resposta volta
    na hora; a sincronização em si roda do lado de lá e a tela acompanha
    pelo status da conexão."""
    conexao = _conexao_do_usuario(conexao_id, g.sessao["usuario_id"])
    if not conexao:
        return erro("Conexão não encontrada.", 404)

    cred, _ = _credencial(g.sessao["usuario_id"])
    aviso = openfinance.atualizar(cred, conexao["item_id"])
    if aviso:
        return erro(aviso, 502)
    return jsonify({"ok": True})


@app.post("/api/openfinance/importar")
@exige_sessao()
def importar_openfinance():
    """Traz as transações das conexões para Entradas e Saídas.

    Pode rodar quantas vezes quiser sobre o mesmo período: cada transação
    leva o id de origem da Pluggy, e a chave única uq_transacoes_origem faz
    o repetido ser ignorado em vez de duplicado.
    """
    uid = g.sessao["usuario_id"]
    try:
        desde = date.fromisoformat(str((request.get_json(silent=True) or {}).get("desde")))
    except ValueError:
        return erro("Data inicial inválida.")
    if desde > date.today():
        return erro("A data inicial não pode ser no futuro.")
    if not _conexoes(uid):
        return erro("Nenhuma conexão cadastrada.")

    resultado, aviso = importar_para(uid, desde)
    if aviso:
        return erro(aviso, 502)
    resultado.pop("_novas", None)
    return jsonify(resultado)


def importar_para(uid, desde):
    """A importação em si, fora da rota: a tela chama pela rota acima, e o
    webhook da Pluggy (notificações) chama direto, sem sessão.

    @return (resultado, aviso). `resultado["_novas"]` são as linhas que
            entraram agora (para notificar), e não vai para a resposta.
    """
    hoje = date.today()
    conexoes = _conexoes(uid)
    if not conexoes:
        return None, "Nenhuma conexão cadastrada."

    # Importado antes de existir conexao_id fica sem saber de que banco
    # veio, e o cadeado da conta não alcança. Uma vez só, a importação volta
    # um ano para preencher (o upsert grava a conexão nas linhas que já
    # existem).
    if buscar_um(
        "SELECT 1 AS x FROM transacoes WHERE usuario_id = %s AND origem_id IS NOT NULL "
        "AND conexao_id IS NULL LIMIT 1",
        (uid,),
    ):
        desde = min(desde, hoje - timedelta(days=365))
    por_item = {c["item_id"]: c["id"] for c in conexoes}

    cred, _ = _credencial(uid)
    lista, ignoradas, descartados, aviso = openfinance.transacoes(
        cred, [c["item_id"] for c in conexoes], desde
    )
    if aviso:
        return None, aviso

    # Descarte que o usuário marcou como errado na conferência volta para a
    # soma: a regra continua achando que é movimento interno, mas a palavra
    # final é dele.
    # Só enquanto a decisão for a mesma que ele julgou: se a regra mudou o
    # motivo ou o par, o veredito cai e o descarte volta a ser conferido.
    restaurados = {
        d["origem_id"]: (d["motivo"], d["par_origem_id"]) for d in buscar_todos(
            "SELECT origem_id, motivo, par_origem_id FROM descartes "
            "WHERE usuario_id = %s AND veredito = 'errado'",
            (uid,),
        )
    }
    auditaveis = [d for d in descartados if d["motivo"] in MOTIVOS_CONFERIDOS and d["data"]]
    voltam = {
        d["origem_id"] for d in auditaveis
        if restaurados.get(d["origem_id"]) == (d["motivo"], d["par"])
    }
    for d in auditaveis:
        if d["origem_id"] in voltam:
            ignoradas[d["motivo"]] -= 1
            lista.append({k: d[k] for k in CAMPOS_LANCAMENTO})
    fora = [d["origem_id"] for d in descartados if d["origem_id"] not in voltam]

    regras = _regras(uid)
    for t in lista:
        t["categoria"] = _categoria_pela_regra(t["nome"], regras) or t["categoria"]

    existentes = set()
    if lista:
        marcadores = ", ".join(["%s"] * len(lista))
        existentes = {
            l["origem_id"] for l in buscar_todos(
                f"SELECT origem_id FROM transacoes WHERE usuario_id = %s AND origem_id IN ({marcadores})",
                (uid, *[t["origem_id"] for t in lista]),
            )
        }

    removidas = 0
    with cursor(commit=True) as cur:
        if lista:
            # A linha que já existe só ganha o `meio`: categoria e "não conta"
            # podem ter sido editados pelo usuário e ficam como estão.
            cur.executemany(
                "INSERT INTO transacoes (usuario_id, data, nome, valor, natureza, "
                "categoria, recorrencia, meio, origem_id, conexao_id) "
                "VALUES (%s, %s, %s, %s, %s, %s, 'unica', %s, %s, %s) "
                "ON DUPLICATE KEY UPDATE meio = VALUES(meio), "
                "conexao_id = COALESCE(VALUES(conexao_id), conexao_id)",
                [(uid, t["data"], t["nome"], t["valor"], t["natureza"], t["categoria"],
                  t["meio"], t["origem_id"], por_item.get(t.get("item_id"))) for t in lista],
            )
        # O que a regra atual descarta sai do banco mesmo que uma importação
        # de antes da regra tenha deixado entrar. Só toca linha importada.
        if fora:
            marcadores = ", ".join(["%s"] * len(fora))
            cur.execute(
                f"DELETE FROM transacoes WHERE usuario_id = %s AND origem_id IN ({marcadores})",
                (uid, *fora),
            )
            removidas = cur.rowcount
        _guardar_descartes(cur, uid, desde, auditaveis)
        cur.execute(
            "UPDATE conexoes_bancarias SET importado_ate = %s WHERE usuario_id = %s",
            (hoje, uid),
        )

    novas = [t for t in lista if t["origem_id"] not in existentes]
    return {
        "ok": True,
        "lidas": len(lista),
        "novas": len(novas),
        "jaExistiam": len(lista) - len(novas),
        "removidas": removidas,
        "ignoradas": ignoradas,
        "_novas": novas,
    }, None


# ── Conferir números ─────────────────────────────────────────
# Mede a regra que tira movimento interno da soma. De um lado, o que a
# importação descartou (tabela `descartes`); do outro, importadas que
# ficaram na soma mas parecem o mesmo dinheiro passando de uma conta para
# outra. O usuário marca cada um como certo ou errado, e a taxa de acerto
# sai daí.
MOTIVOS_CONFERIDOS = ("pagamentoFatura", "transferencias")
CAMPOS_LANCAMENTO = ("origem_id", "data", "nome", "valor", "natureza", "categoria", "meio", "item_id")

# A mesma folga da regra de pares (openfinance._FOLGA_PAR_DIAS): é o tempo
# que um movimento interno leva para aparecer dos dois lados.
_FOLGA_SUSPEITO = timedelta(days=5)


def _guardar_descartes(cur, uid, desde, descartes):
    """Grava o que esta importação deixou de fora, com motivo e par.

    O veredito sobrevive enquanto motivo e par forem os mesmos; se a regra
    mudou a decisão, ele volta a NULL para ser conferido de novo. O que
    estava descartado no período e deixou de estar sai da tabela.
    """
    if descartes:
        cur.executemany(
            "INSERT INTO descartes (usuario_id, origem_id, data, nome, valor, natureza, meio, "
            "conta, categoria, motivo, par_origem_id) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
            # veredito e conferido_em comparam só o valor antigo da linha com o
            # novo, sem depender da ordem das atribuições (o MySQL aplica da
            # esquerda para a direita; o TiDB não garante o mesmo). Por isso
            # vêm antes de motivo e par serem trocados, e nenhuma lê a outra.
            "ON DUPLICATE KEY UPDATE "
            "veredito = IF(descartes.motivo <=> VALUES(motivo) "
            "AND descartes.par_origem_id <=> VALUES(par_origem_id), descartes.veredito, NULL), "
            "conferido_em = IF(descartes.motivo <=> VALUES(motivo) "
            "AND descartes.par_origem_id <=> VALUES(par_origem_id), descartes.conferido_em, NULL), "
            "data = VALUES(data), nome = VALUES(nome), valor = VALUES(valor), natureza = VALUES(natureza), "
            "meio = VALUES(meio), conta = VALUES(conta), categoria = VALUES(categoria), "
            "motivo = VALUES(motivo), par_origem_id = VALUES(par_origem_id)",
            [(uid, d["origem_id"], d["data"], d["nome"], d["valor"], d["natureza"], d["meio"],
              d["conta"], d["categoria"], d["motivo"], d["par"]) for d in descartes],
        )
    ids = [d["origem_id"] for d in descartes]
    fora = f" AND origem_id NOT IN ({', '.join(['%s'] * len(ids))})" if ids else ""
    cur.execute(
        f"DELETE FROM descartes WHERE usuario_id = %s AND data >= %s{fora}",
        (uid, desde, *ids),
    )


def _suspeitos(linhas):
    """Pares que ficaram na soma mas parecem o mesmo dinheiro: mesmo valor,
    direções opostas, até _FOLGA_SUSPEITO de distância. Cada lançamento
    entra em um par só, o mais próximo na data."""
    receitas = {}
    for l in linhas:
        if l["natureza"] == "receita":
            receitas.setdefault(l["valor"], []).append(l)

    candidatos = []
    for d in linhas:
        if d["natureza"] != "despesa":
            continue
        for r in receitas.get(d["valor"], []):
            dias = abs(r["data"] - d["data"])
            if dias <= _FOLGA_SUSPEITO:
                candidatos.append((dias, d["id"], r["id"], d, r))
    candidatos.sort(key=lambda c: c[:3])

    usados, pares = set(), []
    for _, a, b, d, r in candidatos:
        if a in usados or b in usados:
            continue
        usados.update((a, b))
        pares.append((d, r))
    pares.sort(key=lambda p: max(p[0]["data"], p[1]["data"]), reverse=True)
    return pares


def _item_conferencia(l):
    return {
        "id": l["id"],
        "data": l["data"].isoformat(),
        "nome": l["nome"],
        "valor": float(l["valor"]),
        "natureza": l["natureza"],
        "meio": l["meio"],
        "conta": l.get("conta"),
        "categoria": l.get("categoria"),
        "veredito": l.get("veredito"),
    }


@app.get("/api/conferencia")
@exige_sessao()
def ler_conferencia():
    """Descartes agrupados por par, suspeitos e o placar da regra."""
    uid = g.sessao["usuario_id"]
    descartes = buscar_todos(
        "SELECT id, origem_id, data, nome, valor, natureza, meio, conta, motivo, "
        "par_origem_id, veredito FROM descartes WHERE usuario_id = %s "
        "ORDER BY data DESC, id DESC",
        (uid,),
    )

    # Os dois lados de um par viram um grupo só, a saída primeiro: lido de
    # cima para baixo, é "saiu daqui, chegou ali".
    por_origem = {d["origem_id"]: d for d in descartes}
    grupos, vistos = [], set()
    for d in descartes:
        if d["id"] in vistos:
            continue
        par = por_origem.get(d["par_origem_id"])
        itens = [d] + ([par] if par and par["id"] not in vistos else [])
        vistos.update(i["id"] for i in itens)
        itens.sort(key=lambda i: i["natureza"] != "despesa")
        grupos.append({"motivo": d["motivo"], "itens": [_item_conferencia(i) for i in itens]})

    # Descarte devolvido à soma pelo usuário não entra: ele já disse que
    # aquilo é gasto de verdade, e o par dele continua descartado.
    linhas = buscar_todos(
        "SELECT id, data, nome, valor, natureza, meio, categoria FROM transacoes "
        "WHERE usuario_id = %s AND origem_id IS NOT NULL AND ignorada = 0 "
        "AND conferencia IS NULL AND data >= %s "
        "AND origem_id NOT IN (SELECT origem_id FROM descartes WHERE usuario_id = %s) "
        "ORDER BY data, id",
        (uid, date.today() - timedelta(days=400), uid),
    )
    suspeitos = _suspeitos(linhas)

    # Os quatro jeitos de a regra acertar ou errar, contados em lançamentos:
    # descartou certo, descartou errado, manteve certo, faltou descartar.
    conferidas = {
        l["conferencia"]: l["n"] for l in buscar_todos(
            "SELECT conferencia, COUNT(*) AS n FROM transacoes "
            "WHERE usuario_id = %s AND conferencia IS NOT NULL GROUP BY conferencia",
            (uid,),
        )
    }

    return jsonify({
        "resumo": {
            "descartes": len(descartes),
            "certos": sum(1 for d in descartes if d["veredito"] == "certo"),
            "errados": sum(1 for d in descartes if d["veredito"] == "errado"),
            "mantidos": conferidas.get("certo", 0),
            "faltaram": conferidas.get("errado", 0),
            "suspeitos": len(suspeitos),
        },
        "grupos": grupos,
        "suspeitos": [
            {"itens": [_item_conferencia(d), _item_conferencia(r)]} for d, r in suspeitos
        ],
    })


@app.put("/api/conferencia/descartes/<int:descarte_id>")
@exige_sessao()
def julgar_descarte(descarte_id):
    """Certo, errado, ou de volta a não conferido (null).

    'errado' põe o lançamento de volta em Entradas e Saídas na hora, e as
    importações seguintes respeitam; desfazer o tira de novo.
    """
    veredito = (request.get_json(silent=True) or {}).get("veredito")
    if veredito not in ("certo", "errado", None):
        return erro("Veredito inválido.")

    uid = g.sessao["usuario_id"]
    d = buscar_um(
        "SELECT origem_id, data, nome, valor, natureza, meio, categoria, veredito "
        "FROM descartes WHERE id = %s AND usuario_id = %s",
        (descarte_id, uid),
    )
    if not d:
        return erro("Descarte não encontrado.", 404)
    categoria = _categoria_pela_regra(d["nome"], _regras(uid)) or d["categoria"]

    with cursor(commit=True) as cur:
        cur.execute(
            "UPDATE descartes SET veredito = %s, conferido_em = IF(%s IS NULL, NULL, NOW()) "
            "WHERE id = %s AND usuario_id = %s",
            (veredito, veredito, descarte_id, uid),
        )
        if veredito == "errado" and d["veredito"] != "errado":
            cur.execute(
                "INSERT INTO transacoes (usuario_id, data, nome, valor, natureza, "
                "categoria, recorrencia, meio, origem_id) "
                "VALUES (%s, %s, %s, %s, %s, %s, 'unica', %s, %s) "
                "ON DUPLICATE KEY UPDATE meio = VALUES(meio)",
                (uid, d["data"], d["nome"], d["valor"], d["natureza"], categoria,
                 d["meio"], d["origem_id"]),
            )
        elif d["veredito"] == "errado" and veredito != "errado":
            cur.execute(
                "DELETE FROM transacoes WHERE usuario_id = %s AND origem_id = %s",
                (uid, d["origem_id"]),
            )
    return jsonify({"ok": True})


@app.post("/api/conferencia/suspeitos")
@exige_sessao()
def julgar_suspeito():
    """Julga um par suspeito de uma vez.

    'errado': os dois são o mesmo dinheiro mudando de conta, então saem da
    soma como "não conta". 'certo': contar os dois está certo, e o par não
    volta a aparecer.
    """
    d = request.get_json(silent=True) or {}
    ids, veredito = d.get("ids"), d.get("veredito")
    if (
        veredito not in ("certo", "errado")
        or not isinstance(ids, list)
        or len(set(ids)) != 2
        or not all(isinstance(i, int) for i in ids)
    ):
        return erro("Pedido inválido.")

    uid = g.sessao["usuario_id"]
    achados = buscar_um(
        "SELECT COUNT(*) AS n FROM transacoes WHERE usuario_id = %s "
        "AND origem_id IS NOT NULL AND id IN (%s, %s)",
        (uid, *ids),
    )["n"]
    if achados != 2:
        return erro("Lançamento não encontrado.", 404)

    with cursor(commit=True) as cur:
        cur.execute(
            "UPDATE transacoes SET conferencia = %s, ignorada = IF(%s = 'errado', 1, ignorada) "
            "WHERE usuario_id = %s AND id IN (%s, %s)",
            (veredito, veredito, uid, *ids),
        )
    return jsonify({"ok": True})


# ── Regras de categoria ──────────────────────────────────────
def _regras(usuario_id):
    # Padrão mais longo primeiro: "pix enviado para vilma" ganha de "pix".
    return buscar_todos(
        "SELECT id, padrao, categoria FROM regras_categoria WHERE usuario_id = %s "
        "ORDER BY CHAR_LENGTH(padrao) DESC, id",
        (usuario_id,),
    )


def _categoria_pela_regra(nome, regras):
    texto = openfinance.normalizar(nome)
    for r in regras:
        if r["padrao"] in texto:
            return r["categoria"]
    return None


@app.get("/api/regras")
@exige_sessao()
def listar_regras():
    return jsonify([
        {"id": r["id"], "padrao": r["padrao"], "categoria": r["categoria"]}
        for r in _regras(g.sessao["usuario_id"])
    ])


@app.post("/api/regras")
@exige_sessao()
def criar_regra():
    """"Descrição contém X vira Y". Vale para as próximas importações e já
    é aplicada às importadas que existem, menos as de categoria escolhida à
    mão (categoria_manual)."""
    d = request.get_json(silent=True) or {}
    padrao = openfinance.normalizar(d.get("padrao"))[:120]
    categoria = str(d.get("categoria") or "").strip()[:80]
    if len(padrao) < 3:
        return erro("O texto da regra precisa de pelo menos 3 letras.")
    if not categoria:
        return erro("Informe a categoria.")

    uid = g.sessao["usuario_id"]
    alvo = [
        l["id"] for l in buscar_todos(
            "SELECT id, nome FROM transacoes WHERE usuario_id = %s AND origem_id IS NOT NULL "
            "AND categoria_manual = 0",
            (uid,),
        )
        if padrao in openfinance.normalizar(l["nome"])
    ]

    with cursor(commit=True) as cur:
        cur.execute(
            "INSERT INTO regras_categoria (usuario_id, padrao, categoria) VALUES (%s, %s, %s) "
            "ON DUPLICATE KEY UPDATE categoria = VALUES(categoria)",
            (uid, padrao, categoria),
        )
        if alvo:
            marcadores = ", ".join(["%s"] * len(alvo))
            cur.execute(
                f"UPDATE transacoes SET categoria = %s WHERE usuario_id = %s AND id IN ({marcadores})",
                (categoria, uid, *alvo),
            )
    return jsonify({"ok": True, "padrao": padrao, "aplicadas": len(alvo)}), 201


@app.delete("/api/regras/<int:regra_id>")
@exige_sessao()
def apagar_regra(regra_id):
    """Some a regra; os lançamentos que ela já trocou ficam como estão."""
    with cursor(commit=True) as cur:
        cur.execute(
            "DELETE FROM regras_categoria WHERE id = %s AND usuario_id = %s",
            (regra_id, g.sessao["usuario_id"]),
        )
        if cur.rowcount == 0:
            return erro("Regra não encontrada.", 404)
    return jsonify({"ok": True})


_TABELAS_ESPERADAS = (
    "usuarios", "sessoes", "transacoes", "orcamentos", "investimentos", "metas",
    "subtarefas", "conexoes_bancarias", "credenciais_pluggy", "regras_categoria",
    "aceites", "descartes", "passkeys", "desafios_webauthn",
    "espacos", "espaco_membros", "convites",
    "push_inscricoes", "notif_preferencias", "webhooks_pluggy", "notificacoes_enviadas",
)
# Colunas acrescentadas depois que o banco da nuvem já existia (as mesmas
# de ops/atualizar_banco.py).
_COLUNAS_ESPERADAS = (
    ("transacoes", "conexao_id"),
    ("transacoes", "privada"),
    ("conexoes_bancarias", "privada"),
)


@app.get("/api/saude")
def saude():
    """Diz se o banco responde e quais tabelas do schema.sql ainda faltam
    nele (banco da nuvem criado antes de uma tabela nova, por exemplo).
    Só nomes de tabela, que já estão no repositório."""
    existentes = {
        list(r.values())[0]
        for r in buscar_todos(
            "SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA = %s",
            (config.DB_NAME,),
        )
    }
    faltando = [t for t in _TABELAS_ESPERADAS if t not in existentes]
    colunas = {
        (r["TABLE_NAME"], r["COLUMN_NAME"])
        for r in buscar_todos(
            "SELECT TABLE_NAME, COLUMN_NAME FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = %s",
            (config.DB_NAME,),
        )
    }
    colunas_faltando = [f"{t}.{c}" for t, c in _COLUNAS_ESPERADAS if (t, c) not in colunas]
    return jsonify({
        "ok": not faltando and not colunas_faltando,
        "banco": config.DB_NAME,
        "tabelasFaltando": faltando,
        "colunasFaltando": colunas_faltando,
        "comoCorrigir": "python ops/atualizar_banco.py" if faltando or colunas_faltando else None,
    })


def _porta_ocupada(host: str, porta: int) -> bool:
    """O Windows deixa DOIS processos escutarem a mesma porta.

    O socket do Werkzeug usa SO_REUSEADDR, e no Windows isso permite um
    segundo bind na mesma porta em vez de recusar como no Linux. O
    resultado é que as respostas passam a vir ora de um processo, ora do
    outro; se um deles for de antes de uma alteração no código, a API
    parece rodar versão velha de forma intermitente.

    Conectar antes de subir é o que detecta isso: se alguém aceita a
    conexão, já tem servidor ali.
    """
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, porta)) == 0


if __name__ == "__main__":
    if _porta_ocupada(config.API_HOST, config.API_PORT):
        raise SystemExit(
            f"\nJá existe algo escutando em {config.API_HOST}:{config.API_PORT}.\n"
            "Encerre a API que está rodando antes de subir outra: duas ao mesmo\n"
            "tempo se revezam nas respostas e uma delas pode estar com código antigo.\n"
        )

    print(f"API em http://{config.API_HOST}:{config.API_PORT}  (banco: {config.DB_NAME})")
    app.run(host=config.API_HOST, port=config.API_PORT, debug=False)
