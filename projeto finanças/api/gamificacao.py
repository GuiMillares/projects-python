"""Regras de XP e nível.

O XP total NÃO é gravado em lugar nenhum: é sempre derivado das subtarefas
e metas que estão marcadas como concluídas. Guardar o total abriria espaço
para ele divergir do que o justifica (desmarcar uma subtarefa e o número
continuar lá), e o cálculo é barato o bastante para rodar a cada carga.

Funções puras de propósito: recebem números, devolvem números, não tocam o
banco. Isso deixa a curva de nível testável sem servidor no ar.
"""

import math

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


def bonus_da_meta(soma_xp_subtarefas: int) -> int:
    """Bônus por concluir a meta inteira. Sempre > a soma das subtarefas."""
    return max(BONUS_MINIMO, math.ceil(soma_xp_subtarefas * FATOR_BONUS))


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
    """
    total = 0
    for meta in metas:
        subs = meta.get("subtarefas") or []
        total += sum(s["xp"] for s in subs if s["concluida"])
        if meta["concluida"]:
            total += bonus_da_meta(sum(s["xp"] for s in subs))
    return total
