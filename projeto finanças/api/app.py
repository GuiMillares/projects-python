"""API local do painel financeiro.

Escuta só em 127.0.0.1: é o processo com quem o webview do Tauri
conversa. Substitui o par Firebase Auth + Cloud Functions: o login
virou senha com scrypt neste processo, e o 2FA que antes rodava na
Cloud Function roda em seguranca.py. A regra que valia lá continua
valendo aqui: o segredo TOTP não sai do servidor.

Rodar:
    python app.py
"""

import re
from datetime import date, datetime
from decimal import Decimal
from functools import wraps

from flask import Flask, g, jsonify, request
from werkzeug.exceptions import HTTPException

import config
import cotacoes
import gamificacao
import ia
import seguranca
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


def exige_sessao(completa=True):
    """Protege a rota.

    completa=True  → exige 2FA já validado (rotas de dado).
    completa=False → aceita a sessão parcial (só as rotas de 2FA).
    """
    def decorador(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            sessao = seguranca.ler_sessao(_token_do_header())
            if not sessao:
                return erro("Sessão inválida ou expirada.", 401)
            if completa and not sessao["dois_fatores_ok"]:
                return erro("Verificação em duas etapas pendente.", 403)
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
    """Gera o segredo e devolve só o otpauth:// para virar QR code."""
    sessao = g.sessao
    uri = seguranca.gerar_segredo(sessao["usuario_id"], sessao["email"])
    return jsonify({"otpauthUri": uri})


@app.post("/api/auth/2fa/verify")
@exige_sessao(completa=False)
def verificar_2fa():
    sessao = g.sessao
    codigo = (request.get_json(silent=True) or {}).get("codigo", "")

    if not seguranca.conferir_codigo(sessao["usuario_id"], codigo):
        seguranca.registrar_falha(sessao["usuario_id"])
        return erro("Código incorreto ou expirado.", 401)

    seguranca.limpar_falhas(sessao["usuario_id"])
    seguranca.promover_sessao(sessao["id"])
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
@exige_sessao()
def ler_perfil():
    s = g.sessao
    # A foto não vem no JOIN da sessão de propósito: ler_sessao roda em
    # toda requisição, e arrastar dezenas de KB de imagem junto seria
    # desperdício em cada chamada de dado.
    linha = buscar_um("SELECT foto FROM usuarios WHERE id = %s", (s["usuario_id"],))
    return jsonify({
        "email": s["email"],
        "nome": s["nome"],
        "foto": (linha or {}).get("foto"),
        "twoFactorEnrolled": bool(s["totp_confirmado"]),
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
    }


@app.get("/api/transacoes")
@exige_sessao()
def listar_transacoes():
    """Devolve o histórico do usuário, mais antigo primeiro.

    O recorte de período fica no cliente: são poucos milhares de linhas
    num app pessoal, e o dashboard precisa do histórico inteiro para o
    saldo acumulado bater.
    """
    linhas = buscar_todos(
        "SELECT id, data, nome, valor, natureza, categoria, recorrencia "
        "FROM transacoes WHERE usuario_id = %s ORDER BY data, id",
        (g.sessao["usuario_id"],),
    )
    return jsonify([_serializar(t) for t in linhas])


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
        "       concluida_em, criado_em "
        "  FROM metas WHERE usuario_id = %s "
        " ORDER BY concluida, COALESCE(prazo, '9999-12-31'), id",
        (usuario_id,),
    )
    if not metas:
        return []

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
        por_meta[s["meta_id"]].append({
            "id": s["id"],
            "titulo": s["titulo"],
            "concluida": bool(s["concluida"]),
            "xp": int(s["xp"]),
            "ordem": int(s["ordem"]),
            "geradaPorIa": bool(s["gerada_por_ia"]),
        })

    return [{
        "id": m["id"],
        "titulo": m["titulo"],
        "descricao": m["descricao"],
        "alvo": float(m["alvo"]) if m["alvo"] is not None else None,
        "guardado": float(m["guardado"]),
        "prazo": m["prazo"].isoformat() if isinstance(m["prazo"], date) else m["prazo"],
        "concluida": bool(m["concluida"]),
        "subtarefas": por_meta[m["id"]],
        "bonusXp": gamificacao.bonus_da_meta(sum(s["xp"] for s in por_meta[m["id"]])),
    } for m in metas]


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
        campos += ["concluida = %s", "concluida_em = %s"]
        valores += [int(concluida), datetime.now() if concluida else None]

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


@app.get("/api/saude")
def saude():
    return jsonify({"ok": True, "banco": config.DB_NAME})


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
