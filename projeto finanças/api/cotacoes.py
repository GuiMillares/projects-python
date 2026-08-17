"""Cotação da B3 via brapi.dev.

Só a biblioteca padrão: `urllib.request` resolve, e é uma dependência a
menos para instalar num app que já roda offline no resto.

REGRA DESTE MÓDULO: ele nunca levanta exceção para quem chama. Cotação é
enfeite sobre um dado que já existe no banco; se a brapi cair, a tela de
investimentos tem que continuar mostrando quantidade e preço médio. Por
isso `buscar` devolve sempre uma tupla (cotações, aviso) e o aviso é texto
para exibir, não erro para estourar.

Sobre o token (config.BRAPI_TOKEN):
  COM token  -> um request só, com todos os tickers de uma vez.
  SEM token  -> a brapi aceita UM ticker por request e recusa a lista com
                401 MISSING_TOKEN. O código cai para requests individuais,
                limitados a BRAPI_MAX_SEM_TOKEN para não martelar a API.
"""

import json
import time
import urllib.error
import urllib.parse
import urllib.request

import config

# ticker -> (momento_em_que_expira, dados)
_cache: dict[str, tuple[float, dict]] = {}


def _do_cache(ticker: str):
    achado = _cache.get(ticker)
    if not achado:
        return None
    expira, dados = achado
    if time.time() > expira:
        _cache.pop(ticker, None)
        return None
    return dados


def _guardar(ticker: str, dados: dict):
    _cache[ticker] = (time.time() + config.BRAPI_CACHE_SEGUNDOS, dados)


def _traduzir(res: dict) -> dict:
    """Fica só com o que a tela usa; o payload da brapi tem dezenas de campos."""
    return {
        "ticker": res.get("symbol"),
        "preco": res.get("regularMarketPrice"),
        "variacaoDia": res.get("regularMarketChange"),
        "variacaoDiaPct": res.get("regularMarketChangePercent"),
        "nome": res.get("longName") or res.get("shortName"),
        "moeda": res.get("currency") or "BRL",
        "atualizadoEm": res.get("regularMarketTime"),
    }


def _chamar(tickers: list[str]) -> list[dict]:
    """Um request à brapi. Levanta em caso de falha; quem trata é `buscar`."""
    url = f"{config.BRAPI_BASE}/quote/{urllib.parse.quote(','.join(tickers))}"
    if config.BRAPI_TOKEN:
        url += f"?token={urllib.parse.quote(config.BRAPI_TOKEN)}"

    req = urllib.request.Request(url, headers={"User-Agent": "painel-financas/1.0"})
    with urllib.request.urlopen(req, timeout=config.BRAPI_TIMEOUT) as resp:
        corpo = json.loads(resp.read().decode("utf-8"))
    return corpo.get("results") or []


def _mensagem_de_erro(e: Exception) -> str:
    if isinstance(e, urllib.error.HTTPError):
        if e.code == 401:
            return (
                "A brapi recusou a consulta por falta de token. "
                "Gere um gratuito em brapi.dev e configure FIN_BRAPI_TOKEN."
            )
        if e.code == 429:
            return "Limite de consultas da brapi atingido. Tente de novo em alguns minutos."
        return f"A brapi respondeu com erro {e.code}."
    if isinstance(e, urllib.error.URLError):
        return "Sem conexão com a brapi. Cotações podem estar desatualizadas."
    return "Não foi possível consultar as cotações agora."


def buscar(tickers) -> tuple[dict, str | None]:
    """Cotações dos tickers pedidos.

    @return ({ticker: dados}, aviso_ou_None). O dicionário pode vir parcial
            ou vazio: cada ticker sem cotação simplesmente não aparece nele,
            e a tela mostra a posição sem os números de mercado.
    """
    pedidos = sorted({str(t).strip().upper() for t in tickers if str(t).strip()})
    if not pedidos:
        return {}, None

    encontrados: dict[str, dict] = {}
    faltando: list[str] = []
    for t in pedidos:
        em_cache = _do_cache(t)
        if em_cache:
            encontrados[t] = em_cache
        else:
            faltando.append(t)

    if not faltando:
        return encontrados, None

    aviso = None
    if config.BRAPI_TOKEN:
        lotes = [faltando]
    else:
        # Sem token a lista é recusada, então vai um por vez. O corte evita
        # transformar uma carteira grande numa rajada de requests.
        lotes = [[t] for t in faltando[: config.BRAPI_MAX_SEM_TOKEN]]
        if len(faltando) > config.BRAPI_MAX_SEM_TOKEN:
            aviso = (
                f"Sem token da brapi só consigo {config.BRAPI_MAX_SEM_TOKEN} "
                "cotações por vez. Configure FIN_BRAPI_TOKEN para buscar todas."
            )

    ultimo_erro = None
    for lote in lotes:
        # Cada lote é tratado por si: um ticker inexistente no meio da
        # carteira não pode derrubar a cotação dos outros.
        try:
            for res in _chamar(lote):
                dados = _traduzir(res)
                if dados["ticker"] and dados["preco"] is not None:
                    encontrados[dados["ticker"]] = dados
                    _guardar(dados["ticker"], dados)
        except Exception as e:  # noqa: BLE001 - de propósito: nada sai daqui
            ultimo_erro = e

    sem_resposta = [t for t in faltando if t not in encontrados]

    if sem_resposta and not aviso:
        if len(sem_resposta) == len(pedidos):
            # Nenhuma cotação veio: é problema geral (rede, token, limite).
            aviso = _mensagem_de_erro(ultimo_erro) if ultimo_erro else (
                "Não recebi cotação para nenhum ativo da carteira."
            )
        else:
            # Parte funcionou. Dizer "falta token" aqui seria mentira, já
            # que as outras vieram: o provável é ticker inexistente.
            nomes = ", ".join(sem_resposta[:4])
            resto = f" e mais {len(sem_resposta) - 4}" if len(sem_resposta) > 4 else ""
            aviso = (
                f"Sem cotação para {nomes}{resto}. Confira se o ticker existe na B3"
                + ("." if config.BRAPI_TOKEN else " ou configure FIN_BRAPI_TOKEN.")
            )

    return encontrados, aviso
