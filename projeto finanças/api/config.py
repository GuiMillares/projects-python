"""Configuração da API. Tudo sobrescrevível por variável de ambiente."""

import os
from pathlib import Path


def _carregar_env(caminho: Path):
    """Lê o .env da raiz do projeto (CHAVE=valor, # comenta).

    Leitor próprio em vez de python-dotenv: são dez linhas e uma dependência
    a menos. Variável que já existe no ambiente ganha do arquivo, então quem
    configurou pelo Windows (setx) não é atropelado.
    """
    if not caminho.is_file():
        return
    for linha in caminho.read_text(encoding="utf-8-sig").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        os.environ.setdefault(chave.strip(), valor.strip().strip("\"'"))


# O .env fica em "projeto finanças/", um nível acima de api/, e está no
# .gitignore: é onde moram os segredos que não vão para o repositório.
_carregar_env(Path(__file__).resolve().parent.parent / ".env")

# ── Banco (Laragon) ──────────────────────────────────────────
# O MySQL do Laragon vem com root sem senha e escutando só em
# localhost. Como a API também só escuta em 127.0.0.1, o banco
# nunca fica exposto à rede.
DB_HOST = os.getenv("FIN_DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("FIN_DB_PORT", "3306"))
DB_USER = os.getenv("FIN_DB_USER", "root")
DB_PASS = os.getenv("FIN_DB_PASS", "")
DB_NAME = os.getenv("FIN_DB_NAME", "local_finance")

# ── API ──────────────────────────────────────────────────────
# 127.0.0.1 e não 0.0.0.0: o webview do Tauri roda na mesma
# máquina, não há motivo para aceitar conexão de fora.
API_HOST = os.getenv("FIN_API_HOST", "127.0.0.1")
API_PORT = int(os.getenv("FIN_API_PORT", "8756"))

# Origens que podem falar com a API. `tauri://localhost` é a origem
# do webview no app empacotado; as portas 1420/1421 são o Vite.
ORIGENS_PERMITIDAS = {
    "http://localhost:1420",
    "http://127.0.0.1:1420",
    "http://localhost:1421",
    "tauri://localhost",
    "https://tauri.localhost",
}

# ── Sessão ───────────────────────────────────────────────────
SESSAO_HORAS = int(os.getenv("FIN_SESSAO_HORAS", "12"))

# Sessão só com senha (2FA pendente) morre rápido: é uma janela de
# passagem, não um estado em que se fica.
SESSAO_PARCIAL_MINUTOS = 10

# ── Anti-força-bruta ─────────────────────────────────────────
MAX_TENTATIVAS = 5
BLOQUEIO_MINUTOS = 15

EMISSOR_TOTP = os.getenv("FIN_TOTP_EMISSOR", "Financas")

# ── LGPD ─────────────────────────────────────────────────────
# Quem responde pelos dados desta instalação (o controlador) e como falar
# com essa pessoa. Aparecem na política de privacidade. Ficam no .env, e
# não no código, porque o repositório é público e cada instalação tem o
# seu responsável.
CONTROLADOR_NOME = os.getenv("FIN_CONTROLADOR_NOME", "").strip()
CONTROLADOR_CONTATO = os.getenv("FIN_CONTROLADOR_CONTATO", "").strip()

# ── Cotações (brapi.dev) ─────────────────────────────────────
BRAPI_BASE = os.getenv("FIN_BRAPI_BASE", "https://brapi.dev/api")

# Token do plano gratuito (brapi.dev). Sem ele a API só aceita UM ticker
# por request e recusa a lista com 401; ver cotacoes.py.
BRAPI_TOKEN = os.getenv("FIN_BRAPI_TOKEN", "").strip()

BRAPI_TIMEOUT = int(os.getenv("FIN_BRAPI_TIMEOUT", "8"))

# Cotação em cache por um minuto. Sem isto, cada F5 na tela vira uma
# rodada de requests e o limite gratuito acaba rápido.
BRAPI_CACHE_SEGUNDOS = int(os.getenv("FIN_BRAPI_CACHE", "60"))

# Teto de requests individuais quando não há token configurado.
BRAPI_MAX_SEM_TOKEN = int(os.getenv("FIN_BRAPI_MAX_SEM_TOKEN", "6"))

# ── Geração de subtarefas por IA (api/ia.py) ─────────────────
# A CHAVE NÃO MORA AQUI. O SDK do Google lê GEMINI_API_KEY do ambiente
# sozinho; este arquivo só guarda o que é ajuste, não segredo.
#
# Modelos possíveis, do mais barato ao mais capaz:
#   gemini-3.5-flash-lite   o mais rápido e econômico
#   gemini-3.5-flash        padrão: equilíbrio para passos que a pessoa lê
#   gemini-3.7-flash        mais recente, melhor julgamento
# Trocar não exige mexer em código, só na variável de ambiente.
IA_MODELO = os.getenv("FIN_IA_MODELO", "gemini-3.5-flash")

# Timeout curto: a chamada acontece dentro de um clique na tela, e o
# padrão do SDK (10 minutos) deixaria a interface pendurada.
IA_TIMEOUT = int(os.getenv("FIN_IA_TIMEOUT", "60"))

# Teto de subtarefas aceitas por meta, independente do que a IA devolver.
IA_MAX_SUBTAREFAS = int(os.getenv("FIN_IA_MAX_SUBTAREFAS", "8"))

# Quanto o modelo pensa antes de escrever (MINIMAL, LOW, MEDIUM, HIGH).
# MEDIUM deixa os passos sob medida para a meta; volte para LOW se o custo
# começar a pesar.
IA_THINKING = os.getenv("FIN_IA_THINKING", "MEDIUM")

# ── Open Finance (Pluggy, via Meu Pluggy) ────────────────────
# As credenciais vêm do painel de desenvolvedor da Pluggy e moram só no
# ambiente, igual ao token da brapi. Sem elas a tela de Contas abre e
# explica o que falta.
PLUGGY_BASE = os.getenv("FIN_PLUGGY_BASE", "https://api.pluggy.ai")
PLUGGY_CLIENT_ID = os.getenv("FIN_PLUGGY_CLIENT_ID", "").strip()
PLUGGY_CLIENT_SECRET = os.getenv("FIN_PLUGGY_CLIENT_SECRET", "").strip()

PLUGGY_TIMEOUT = int(os.getenv("FIN_PLUGGY_TIMEOUT", "20"))

# Saldo e fatura ficam em cache por um minuto: a Pluggy só muda esses
# números quando sincroniza com o banco, então reler a cada F5 não traz
# nada novo e gasta cota.
PLUGGY_CACHE_SEGUNDOS = int(os.getenv("FIN_PLUGGY_CACHE", "60"))

# Janela de compras lida para projetar as faturas futuras. A parcela mais
# recente de cada compra parcelada está sempre na fatura atual ou na
# anterior, então pouco mais de dois meses já cobre.
PLUGGY_DIAS_PARCELAS = int(os.getenv("FIN_PLUGGY_DIAS_PARCELAS", "70"))

# Teto de páginas por consulta, para uma conta com histórico enorme não
# virar uma rajada de requests.
PLUGGY_MAX_PAGINAS = int(os.getenv("FIN_PLUGGY_MAX_PAGINAS", "30"))
