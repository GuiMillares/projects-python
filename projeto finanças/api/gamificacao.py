"""Regras de XP e nível.

O XP total NÃO é gravado em lugar nenhum: é sempre derivado das subtarefas
e metas que estão marcadas como concluídas. Guardar o total abriria espaço
para ele divergir do que o justifica (desmarcar uma subtarefa e o número
continuar lá), e o cálculo é barato o bastante para rodar a cada carga.

Funções puras de propósito: recebem números, devolvem números, não tocam o
banco. Isso deixa a curva de nível testável sem servidor no ar.

DIFICULDADE (desde 27/10/2026). Meta com valor ganha um multiplicador
sobre o XP dos passos e do bônus, pelo PESO que ela tem no mês de quem a
fez: parcela mensal (valor ÷ meses entre a criação e o prazo) dividida
pela renda mensal média da própria pessoa. O mesmo valor com metade do
prazo pesa o dobro. É por renda e não por reais porque cada pessoa usa o
app sozinha: R$ 3 mil por mês é épico para um e simples para outro. Sem
renda registrada ainda, a parcela é comparada com faixas fixas em reais.
Meta sem valor fica no padrão (x1).

O multiplicador de meta CONCLUÍDA é congelado no banco na hora da
conclusão (metas.multiplicador): a renda muda todo mês, e o XP de algo que
já foi feito não pode mudar junto.
"""

import math
from datetime import date

# XP mínimo do bônus de uma meta sem subtarefa nenhuma. Concluir uma meta
# que você escreveu e cumpriu sozinho ainda vale alguma coisa.
BONUS_MINIMO = 50

# O bônus é 1.5x a soma das subtarefas. O fator maior que 1 é o que garante
# a regra combinada: terminar a meta inteira sempre vale mais do que a soma
# dos pedaços dela, então nunca compensa parar com tudo feito menos o fim.
FATOR_BONUS = 1.5

# Cada nível custa 100 XP a mais que o anterior: nível 2 aos 100, 3 aos 300,
# 4 aos 600. Curva quadrática simples, sem tabela para manter sincronizada.
XP_POR_DEGRAU = 100

# Teto da escada. A tela desenha 300 aparências distintas (15 patamares x
# 4 divisões x 5 pips, ver ui/src/services/niveis.js); acima disso o número
# pararia de ter representação visual, então o nível para de subir aqui.
NIVEL_MAXIMO = 300

# (teto do peso na renda, teto da parcela em reais, multiplicador, nome).
# A última faixa não tem teto. O x2,5 é o limite de propósito: sem ele,
# uma meta absurda de curto prazo viraria atalho para subir de nível.
FAIXAS = [
    (0.05, 150, 1.0, "simples"),
    (0.15, 500, 1.25, "moderada"),
    (0.30, 1200, 1.5, "puxada"),
    (0.60, 2500, 2.0, "difícil"),
    (None, None, 2.5, "épica"),
]

# Meta com valor e sem prazo é medida como se fosse para um ano.
MESES_SEM_PRAZO = 12

# Concluir até o prazo rende 25% a mais no bônus. Atrasar não tira nada.
BONUS_PONTUAL = 1.25


def dificuldade(alvo, prazo, criada_em, renda_mensal) -> dict:
    """Quanto a meta pesa e o multiplicador que isso dá.

    `criada_em` e não hoje como início: medir até hoje faria a meta ficar
    mais "difícil" sozinha a cada dia que passa sem ninguém fazer nada.
    """
    if not alvo or float(alvo) <= 0:
        return {"nome": "simples", "multiplicador": 1.0, "parcelaMensal": None, "peso": None, "base": None}

    inicio = criada_em.date() if hasattr(criada_em, "date") else (criada_em or date.today())
    meses = max(1.0, (prazo - inicio).days / 30.44) if prazo else MESES_SEM_PRAZO
    parcela = float(alvo) / meses

    if renda_mensal and renda_mensal > 0:
        peso, base, medida, coluna = parcela / renda_mensal, "renda", parcela / renda_mensal, 0
    else:
        peso, base, medida, coluna = None, "reais", parcela, 1

    for faixa in FAIXAS:
        teto = faixa[coluna]
        if teto is None or medida <= teto:
            return {
                "nome": faixa[3],
                "multiplicador": faixa[2],
                "parcelaMensal": round(parcela, 2),
                "peso": round(peso, 3) if peso is not None else None,
                "base": base,
            }


def xp_com_dificuldade(xp: int, multiplicador: float) -> int:
    return round(xp * multiplicador)


def bonus_da_meta(soma_xp_subtarefas: int, multiplicador: float = 1.0, pontual: bool = False) -> int:
    """Bônus por concluir a meta inteira. Sempre > a soma das subtarefas.

    `soma_xp_subtarefas` é a soma SEM multiplicador: o multiplicador entra
    uma vez só, aqui, igual entra uma vez em cada passo. Assim o bônus
    continua 1,5x a soma do que os passos realmente rendem.
    """
    bonus = max(BONUS_MINIMO, soma_xp_subtarefas * FATOR_BONUS) * multiplicador
    if pontual:
        bonus *= BONUS_PONTUAL
    return math.ceil(bonus)


def xp_acumulado_ate(nivel: int) -> int:
    """XP total necessário para ESTAR no nível informado.

    nível 1 = 0, nível 2 = 100, nível 3 = 300, nível 4 = 600...
    """
    if nivel <= 1:
        return 0
    return XP_POR_DEGRAU * (nivel - 1) * nivel // 2


def nivel_de(xp: int) -> int:
    """Nível correspondente a um total de XP.

    Resolve a inversa da soma acumulada em vez de iterar: com XP alto um
    laço faria centenas de voltas a cada request.
    """
    if xp < XP_POR_DEGRAU:
        return 1
    # xp >= 50*n*(n-1)  =>  n = (1 + sqrt(1 + 8*xp/100)) / 2
    n = (1 + math.isqrt(1 + 8 * xp * 100 // (XP_POR_DEGRAU**2) * XP_POR_DEGRAU // 100)) // 2
    # A raiz inteira pode errar por um para cima ou para baixo na fronteira;
    # dois ajustes bastam e ficam O(1).
    while xp_acumulado_ate(n + 1) <= xp:
        n += 1
    while n > 1 and xp_acumulado_ate(n) > xp:
        n -= 1
    return min(n, NIVEL_MAXIMO)


def progresso(xp: int) -> dict:
    """Situação completa do personagem para a tela desenhar a barra."""
    nivel = nivel_de(xp)

    # No teto não existe "próximo nível": a barra fica cheia e o contador
    # de falta zera, em vez de apontar para um nível 301 que não se desenha.
    if nivel >= NIVEL_MAXIMO:
        return {
            "xp": xp,
            "nivel": NIVEL_MAXIMO,
            "xpNoNivel": 0,
            "xpDoNivel": 0,
            "xpParaProximo": 0,
            "percentual": 100.0,
        }

    base = xp_acumulado_ate(nivel)
    proximo = xp_acumulado_ate(nivel + 1)
    faixa = proximo - base
    return {
        "xp": xp,
        "nivel": nivel,
        "xpNoNivel": xp - base,
        "xpDoNivel": faixa,
        "xpParaProximo": proximo - xp,
        # Percentual já calculado aqui para a barra não precisar dividir por
        # zero num nível de faixa vazia.
        "percentual": round((xp - base) / faixa * 100, 1) if faixa else 100.0,
    }


def calcular_xp(metas: list) -> int:
    """XP total a partir das metas já com as subtarefas embutidas.

    Cada subtarefa concluída vale o próprio XP; cada meta concluída vale o
    bônus por cima. Meta concluída NÃO implica subtarefas concluídas: quem
    marcou a meta sem marcar os passos ganha só o bônus, e é coerente.

    Espera o formato de app._carregar_metas: `xp` dos passos e `bonusXp`
    já com a dificuldade aplicada. Sem `bonusXp`, calcula no padrão x1.
    """
    total = 0
    for meta in metas:
        subs = meta.get("subtarefas") or []
        total += sum(s["xp"] for s in subs if s["concluida"])
        if meta["concluida"]:
            bonus = meta.get("bonusXp")
            total += bonus if bonus is not None else bonus_da_meta(sum(s["xp"] for s in subs))
    return total
