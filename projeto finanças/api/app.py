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
from datetime import date, datetime, timedelta
from decimal import Decimal
from functools import wraps

from flask import Flask, g, jsonify, request
from werkzeug.exceptions import HTTPException

import config
import cotacoes
import gamificacao
import ia
import openfinance
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
        "importada": t.get("origem_id") is not None,
        "ignorada": bool(t.get("ignorada")),
        "meio": t.get("meio"),
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
        "SELECT id, data, nome, valor, natureza, categoria, recorrencia, origem_id, "
        "ignorada, meio FROM transacoes WHERE usuario_id = %s ORDER BY data, id",
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
        "SELECT id, item_id FROM conexoes_bancarias WHERE id = %s AND usuario_id = %s",
        (conexao_id, usuario_id),
    )


@app.get("/api/openfinance")
@exige_sessao()
def ler_openfinance():
    """Saldos, cartões e faturas de cada conexão, lidos da Pluggy agora.

    Uma conexão que falha não derruba as outras: ela volta com `dados` nulo
    e o próprio `aviso`, e a tela mostra o resto.
    """
    conexoes = _conexoes(g.sessao["usuario_id"])

    saida = []
    for c in conexoes:
        dados, aviso = openfinance.panorama(c["item_id"])
        saida.append({
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
    ultimas = [c["importado_ate"] for c in conexoes if c["importado_ate"]]
    if conexoes and len(ultimas) == len(conexoes):
        desde = min(ultimas) - timedelta(days=35)
    else:
        desde = hoje - timedelta(days=365)

    return jsonify({
        "disponivel": openfinance.disponivel(),
        "aviso": None if openfinance.disponivel() else openfinance.sem_credencial(),
        "conexoes": saida,
        "importarDesde": desde.isoformat(),
    })


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

    token, aviso = openfinance.token_do_widget(g.sessao["usuario_id"], item_id)
    if not token:
        return erro(aviso, 502)
    return jsonify({"accessToken": token})


@app.post("/api/openfinance/conexoes")
@exige_sessao()
def criar_conexao():
    item_id = str((request.get_json(silent=True) or {}).get("itemId") or "").strip().lower()

    # Confere na Pluggy antes de gravar: id digitado errado vira erro aqui,
    # e não uma conexão quebrada para sempre na tela.
    item, aviso = openfinance.conferir(item_id)
    if not item:
        return erro(aviso or "Conexão não encontrada.")

    with cursor(commit=True) as cur:
        cur.execute(
            "INSERT INTO conexoes_bancarias (usuario_id, item_id, instituicao) "
            "VALUES (%s, %s, %s) AS novo "
            "ON DUPLICATE KEY UPDATE instituicao = novo.instituicao",
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
        cur.execute(
            "DELETE FROM conexoes_bancarias WHERE id = %s AND usuario_id = %s",
            (conexao_id, g.sessao["usuario_id"]),
        )
    openfinance.esquecer(conexao["item_id"])
    return jsonify({"ok": True})


@app.post("/api/openfinance/conexoes/<int:conexao_id>/atualizar")
@exige_sessao()
def atualizar_conexao(conexao_id):
    """Pede à Pluggy para buscar os dados no banco agora. A resposta volta
    na hora; a sincronização em si roda do lado de lá e a tela acompanha
    pelo status da conexão."""
    conexao = _conexao_do_usuario(conexao_id, g.sessao["usuario_id"])
    if not conexao:
        return erro("Conexão não encontrada.", 404)

    aviso = openfinance.atualizar(conexao["item_id"])
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
    hoje = date.today()
    if desde > hoje:
        return erro("A data inicial não pode ser no futuro.")

    conexoes = _conexoes(uid)
    if not conexoes:
        return erro("Nenhuma conexão cadastrada.")

    lista, ignoradas, descartados, aviso = openfinance.transacoes(
        [c["item_id"] for c in conexoes], desde
    )
    if aviso:
        return erro(aviso, 502)

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
                "categoria, recorrencia, meio, origem_id) "
                "VALUES (%s, %s, %s, %s, %s, %s, 'unica', %s, %s) AS novo "
                "ON DUPLICATE KEY UPDATE meio = novo.meio",
                [(uid, t["data"], t["nome"], t["valor"], t["natureza"], t["categoria"],
                  t["meio"], t["origem_id"]) for t in lista],
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

    novas = sum(1 for t in lista if t["origem_id"] not in existentes)
    return jsonify({
        "ok": True,
        "lidas": len(lista),
        "novas": novas,
        "jaExistiam": len(lista) - novas,
        "removidas": removidas,
        "ignoradas": ignoradas,
    })


# ── Conferir números ─────────────────────────────────────────
# Mede a regra que tira movimento interno da soma. De um lado, o que a
# importação descartou (tabela `descartes`); do outro, importadas que
# ficaram na soma mas parecem o mesmo dinheiro passando de uma conta para
# outra. O usuário marca cada um como certo ou errado, e a taxa de acerto
# sai daí.
MOTIVOS_CONFERIDOS = ("pagamentoFatura", "transferencias")
CAMPOS_LANCAMENTO = ("origem_id", "data", "nome", "valor", "natureza", "categoria", "meio")

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
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) AS novo "
            # O MySQL aplica as atribuições da esquerda para a direita: o
            # veredito é decidido antes de motivo e par serem trocados.
            "ON DUPLICATE KEY UPDATE "
            "veredito = IF(descartes.motivo <=> novo.motivo "
            "AND descartes.par_origem_id <=> novo.par_origem_id, descartes.veredito, NULL), "
            "conferido_em = IF(descartes.veredito IS NULL, NULL, descartes.conferido_em), "
            "data = novo.data, nome = novo.nome, valor = novo.valor, natureza = novo.natureza, "
            "meio = novo.meio, conta = novo.conta, categoria = novo.categoria, "
            "motivo = novo.motivo, par_origem_id = novo.par_origem_id",
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
                "VALUES (%s, %s, %s, %s, %s, %s, 'unica', %s, %s) AS novo "
                "ON DUPLICATE KEY UPDATE meio = novo.meio",
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
            "INSERT INTO regras_categoria (usuario_id, padrao, categoria) VALUES (%s, %s, %s) AS novo "
            "ON DUPLICATE KEY UPDATE categoria = novo.categoria",
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
