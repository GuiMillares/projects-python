"""Quem vê o quê no espaço compartilhado.

Visões:
* "eu"      → só o que é da pessoa (tudo, inclusive o privado);
* "juntos"  → ela + o que os outros membros compartilham;
* <id>      → o que aquele membro compartilha.

Compartilhado é o padrão. Fica de fora da visão dos OUTROS:
* o lançamento com cadeado (transacoes.privada = 1);
* tudo o que veio de uma conexão bancária com cadeado
  (conexoes_bancarias.privada = 1).
O dono sempre vê tudo o que é seu.

Escrita não passa por aqui: toda rota de alterar ou apagar segue com
`usuario_id = <quem pede>` no WHERE. Ver o do outro não é editar o do outro.

Pix entre membros: na visão com mais de uma pessoa, a saída de um que
volta como entrada do outro (mesmo valor, até FOLGA_DIAS de distância) é
dinheiro trocando de mão dentro da casa, não gasto nem renda do grupo.
Os dois lados ganham `entreMembros` e o cliente tira da soma.
"""


import espacos
from db import buscar_todos

FOLGA_DIAS = 3


class VisaoInvalida(Exception):
    pass


def membros(usuario_id: int) -> list:
    """[{'id', 'nome'}] de quem a pessoa pode ver, ela primeiro."""
    meu = espacos.espaco_de(usuario_id)
    if not meu:
        linha = buscar_todos("SELECT id, nome, email FROM usuarios WHERE id = %s", (usuario_id,))
    else:
        linha = espacos.membros(meu["id"])
    lista = [
        {"id": m["id"], "nome": (m["nome"] or m["email"].split("@")[0]).split()[0]}
        for m in linha
    ]
    lista.sort(key=lambda m: m["id"] != usuario_id)
    return lista


def ids_da_visao(usuario_id: int, visao) -> list:
    if visao in (None, "", "eu"):
        return [usuario_id]
    ids = [m["id"] for m in membros(usuario_id)]
    if visao == "juntos":
        return ids
    try:
        alvo = int(visao)
    except (TypeError, ValueError):
        raise VisaoInvalida("Visão inválida.")
    if alvo not in ids:
        raise VisaoInvalida("Essa pessoa não está no seu espaço.")
    return [alvo]


def _filtro(usuario_id: int, ids: list):
    """WHERE das transações visíveis. `t` = transacoes, `c` = conexão."""
    marcadores = ", ".join(["%s"] * len(ids))
    sql = (
        f"t.usuario_id IN ({marcadores}) AND "
        "(t.usuario_id = %s OR (t.privada = 0 AND COALESCE(c.privada, 0) = 0))"
    )
    return sql, (*ids, usuario_id)


def transacoes(usuario_id: int, visao) -> list:
    ids = ids_da_visao(usuario_id, visao)
    onde, params = _filtro(usuario_id, ids)
    linhas = buscar_todos(
        "SELECT t.id, t.usuario_id, t.data, t.nome, t.valor, t.natureza, t.categoria, "
        "       t.recorrencia, t.origem_id, t.ignorada, t.meio, t.privada, t.conexao_id, "
        "       COALESCE(c.privada, 0) AS conexao_privada "
        "  FROM transacoes t LEFT JOIN conexoes_bancarias c ON c.id = t.conexao_id "
        f" WHERE {onde} ORDER BY t.data, t.id",
        params,
    )
    if len(ids) > 1:
        _marcar_entre_membros(linhas)
    return linhas


def _marcar_entre_membros(linhas):
    """Casa saída de um membro com entrada de outro: mesmo valor, até
    FOLGA_DIAS. Cada lançamento entra em um par só, o mais próximo."""
    entradas = {}
    for t in linhas:
        if t["natureza"] == "receita" and not t["ignorada"]:
            entradas.setdefault(t["valor"], []).append(t)
    for s in linhas:
        if s["natureza"] != "despesa" or s["ignorada"] or s.get("entre_membros"):
            continue
        candidatas = [
            e for e in entradas.get(s["valor"], [])
            if e["usuario_id"] != s["usuario_id"] and not e.get("entre_membros")
            and abs((e["data"] - s["data"]).days) <= FOLGA_DIAS
        ]
        if candidatas:
            par = min(candidatas, key=lambda e: abs((e["data"] - s["data"]).days))
            s["entre_membros"] = par["entre_membros"] = True
