"""Quebra de metas em subtarefas usando a API do Google Gemini.

=============================================================================
ESTE É O ÚNICO ARQUIVO DO PROJETO QUE FALA COM UM MODELO DE LINGUAGEM.
=============================================================================

CONFIGURAÇÃO NECESSÁRIA
-----------------------
Uma variável de ambiente com a chave da API:

    export GEMINI_API_KEY=AIza...                # Git Bash
    $env:GEMINI_API_KEY = "AIza..."              # PowerShell (sessão atual)
    [Environment]::SetEnvironmentVariable("GEMINI_API_KEY", "AIza...", "User")

Gere a chave em aistudio.google.com/apikey. O tier gratuito não pede cartão
de crédito.

O SDK também aceita GOOGLE_API_KEY, e ela tem precedência se as duas
estiverem definidas. Prefira GEMINI_API_KEY: GOOGLE_API_KEY é um nome
genérico do ecossistema Google e pode colidir com outra ferramenta na mesma
máquina.

A chave é lida do ambiente pelo próprio SDK, e é por isso que o cliente é
construído sem argumentos abaixo: NENHUMA credencial aparece neste código,
nem em `config.py`, nem no banco. Se um dia aparecer uma chave literal em
qualquer arquivo do repositório, foi vazamento, não configuração.

Lembre da pegadinha do Windows (ver contexto.txt seção 7): variável definida
com escopo "User" só é enxergada por processos abertos DEPOIS da definição.

SEM A CHAVE, NADA QUEBRA
------------------------
Mesmo contrato de `cotacoes.py`: esta função nunca levanta exceção para
quem chama. Devolve `(subtarefas, aviso)`. Sem chave configurada, ou com a
API fora do ar, a lista volta vazia e o aviso explica o motivo; a meta é
criada do mesmo jeito e o usuário escreve os passos à mão.
"""

import json
import os

import config

# O import do SDK fica dentro das funções: `google-genai` é a dependência
# mais pesada do projeto, e quem não usa a geração por IA não deveria pagar
# o custo de importá-la a cada boot da API.

# Schema da resposta. Com `response_json_schema` o retorno é garantidamente
# um JSON válido nesta forma, o que dispensa regex, retry de parse e o
# "responda APENAS com JSON" no prompt.
#
# `xp` é enum e não faixa numérica: além de o schema do Gemini não cobrir
# minimum/maximum, o enum força valores redondos em vez de 13, 17, 22.
#
# Sem `additionalProperties: false` de propósito: o suporte a esse campo
# varia entre versões da API, e ele não faz falta aqui porque a
# normalização abaixo ignora qualquer campo extra de qualquer jeito.
ESQUEMA_SUBTAREFAS = {
    "type": "object",
    "properties": {
        "subtarefas": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "titulo": {
                        "type": "string",
                        "description": "Passo concreto, no imperativo, começando por um verbo.",
                    },
                    "xp": {
                        "type": "integer",
                        "enum": [5, 10, 15, 20, 25, 30],
                        "description": "Esforço do passo: 5 é trivial, 30 é o mais pesado da meta.",
                    },
                },
                "required": ["titulo", "xp"],
            },
        }
    },
    "required": ["subtarefas"],
}

INSTRUCOES = """Você quebra metas pessoais em passos concretos para um app de finanças pessoais brasileiro.

Devolva de 4 a 7 subtarefas, na ordem em que devem ser feitas. Cada uma precisa ser uma ação verificável que a pessoa consegue marcar como feita num sábado à tarde, não um objetivo vago.

Antes de escrever, pense no caminho completo desta meta específica: o que destrava o quê, qual é o primeiro obstáculo real, o que costuma fazer as pessoas desistirem no meio. Os passos devem contar essa história em sequência, do primeiro movimento ao arremate, e fazer sentido só para ESTA meta. Se os mesmos passos serviriam para qualquer outra meta, estão genéricos demais: refaça.

Cada passo cobre uma frente diferente do caminho. É proibido devolver dois passos que sejam variações um do outro ("pesquisar corretoras" e "comparar corretoras" são o mesmo passo) e é proibido repetir ou parafrasear qualquer passo que já exista na meta, quando a lista deles for fornecida. Nesse caso, gere apenas o que falta para completar o caminho, e devolva menos passos se ele já estiver quase coberto.

Escreva no imperativo, começando por um verbo, em português do Brasil. Máximo 90 caracteres por subtarefa.

Prefira passos que a pessoa controla. "Pesquisar três corretoras e abrir conta numa" é uma subtarefa; "conseguir um aumento" não é.

Se a meta tem valor e prazo, faça a conta e coloque números reais nos passos: quanto por mês, até quando cada marco. Um passo com número é verificável; "economizar mais" não é.

Distribua o XP conforme o esforço de cada passo, sem deixar todos iguais."""

# Motivos de parada que significam "o modelo não entregou o conteúdo".
# STOP é o único desfecho bom; MAX_TOKENS devolve JSON cortado, que não
# passa no json.loads e viraria erro genérico sem esta checagem.
FINAIS_RUINS = {
    "SAFETY": "O modelo bloqueou esta meta por política de conteúdo.",
    "PROHIBITED_CONTENT": "O modelo bloqueou esta meta por política de conteúdo.",
    "BLOCKLIST": "O modelo bloqueou esta meta por política de conteúdo.",
    "SPII": "O modelo bloqueou a meta por parecer conter dado pessoal sensível.",
    "RECITATION": "O modelo interrompeu a resposta por repetição de conteúdo protegido.",
    "MAX_TOKENS": "A resposta da IA foi cortada no limite de tokens.",
}


def _descrever_meta(titulo, descricao=None, alvo=None, prazo=None, existentes=None):
    """Monta o texto da meta. Campos vazios não viram linhas em branco."""
    partes = [f"Meta: {titulo}"]
    if descricao:
        partes.append(f"Detalhes: {descricao}")
    if alvo:
        valor = f"{float(alvo):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        partes.append(f"Valor alvo: R$ {valor}")
    if prazo:
        partes.append(f"Prazo: {prazo}")
    if existentes:
        # A lista vai no prompt para o modelo complementar em vez de
        # recomeçar. Sem ela, "sugerir mais passos" devolvia quase os mesmos.
        partes.append("")
        partes.append("Passos que a meta JÁ TEM (não repita nem parafraseie nenhum):")
        partes.extend(f"- {t}" for t in existentes)
    return "\n".join(partes)


def _normalizar(texto: str) -> str:
    """Chave de comparação para detectar passo repetido.

    Minúsculas, sem acento e sem pontuação: "Abrir conta na corretora!" e
    "abrir conta na corretora" precisam colidir. Paráfrase de verdade quem
    segura é o prompt; isto aqui é a rede para o caso literal.
    """
    import unicodedata

    sem_acento = "".join(
        c for c in unicodedata.normalize("NFD", texto.lower())
        if unicodedata.category(c) != "Mn"
    )
    limpo = "".join(c if c.isalnum() or c.isspace() else " " for c in sem_acento)
    return " ".join(limpo.split())


def _mensagem_de_erro(e) -> str:
    """Traduz a exceção do SDK para algo acionável na tela."""
    from google.genai import errors

    # Client() levanta ValueError quando não acha chave nenhuma. Não deveria
    # chegar aqui (disponivel() barra antes), mas se a variável sumir entre
    # a checagem e a chamada, o usuário merece a mensagem certa.
    if isinstance(e, ValueError) and "API key" in str(e):
        return "Nenhuma chave encontrada. Configure a variável de ambiente GEMINI_API_KEY."

    if isinstance(e, errors.APIError):
        codigo = getattr(e, "code", None)
        if codigo in (400, 401, 403):
            return "A chave do Gemini foi recusada. Confira a GEMINI_API_KEY."
        if codigo == 429:
            return "Cota do Gemini atingida. Tente de novo em alguns minutos."
        if codigo and codigo >= 500:
            return "O Gemini está fora do ar no momento. A meta foi criada sem os passos."
        return f"O Gemini respondeu com erro {codigo}."

    return "Não consegui gerar os passos agora."


def disponivel() -> bool:
    """Se a geração por IA está configurada.

    A tela usa isto para não oferecer um botão que só produziria erro. A
    checagem é feita aqui e não via `genai.Client()` porque construir o
    cliente sem chave levanta ValueError.
    """
    return bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))


def gerar_subtarefas(titulo, descricao=None, alvo=None, prazo=None, existentes=None):
    """Sugere os passos de uma meta.

    `existentes` são os títulos das subtarefas que a meta já tem: eles vão
    no prompt (para o modelo complementar em vez de recomeçar) e servem de
    filtro na saída (nenhum passo literalmente igual passa).

    @return (lista_de_subtarefas, aviso_ou_None). A lista pode vir vazia;
            isso nunca é motivo para falhar a criação da meta.
    """
    if not disponivel():
        return [], (
            "Geração automática desligada: configure a variável de ambiente "
            "GEMINI_API_KEY para a IA sugerir os passos."
        )

    try:
        from google import genai
        from google.genai import types

        # Sem api_key= aqui: o SDK resolve a credencial do ambiente. É o que
        # mantém a chave fora do código.
        #
        # timeout curto porque isso roda dentro de um clique na tela; o
        # padrão deixaria a interface pendurada. Em MILISSEGUNDOS.
        cliente = genai.Client(
            http_options=types.HttpOptions(timeout=config.IA_TIMEOUT * 1000)
        )

        resposta = cliente.models.generate_content(
            model=config.IA_MODELO,
            contents=_descrever_meta(titulo, descricao, alvo, prazo, existentes),
            config=types.GenerateContentConfig(
                system_instruction=INSTRUCOES,
                # Os dois juntos: o mime type liga o modo JSON e o schema diz
                # qual JSON. Só o schema não basta.
                response_mime_type="application/json",
                response_json_schema=ESQUEMA_SUBTAREFAS,
                # MEDIUM em vez de LOW: pensar no caminho da meta antes de
                # escrever é o que separa passo sob medida de lista genérica,
                # e o custo extra por meta segue em centavos.
                thinking_config=types.ThinkingConfig(thinking_level=config.IA_THINKING),
                max_output_tokens=3000,
            ),
        )

        # Checar o motivo de parada ANTES de ler o texto: num bloqueio o
        # conteúdo vem vazio, e num corte por limite vem JSON pela metade.
        # Sem isto, os dois virariam "erro ao interpretar" sem explicar nada.
        candidatos = resposta.candidates or []
        if candidatos:
            motivo = getattr(candidatos[0].finish_reason, "value", candidatos[0].finish_reason)
            if motivo and str(motivo) in FINAIS_RUINS:
                return [], FINAIS_RUINS[str(motivo)]

        texto = resposta.text
        if not texto:
            return [], "A resposta da IA veio vazia."

        # O schema garante a forma, mas ainda normalizamos: título é cortado
        # no limite da coluna e o XP é preso à faixa, porque o banco é a
        # última linha de defesa e um CHECK estourado viraria erro 500.
        brutas = json.loads(texto).get("subtarefas") or []

        # Rede contra repetição literal: nada que já exista na meta entra de
        # novo, e o próprio lote não pode se repetir. Case, acento e
        # pontuação não contam como diferença.
        vistos = {_normalizar(t) for t in (existentes or [])}
        subtarefas = []
        for s in brutas:
            if len(subtarefas) >= config.IA_MAX_SUBTAREFAS:
                break
            titulo_sub = str(s.get("titulo", "")).strip()[:200]
            if not titulo_sub:
                continue
            chave = _normalizar(titulo_sub)
            if not chave or chave in vistos:
                continue
            vistos.add(chave)
            subtarefas.append({
                "titulo": titulo_sub,
                "xp": max(1, min(int(s.get("xp", 10)), 100)),
                "ordem": len(subtarefas),
            })

        if not subtarefas:
            if existentes:
                return [], (
                    "A IA avaliou que os passos existentes já cobrem a meta "
                    "e não sugeriu nada novo."
                )
            return [], "A IA não devolveu nenhum passo utilizável."
        return subtarefas, None

    except Exception as e:  # noqa: BLE001 - de propósito: nada sai daqui
        return [], _mensagem_de_erro(e)
