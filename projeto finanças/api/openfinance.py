"""Open Finance via Pluggy.

O Open Finance Brasil só entrega dado para instituição autorizada pelo
Banco Central, então o app não fala com os bancos: fala com a Pluggy. As
contas são conectadas no Meu Pluggy (meu.pluggy.ai), com o consentimento
dado no app de cada banco, e aqui só chegam os ids dessas conexões
("items", no vocabulário da Pluggy).

Só a biblioteca padrão, como em cotacoes.py.

REGRA DESTE MÓDULO: igual a cotacoes.py e ia.py, ele nunca levanta exceção
para quem chama. Toda função pública devolve (resultado, aviso), e o aviso
é texto para a tela, não erro para estourar. Se a Pluggy cair, a tela de
Contas mostra o aviso e o resto do app nem fica sabendo.

Saldo e fatura NÃO são gravados no banco, pelo mesmo motivo do valor atual
dos investimentos: seriam números velhos contradizendo a tela. O que vai
para o MySQL são só os ids das conexões e, quando o usuário pede, as
transações importadas para Entradas e Saídas.
"""

import calendar
import json
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import config

# O Brasil não tem horário de verão desde 2019, então -3 fixo resolve sem
# depender do tzdata, que nem sempre vem instalado no Python do Windows.
_BRT = timezone(timedelta(hours=-3))

# Id de item da Pluggy é um UUID. Validar aqui importa porque ele entra no
# caminho da URL: deixar passar barra viraria injeção de caminho.
ID_VALIDO = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")

_chave = {"valor": None, "expira": 0.0}

# item_id -> (momento_em_que_expira, dados)
_cache: dict[str, tuple[float, dict]] = {}


class _FalhaPluggy(Exception):
    def __init__(self, mensagem, status=None):
        super().__init__(mensagem)
        self.status = status


def disponivel() -> bool:
    return bool(config.PLUGGY_CLIENT_ID and config.PLUGGY_CLIENT_SECRET)


# ── HTTP ─────────────────────────────────────────────────────
def _mensagem_http(e: urllib.error.HTTPError) -> str:
    detalhe = ""
    try:
        detalhe = (json.loads(e.read().decode("utf-8")) or {}).get("message") or ""
    except Exception:  # noqa: BLE001 - corpo de erro ilegível não muda a resposta
        pass

    if e.code == 401:
        base = (
            "A Pluggy recusou as credenciais. Confira FIN_PLUGGY_CLIENT_ID e "
            "FIN_PLUGGY_CLIENT_SECRET."
        )
    elif e.code == 404:
        base = "A Pluggy não encontrou essa conexão. Confira o id no painel da Pluggy."
    elif e.code == 429:
        base = "Limite de consultas da Pluggy atingido. Tente de novo em alguns minutos."
    else:
        base = f"A Pluggy respondeu com erro {e.code}."
    return f"{base} ({detalhe})" if detalhe else base


def _requisitar(metodo, caminho, params=None, corpo=None, autenticar=True):
    url = config.PLUGGY_BASE + caminho
    if params:
        url += "?" + urllib.parse.urlencode(params)

    headers = {"User-Agent": "painel-financas/1.0", "Accept": "application/json"}
    dados = None
    if corpo is not None:
        dados = json.dumps(corpo).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if autenticar:
        headers["X-API-KEY"] = _api_key()

    req = urllib.request.Request(url, data=dados, headers=headers, method=metodo)
    try:
        with urllib.request.urlopen(req, timeout=config.PLUGGY_TIMEOUT) as resp:
            bruto = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        raise _FalhaPluggy(_mensagem_http(e), e.code) from e
    except urllib.error.URLError as e:
        raise _FalhaPluggy("Sem conexão com a Pluggy agora.") from e

    # parse_float=Decimal: dinheiro não passa por float nem na leitura.
    return json.loads(bruto, parse_float=Decimal) if bruto else {}


def _api_key() -> str:
    if _chave["valor"] and time.time() < _chave["expira"]:
        return _chave["valor"]

    r = _requisitar(
        "POST", "/auth",
        corpo={"clientId": config.PLUGGY_CLIENT_ID, "clientSecret": config.PLUGGY_CLIENT_SECRET},
        autenticar=False,
    )
    if not r.get("apiKey"):
        raise _FalhaPluggy("A Pluggy não devolveu a chave de acesso.")

    # A chave vale 2 horas. Renovar com folga evita uma consulta cair no
    # meio por expirar entre um request e outro.
    _chave["valor"] = r["apiKey"]
    _chave["expira"] = time.time() + 100 * 60
    return _chave["valor"]


def _chamar(metodo, caminho, params=None, corpo=None):
    """Um request autenticado. Se a chave tiver vencido do lado de lá antes
    do nosso relógio, pede outra e tenta uma única vez de novo."""
    try:
        return _requisitar(metodo, caminho, params, corpo)
    except _FalhaPluggy as e:
        if e.status not in (401, 403) or not _chave["valor"]:
            raise
        _chave["valor"] = None
        return _requisitar(metodo, caminho, params, corpo)


def _todas(caminho, params):
    """Junta as páginas de uma listagem até o teto de PLUGGY_MAX_PAGINAS."""
    itens, pagina = [], 1
    while True:
        r = _chamar("GET", caminho, {**params, "page": pagina})
        itens += r.get("results") or []
        if pagina >= int(r.get("totalPages") or 1) or pagina >= config.PLUGGY_MAX_PAGINAS:
            return itens
        pagina += 1


def _transacoes_da_conta(conta_id, desde, ate=None):
    """GET /v2/transactions, paginado por cursor. O /transactions antigo
    responde 410. O `next` vem como query string pronta; daqui só se tira o
    `after` dela, com o mesmo teto de PLUGGY_MAX_PAGINAS."""
    params = {"accountId": conta_id, "dateFrom": desde.isoformat()}
    if ate:
        params["dateTo"] = ate.isoformat()

    itens = []
    for _ in range(config.PLUGGY_MAX_PAGINAS):
        r = _chamar("GET", "/v2/transactions", params)
        itens += r.get("results") or []
        cursor = urllib.parse.parse_qs(str(r.get("next") or "").lstrip("?")).get("after")
        if not cursor:
            break
        params = {**params, "after": cursor[0]}
    return itens


# ── Datas e números ──────────────────────────────────────────
def _data(iso) -> date | None:
    """'2026-10-20T03:00:00.000Z' vira a data no horário de Brasília.

    A Pluggy manda meia-noite de Brasília como 03:00 UTC; cortar a string
    nos 10 primeiros caracteres funcionaria nesse caso, mas erraria o dia de
    qualquer compra feita depois das 21h.
    """
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo:
        dt = dt.astimezone(_BRT)
    return dt.date()


def _iso(d):
    return d.isoformat() if d else None


def _no_dia(ano, mes, dia) -> date:
    """O dia pedido, ou o último do mês quando ele não existe (31 de abril)."""
    return date(ano, mes, min(dia, calendar.monthrange(ano, mes)[1]))


def _somar_meses(d: date, n: int, dia: int | None = None) -> date:
    ano, mes = divmod(d.month - 1 + n, 12)
    return _no_dia(d.year + ano, mes + 1, dia or d.day)


def _num(v):
    """float só na borda de saída, como em app.py."""
    return float(v) if v is not None else None


def normalizar(texto) -> str:
    sem_acento = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", sem_acento.lower()).strip()


# ── Cache ────────────────────────────────────────────────────
def _do_cache(item_id):
    achado = _cache.get(item_id)
    if not achado:
        return None
    expira, dados = achado
    if time.time() > expira:
        _cache.pop(item_id, None)
        return None
    return dados


def _guardar(item_id, dados):
    _cache[item_id] = (time.time() + config.PLUGGY_CACHE_SEGUNDOS, dados)


# ── Tradução do payload ──────────────────────────────────────
_STATUS = {
    "UPDATED": "Atualizado",
    "UPDATING": "Sincronizando",
    "LOGIN_ERROR": "Precisa reconectar",
    "OUTDATED": "Desatualizado",
    "WAITING_USER_INPUT": "Aguardando você",
}

_SUBTIPOS = {
    "CHECKING_ACCOUNT": "Conta corrente",
    "SAVINGS_ACCOUNT": "Poupança",
    "CREDIT_CARD": "Cartão de crédito",
}


def _item(i):
    status = i.get("status") or ""
    return {
        "itemId": i.get("id"),
        "instituicao": (i.get("connector") or {}).get("name") or "Conexão",
        "status": status,
        "statusTexto": _STATUS.get(status, status.title() or "Desconhecido"),
        "atualizadoEm": i.get("lastUpdatedAt"),
    }


def _nome_conta(c):
    return c.get("marketingName") or c.get("name") or "Conta"


def _conta(c):
    return {
        "id": c.get("id"),
        "nome": _nome_conta(c),
        "numero": c.get("number"),
        "tipo": _SUBTIPOS.get(c.get("subtype"), "Conta"),
        "saldo": _num(c.get("balance")),
        "moeda": c.get("currencyCode") or "BRL",
    }


_TIPOS_INVESTIMENTO = {
    "FIXED_INCOME": "Renda fixa",
    "MUTUAL_FUND": "Fundo",
    "EQUITY": "Ações",
    "ETF": "ETF",
    "COE": "COE",
    "SECURITY": "Previdência",
    "OTHER": "Outro",
}


def _investimento(i):
    return {
        "id": i.get("id"),
        "nome": (i.get("name") or "Investimento").strip(),
        "tipo": _TIPOS_INVESTIMENTO.get(i.get("type"), "Investimento"),
        # balance é o líquido (já descontado IR e IOF): é o que cai na
        # conta se resgatar hoje, então é o que entra no patrimônio.
        "saldo": _num(i.get("balance")),
        "aplicado": _num(i.get("amountOriginal")),
        "vencimento": _iso(_data(i.get("dueDate"))),
    }


def _investimento_ativo(i) -> bool:
    """Posição resgatada continua na lista da Pluggy com saldo zero."""
    return (i.get("status") or "ACTIVE") != "TOTAL_WITHDRAWAL" and (i.get("balance") or 0) > 0


def _e_saida(t, credito: bool) -> bool:
    """Se o lançamento tira dinheiro do bolso.

    `type` é o campo confiável. O sinal do valor fica de reserva e muda de
    sentido conforme a conta: no cartão, valor positivo é compra; na conta
    corrente, é dinheiro entrando.
    """
    tipo = (t.get("type") or "").upper()
    if tipo in ("DEBIT", "CREDIT"):
        return tipo == "DEBIT"
    valor = t.get("amount") or 0
    return valor > 0 if credito else valor < 0


def _valor(t) -> Decimal:
    v = t.get("amountInAccountCurrency")
    if v is None:
        v = t.get("amount") or 0
    return abs(Decimal(str(v)))


def _cartao(c):
    cd = c.get("creditData") or {}
    fechamento = _data(cd.get("balanceCloseDate"))
    vencimento = _data(cd.get("balanceDueDate"))

    faturas = sorted(
        _todas("/bills", {"accountId": c["id"]}),
        key=lambda f: f.get("dueDate") or "",
        reverse=True,
    )
    desde = date.today() - timedelta(days=config.PLUGGY_DIAS_PARCELAS)
    recentes = _transacoes_da_conta(c["id"], desde)

    limite = cd.get("creditLimit")
    livre = cd.get("availableCreditLimit")
    return {
        "id": c.get("id"),
        "nome": _nome_conta(c),
        "numero": c.get("number"),
        "bandeira": cd.get("brand"),
        "faturaAtual": {
            "valor": _num(c.get("balance")),
            "fechamento": _iso(fechamento),
            "vencimento": _iso(vencimento),
            "pagamentoMinimo": _num(cd.get("minimumPayment")),
        },
        "limite": _num(limite),
        "disponivel": _num(livre),
        "faturasPassadas": [
            {
                "id": f.get("id"),
                "vencimento": _iso(_data(f.get("dueDate"))),
                "valor": _num(f.get("totalAmount")),
                "pagamentoMinimo": _num(f.get("minimumPaymentAmount")),
            }
            for f in faturas[:12]
        ],
        "faturasFuturas": _projetar_parcelas(recentes, faturas, fechamento, vencimento),
    }


# "parc 03 10", "parcela 3 de 10", "03 10" (já normalizado, sem a barra).
_MARCA_PARCELA = re.compile(r"\b(parc(ela)?\s*)?\d{1,2}\s+(de\s+)?\d{1,2}\b|\bparc(ela)?\b")


def _projetar_parcelas(transacoes, faturas, fechamento, vencimento):
    """Faturas futuras a partir das compras parceladas.

    O Open Finance não entrega fatura futura pronta: entrega cada parcela
    só quando ela entra numa fatura. A projeção pega a parcela mais recente
    de cada compra (3/10, por exemplo) e espalha as que faltam pelos meses
    seguintes. Fica de fora o que ainda não existe: compra nova, juros e
    anuidade. Por isso a tela chama de projeção, não de fatura.
    """
    venc_da_fatura = {f.get("id"): _data(f.get("dueDate")) for f in faturas}
    dia_fech = fechamento.day if fechamento else None
    folga = (vencimento - fechamento).days if fechamento and vencimento else None

    compras = {}
    for t in transacoes:
        meta = t.get("creditCardMetadata") or {}
        try:
            n, total = int(meta.get("installmentNumber") or 0), int(meta.get("totalInstallments") or 0)
        except (TypeError, ValueError):
            continue
        if n < 1 or total <= n or not _e_saida(t, credito=True):
            continue

        # Em qual vencimento esta parcela cai. Com billId é exato; sem ele,
        # deduz pelo dia de fechamento do cartão (compra no dia do
        # fechamento ou depois já vai para a fatura seguinte).
        base = venc_da_fatura.get(meta.get("billId"))
        if base is None:
            d = _data(t.get("date"))
            if not d:
                continue
            if dia_fech and folga is not None:
                fech = _no_dia(d.year, d.month, dia_fech)
                if d >= fech:
                    fech = _somar_meses(fech, 1, dia_fech)
                base = fech + timedelta(days=folga)
            else:
                base = _somar_meses(d, 1)

        valor = _valor(t)
        descricao = (t.get("description") or "Compra parcelada").strip()
        # A mesma compra aparece uma vez por parcela. A chave junta todas e
        # fica só com a parcela mais adiantada. Muito banco escreve o
        # contador na descrição ("LOJA PARC 03/10"), e sem tirar isso cada
        # parcela viraria uma compra diferente e a projeção dobraria.
        origem = meta.get("purchaseDate") or _somar_meses(base, -n).strftime("%Y-%m")
        nome_base = _MARCA_PARCELA.sub(" ", normalizar(descricao)).strip()
        chave = (nome_base, total, valor, str(origem)[:10])
        if chave not in compras or n > compras[chave]["n"]:
            compras[chave] = {"n": n, "total": total, "valor": valor, "base": base, "descricao": descricao}

    # O que vence até a fatura atual já está somado no saldo dela.
    corte = vencimento or date.today()
    meses = {}
    for c in compras.values():
        for j in range(1, c["total"] - c["n"] + 1):
            venc = _somar_meses(c["base"], j)
            if venc <= corte:
                continue
            m = meses.setdefault(venc.strftime("%Y-%m"), {"vencimento": venc, "valor": Decimal(0), "parcelas": []})
            m["valor"] += c["valor"]
            m["parcelas"].append({
                "descricao": c["descricao"],
                "parcela": f"{c['n'] + j}/{c['total']}",
                "valor": _num(c["valor"]),
            })

    return [
        {
            "mes": ym,
            "vencimento": _iso(m["vencimento"]),
            "valor": _num(m["valor"]),
            "parcelas": sorted(m["parcelas"], key=lambda p: -p["valor"]),
        }
        for ym, m in sorted(meses.items())[:12]
    ]


# ── Funções públicas ─────────────────────────────────────────
def sem_credencial():
    return (
        "Open Finance não configurado. Defina FIN_PLUGGY_CLIENT_ID e "
        "FIN_PLUGGY_CLIENT_SECRET com as credenciais do painel da Pluggy."
    )


def conferir(item_id) -> tuple[dict | None, str | None]:
    """Confere se o id existe na Pluggy antes de gravar a conexão."""
    if not disponivel():
        return None, sem_credencial()
    if not ID_VALIDO.match(str(item_id or "")):
        return None, "Esse id não tem o formato de uma conexão da Pluggy."
    try:
        return _item(_chamar("GET", f"/items/{item_id}")), None
    except _FalhaPluggy as e:
        return None, str(e)
    except Exception:  # noqa: BLE001 - de propósito: nada sai daqui
        return None, "Não consegui consultar a Pluggy agora."


def panorama(item_id) -> tuple[dict | None, str | None]:
    """Instituição, contas com saldo, cartões com faturas e investimentos
    de uma conexão."""
    if not disponivel():
        return None, sem_credencial()
    if not ID_VALIDO.match(str(item_id or "")):
        return None, "Id de conexão inválido."

    em_cache = _do_cache(item_id)
    if em_cache:
        return em_cache, None

    try:
        item = _item(_chamar("GET", f"/items/{item_id}"))
        contas = _todas("/accounts", {"itemId": item_id})
        investimentos = _todas("/investments", {"itemId": item_id})
        dados = {
            **item,
            "contas": [_conta(c) for c in contas if c.get("type") != "CREDIT"],
            "cartoes": [_cartao(c) for c in contas if c.get("type") == "CREDIT"],
            "investimentos": [_investimento(i) for i in investimentos if _investimento_ativo(i)],
        }
    except _FalhaPluggy as e:
        return None, str(e)
    except Exception:  # noqa: BLE001
        return None, "Não consegui ler essa conexão agora."

    # Durante a sincronização os números estão mudando: guardar em cache
    # faria a tela mostrar o meio do caminho por um minuto inteiro.
    if item["status"] != "UPDATING":
        _guardar(item_id, dados)
    return dados, None


def atualizar(item_id) -> str | None:
    """Pede à Pluggy que busque os dados no banco agora. Devolve o aviso."""
    if not disponivel():
        return sem_credencial()
    if not ID_VALIDO.match(str(item_id or "")):
        return "Id de conexão inválido."
    _cache.pop(item_id, None)
    try:
        _chamar("PATCH", f"/items/{item_id}", corpo={})
        return None
    except _FalhaPluggy as e:
        return str(e)
    except Exception:  # noqa: BLE001
        return "Não consegui pedir a atualização agora."


def token_do_widget(usuario_id, item_id=None) -> tuple[str | None, str | None]:
    """Token curto para o widget Pluggy Connect abrir no navegador.

    É o único segredo que vai para o front, e de propósito: ele só serve
    para abrir o widget por 30 minutos, não lê dado nenhum. O clientSecret
    continua só aqui. Com `item_id`, o widget abre no modo de reconectar
    aquela conexão em vez de criar outra.
    """
    if not disponivel():
        return None, sem_credencial()
    corpo = {"options": {"clientUserId": str(usuario_id)}}
    if item_id:
        if not ID_VALIDO.match(str(item_id)):
            return None, "Id de conexão inválido."
        corpo["itemId"] = item_id
    try:
        r = _chamar("POST", "/connect_token", corpo=corpo)
    except _FalhaPluggy as e:
        return None, str(e)
    except Exception:  # noqa: BLE001
        return None, "Não consegui abrir a conexão com a Pluggy agora."
    if not r.get("accessToken"):
        return None, "A Pluggy não devolveu o token de conexão."
    return r["accessToken"], None


def esquecer(item_id):
    _cache.pop(item_id, None)


# Categorias da Pluggy (vêm em inglês) para o vocabulário do app. O que não
# estiver aqui passa com o nome original, sem sumir.
_CATEGORIAS = {
    "income": "Renda", "salary": "Salário", "retirement": "Aposentadoria",
    "entrepreneurial activities": "Renda", "government aid": "Benefícios",
    "non-recurring income": "Renda extra",
    "loans and financing": "Empréstimos", "financing": "Financiamento",
    "real estate financing": "Financiamento", "vehicle financing": "Financiamento",
    "student loan": "Empréstimos", "late payment and overdraft costs": "Juros e multas",
    "interests charged": "Juros e multas",
    "investments": "Investimentos", "automatic investment": "Investimentos",
    "fixed income": "Investimentos", "mutual funds": "Investimentos",
    "variable income": "Investimentos", "pension": "Previdência",
    "proceeds interests and dividends": "Rendimentos",
    "transfers": "Transferências", "transfer - pix": "Transferências",
    "transfer - ted": "Transferências", "transfer - foreign exchange": "Câmbio",
    "services": "Serviços", "telecommunications": "Telefone e internet",
    "internet": "Telefone e internet", "mobile": "Telefone e internet", "tv": "Assinaturas",
    "education": "Educação", "online courses": "Educação", "university": "Educação",
    "school": "Educação", "kindergarten": "Educação",
    "wellness and fitness": "Saúde e bem-estar", "gyms and fitness centers": "Academia",
    "sports practice": "Academia", "wellness": "Saúde e bem-estar",
    "tickets": "Lazer", "stadiums and arenas": "Lazer", "landmarks and museums": "Lazer",
    "cinema, theater and concerts": "Lazer", "leisure": "Lazer",
    "shopping": "Compras", "online shopping": "Compras", "electronics": "Compras",
    "clothing": "Vestuário", "kids and toys": "Compras", "bookstore": "Compras",
    "pet supplies and vet": "Pets", "office supplies": "Compras",
    "digital services": "Assinaturas", "gaming": "Assinaturas",
    "video streaming": "Assinaturas", "music streaming": "Assinaturas",
    "groceries": "Mercado", "food and drinks": "Alimentação", "eating out": "Restaurantes",
    "food delivery": "Delivery",
    "travel": "Viagem", "airport and airlines": "Viagem", "accommodation": "Viagem",
    "mileage programs": "Viagem", "bus tickets": "Viagem",
    "donations": "Doações", "gambling": "Apostas", "lottery": "Apostas", "online bet": "Apostas",
    "taxes": "Impostos", "income taxes": "Impostos", "tax on financial operations": "Impostos",
    "bank fees": "Tarifas", "account fees": "Tarifas",
    "wire transfer fees and atm fees": "Tarifas", "credit card fees": "Tarifas",
    "housing": "Moradia", "rent": "Aluguel", "utilities": "Contas da casa",
    "water": "Contas da casa", "electricity": "Contas da casa", "gas": "Contas da casa",
    "houseware": "Casa", "urban land and building tax": "Impostos",
    "healthcare": "Saúde", "dentist": "Saúde", "pharmacy": "Farmácia",
    "optometry": "Saúde", "hospital clinics and labs": "Saúde",
    "transportation": "Transporte", "taxi and ride-hailing": "Transporte",
    "public transportation": "Transporte", "car rental": "Transporte", "bicycle": "Transporte",
    "automotive": "Carro", "gas stations": "Combustível", "parking": "Carro",
    "tolls and in vehicle payment": "Carro", "vehicle ownership taxes and fees": "Impostos",
    "vehicle maintenance": "Carro", "traffic tickets": "Carro",
    "insurance": "Seguros", "life insurance": "Seguros", "home insurance": "Seguros",
    "health insurance": "Plano de saúde", "vehicle insurance": "Seguros",
    "other": "Outros",
    "loans": "Empréstimos", "credit card payment": "Pagamento de fatura",
    "cashback": "Cashback", "transfer - internal": "Transferências",
}

_PAGAMENTO_FATURA = re.compile(
    r"pagamento.{0,20}(fatura|cartao)|pgto.{0,12}(fat|cart)|fatura.{0,20}paga|pag fat"
)


def _categoria(t) -> str:
    original = (t.get("category") or "").strip()
    return (_CATEGORIAS.get(original.lower()) or original or "Sem categoria")[:80]


def _motivo_para_ignorar(t, credito: bool, tem_cartao: bool) -> str | None:
    """Por que um lançamento NÃO vira transação no app.

    O risco aqui é contar o mesmo dinheiro duas vezes:
    * A compra no cartão já entra como despesa. O pagamento da fatura na
      conta corrente seria a mesma despesa de novo, então sai, mas só se
      algum cartão estiver conectado; sem cartão, ele é o único registro.
    * O pagamento chegando no cartão não é renda, sai sempre.
    * Transferência entre contas do próprio CPF não é entrada nem saída.
    * Lançamento pendente muda de id quando compensa e duplicaria depois.
    """
    if (t.get("status") or "POSTED").upper() == "PENDING":
        return "pendentes"
    if _valor(t) <= 0:
        return "semValor"

    categoria = (t.get("category") or "").lower()
    pagamento = "credit card payment" in categoria or _PAGAMENTO_FATURA.search(
        normalizar(t.get("description"))
    )
    saida = _e_saida(t, credito)
    # Crédito no cartão só é estorno ou cashback quando o banco diz isso.
    # Pagamento chega com textos que nenhuma regex cobre inteira ("PAGAMENTO
    # COM SALDO", "Inclusao de Pagamento Ciclo Corrente") e categoria de
    # transferência, e era contado como renda.
    if credito and not saida and (
        pagamento or categoria.startswith("transfer") or "pagamento" in normalizar(t.get("description"))
    ):
        return "pagamentoFatura"
    if pagamento and not credito and saida and tem_cartao:
        return "pagamentoFatura"
    # Parcela de parcelamento de fatura cobrada no cartão: as compras
    # daquela fatura já entraram uma a uma.
    if credito and saida and "credit card payment" in categoria:
        return "pagamentoFatura"
    if "same person" in categoria or categoria == "transfer - internal":
        return "transferencias"
    return None


# Dias de folga entre os dois lados de um movimento interno: o débito numa
# conta e o crédito na outra nem sempre compensam no mesmo dia.
_FOLGA_PAR_DIAS = 5


def _descartar_pares(brutas, motivos):
    """Acha o outro lado do pagamento de fatura e descarta também.

    O lado do cartão vem marcado, o da conta nem sempre: há banco que manda
    a saída do pagamento só com o próprio nome e categoria "Loans", e ela
    contava como despesa em cima das compras do cartão. O par é
    o lançamento de direção oposta, mesmo valor, em OUTRA conta conectada,
    em até _FOLGA_PAR_DIAS. Altera `motivos` no lugar e devolve quem casou
    com quem ({índice: índice do par}, nos dois sentidos), que a tela de
    conferência mostra ao lado de cada descarte.

    Duas passadas, e a ordem importa. Quando os DOIS lados já vêm marcados
    (de um banco para outro, "same person" nas duas pontas), eles precisam
    se casar entre si primeiro; senão a ponta marcada sai procurando par
    livre e leva junto uma despesa de verdade de mesmo valor (um imposto,
    por exemplo).
    """
    def chave(k):
        _, credito, t = brutas[k]
        return _valor(t), _e_saida(t, credito)

    def melhor_par(k, opcoes):
        """O candidato mais próximo na data, preferindo o outro tipo de
        conta (o par de um cartão é uma conta, e o contrário)."""
        conta, credito, t = brutas[k]
        d = _data(t.get("date"))
        melhores = []
        for j in opcoes:
            conta_j, credito_j, t_j = brutas[j]
            d_j = _data(t_j.get("date"))
            if j in usados or conta_j["id"] == conta["id"] or not d or not d_j:
                continue
            dias = abs((d_j - d).days)
            if dias <= _FOLGA_PAR_DIAS:
                melhores.append((credito_j == credito, dias, j))
        return min(melhores)[2] if melhores else None

    marcadas, livres = {}, {}
    for k, m in enumerate(motivos):
        if m in ("transferencias", "pagamentoFatura"):
            marcadas.setdefault(chave(k), []).append(k)
        elif m is None:
            livres.setdefault(chave(k), []).append(k)

    usados = set()
    pares = {}
    sozinhas = []
    for k in [k for lista in marcadas.values() for k in lista]:
        if k in usados:
            continue
        valor, saida = chave(k)
        j = melhor_par(k, marcadas.get((valor, not saida), []))
        if j is None:
            sozinhas.append(k)
        else:
            usados.update((k, j))
            pares[k], pares[j] = j, k

    # Só o pagamento recebido no cartão procura par livre: ele sempre sai
    # de alguma conta, e nos dados reais o par certo apareceu em todos os
    # casos. Transferência "same person"/"internal" sozinha NÃO procura: o
    # outro lado costuma estar numa conta não conectada, e a busca pegava
    # despesa de verdade de mesmo valor (imposto, boleto).
    for k in sozinhas:
        conta, credito, t = brutas[k]
        m = motivos[k]
        if not (m == "pagamentoFatura" and credito and not _e_saida(t, credito)):
            continue
        valor, saida = chave(k)
        j = melhor_par(k, livres.get((valor, not saida), []))
        if j is not None:
            usados.update((k, j))
            pares[k], pares[j] = j, k
            motivos[j] = m
    return pares


def _lancamento(t, credito):
    """Transação da Pluggy no formato da tabela `transacoes`."""
    return {
        "origem_id": str(t["id"])[:64],
        "data": _data(t.get("date")),
        "nome": (t.get("description") or "").strip()[:160] or "Sem descrição",
        "valor": _valor(t),
        "natureza": "despesa" if _e_saida(t, credito) else "receita",
        "categoria": _categoria(t),
        "meio": "cartao" if credito else "conta",
    }


def transacoes(item_ids, desde: date) -> tuple[list[dict], dict, list[dict], str | None]:
    """Lançamentos das conexões, prontos para a tabela `transacoes`.

    @return (lançamentos, contagem do que foi deixado de fora por motivo,
             descartados, aviso). Os descartados servem para tirar do banco
             o que uma importação antiga deixou entrar antes de a regra
             existir, e para a tela de conferência: cada um vem no formato
             de um lançamento, mais `motivo`, `conta` e o `par` (id de
             origem do outro lado, quando a regra casou os dois). Pendente
             não entra: muda de id quando compensa. Se qualquer conexão
             falhar, a lista volta vazia: é melhor não importar nada do que
             importar metade sem avisar.
    """
    ignorados = {"pendentes": 0, "pagamentoFatura": 0, "transferencias": 0, "semValor": 0}
    if not disponivel():
        return [], ignorados, [], sem_credencial()

    try:
        contas = [c for i in item_ids for c in _todas("/accounts", {"itemId": i})]
        tem_cartao = any(c.get("type") == "CREDIT" for c in contas)

        brutas = []
        for c in contas:
            credito = c.get("type") == "CREDIT"
            brutas += [(c, credito, t) for t in _transacoes_da_conta(c["id"], desde, date.today())]

        motivos = [_motivo_para_ignorar(t, credito, tem_cartao) for _, credito, t in brutas]
        pares = _descartar_pares(brutas, motivos)

        saida, descartados = [], []
        for k, ((c, credito, t), motivo) in enumerate(zip(brutas, motivos)):
            if motivo:
                ignorados[motivo] += 1
                if t.get("id") and motivo != "pendentes":
                    j = pares.get(k)
                    par = brutas[j][2].get("id") if j is not None else None
                    descartados.append({
                        **_lancamento(t, credito),
                        "motivo": motivo,
                        "conta": _nome_conta(c)[:120],
                        "par": str(par)[:64] if par else None,
                    })
                continue
            if not _data(t.get("date")) or not t.get("id"):
                continue
            saida.append(_lancamento(t, credito))
        return saida, ignorados, descartados, None
    except _FalhaPluggy as e:
        return [], ignorados, [], str(e)
    except Exception:  # noqa: BLE001
        return [], ignorados, [], "Não consegui ler as transações agora."
