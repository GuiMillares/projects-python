"""Configuração da API. Tudo sobrescrevível por variável de ambiente."""

import os

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
