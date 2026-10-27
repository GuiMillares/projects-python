// Recorrências detectadas no histórico e a previsão do fim do mês.
//
// Funções puras, como em financasService: recebem as transações (já sem as
// marcadas como "não conta") e devolvem números. Nada aqui fala com a API.
//
// Recorrente = a mesma origem aparece em vários meses fechados. "Mesma
// origem" é decidido pela chave de `chaveRecorrente`: o banco escreve a
// descrição com número de parcela, código e data, então comparar o texto
// inteiro nunca acharia nada.

import { chaveMes, mesDaTransacao, ultimosMeses } from "./financasService";

// Prefixos genéricos que o banco põe antes do nome que importa. Sem tirar
// isso, "pix enviado para" viraria uma única recorrência gigante.
const PREFIXOS = [
  "pix enviado para",
  "pix recebido de",
  "pix enviado",
  "pix recebido",
  "transferencia enviada",
  "transferencia recebida",
  "pagamento efetuado",
  "pagamento de boleto",
  "debito automatico",
  "compra no debito",
];

export function chaveRecorrente(nome) {
  let s = String(nome || "")
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/\bparc(ela)?\b/g, " ")
    .replace(/[^a-z ]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  const prefixo = PREFIXOS.find((p) => s.startsWith(`${p} `));
  if (prefixo) s = s.slice(prefixo.length).trim();
  return s
    .split(" ")
    .filter((p) => p.length > 1)
    .slice(0, 3)
    .join(" ");
}

const media = (xs) => xs.reduce((s, x) => s + x, 0) / xs.length;

const mediana = (xs) => {
  const o = [...xs].sort((a, b) => a - b);
  const m = Math.floor(o.length / 2);
  return o.length % 2 ? o[m] : (o[m - 1] + o[m]) / 2;
};

/** Desvio relativo: 0 = sempre o mesmo valor, 0,5 = varia metade da média. */
const variacao = (xs) => {
  if (xs.length < 2) return 0;
  const m = media(xs);
  if (!m) return 0;
  return Math.sqrt(media(xs.map((x) => (x - m) ** 2))) / m;
};

/**
 * Recorrências dos últimos `meses` meses fechados.
 *
 * Entra quem apareceu em 3 ou mais desses meses (e em pelo menos um dos dois
 * últimos, senão é coisa que já acabou), com valor que não varia demais.
 * Também entra a cobrança NOVA: só nos dois últimos meses, com o mesmo
 * valor, que é a cara de assinatura recém-feita.
 *
 * Cada item:
 *   valorMensal  mediana do total por mês (salário em duas parcelas soma)
 *   noMes        quanto já caiu no mês corrente
 *   falta        o que ainda deve cair no mês corrente
 *   subiu        o último mês fechado veio 10% acima do que era estável
 */
export function detectarRecorrentes(transacoes, hoje = new Date(), meses = 6) {
  const atual = chaveMes(hoje);
  const fechados = ultimosMeses(meses + 1, hoje).slice(0, meses);
  const ultimo = fechados[fechados.length - 1];
  const penultimo = fechados[fechados.length - 2];

  const grupos = new Map();
  for (const t of transacoes) {
    const m = mesDaTransacao(t);
    if (m !== atual && !fechados.includes(m)) continue;
    const chave = chaveRecorrente(t.nome);
    if (!chave) continue;
    // Lançamento manual não tem meio; para a previsão ele sai da conta.
    const meio = t.meio || "conta";
    const id = `${t.natureza}|${meio}|${chave}`;
    if (!grupos.has(id)) grupos.set(id, { id, natureza: t.natureza, meio, porMes: new Map(), itens: [] });
    const g = grupos.get(id);
    g.porMes.set(m, (g.porMes.get(m) || 0) + t.valor);
    g.itens.push(t);
  }

  const saida = [];
  for (const g of grupos.values()) {
    const presentes = fechados.filter((m) => g.porMes.has(m));
    if (presentes.length < 2) continue;

    const valores = presentes.map((m) => g.porMes.get(m));
    const nosDoisUltimos = [penultimo, ultimo].filter((m) => g.porMes.has(m)).length;
    const varia = variacao(valores);

    const nova = presentes.length === 2 && nosDoisUltimos === 2 && varia <= 0.1;
    const recorrente = (presentes.length >= 3 && nosDoisUltimos >= 1 && varia <= 0.6) || nova;
    if (!recorrente) continue;

    // "Subiu" só faz sentido para o que era estável (assinatura, conta
    // fixa): num gasto que já varia, 10% a mais não diz nada.
    const antes = presentes.filter((m) => m !== ultimo).map((m) => g.porMes.get(m));
    const valorUltimo = g.porMes.get(ultimo) ?? null;
    const base = antes.length >= 2 && variacao(antes) <= 0.1 ? mediana(antes) : null;
    const subiu = valorUltimo != null && base != null && valorUltimo > base * 1.1 && valorUltimo - base >= 2;

    const recente = g.itens.reduce((a, b) => (b.data > a.data ? b : a));
    const valorMensal = mediana(valores);
    const noMes = g.porMes.get(atual) || 0;

    saida.push({
      id: g.id,
      nome: recente.nome,
      categoria: recente.categoria,
      natureza: g.natureza,
      meio: g.meio,
      valorMensal,
      dia: Math.round(mediana(g.itens.map((t) => Number(t.data.slice(8, 10)) || 1))),
      meses: presentes.length,
      noMes,
      // 5% de folga: a conta de luz que veio R$ 2 abaixo da mediana já
      // foi paga, não falta R$ 2 dela.
      falta: noMes >= valorMensal * 0.95 ? 0 : valorMensal - noMes,
      variavel: varia > 0.25,
      nova,
      subiu,
      valorAnterior: base,
      valorUltimo,
    });
  }

  return saida.sort((a, b) => b.valorMensal - a.valorMensal);
}

const iso = (d) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

/**
 * Quanto deve sobrar no fim do mês.
 *
 *   saldo de hoje
 *   + recorrentes de entrada que ainda não caíram
 *   - recorrentes de saída que ainda não saíram DA CONTA
 *   - faturas de cartão que vencem até o fim do mês
 *
 * Recorrente no cartão não desconta: ela vai para a fatura, e a fatura já
 * entra pelo valor que o banco informa. Descontar as duas contaria o mesmo
 * dinheiro duas vezes.
 */
export function previsaoDoMes({ saldoHoje, recorrentes, cartoes = [], hoje = new Date() }) {
  const fim = iso(new Date(hoje.getFullYear(), hoje.getMonth() + 1, 0));
  const hojeISO = iso(hoje);

  const pendentes = (natureza) =>
    recorrentes.filter((r) => r.natureza === natureza && r.meio !== "cartao" && r.falta > 0);
  const entradas = pendentes("receita");
  const saidas = pendentes("despesa");
  const faturas = cartoes.filter(
    (c) =>
      c.faturaAtual.valor > 0 &&
      c.faturaAtual.vencimento &&
      c.faturaAtual.vencimento >= hojeISO &&
      c.faturaAtual.vencimento <= fim,
  );

  const soma = (xs, f) => xs.reduce((s, x) => s + f(x), 0);
  const totalEntradas = soma(entradas, (r) => r.falta);
  const totalSaidas = soma(saidas, (r) => r.falta);
  const totalFaturas = soma(faturas, (c) => c.faturaAtual.valor);

  return {
    fim,
    saldoHoje,
    entradas,
    saidas,
    faturas,
    totalEntradas,
    totalSaidas,
    totalFaturas,
    saldoFinal: saldoHoje + totalEntradas - totalSaidas - totalFaturas,
  };
}

/** Avisos do painel: cobrança que subiu e cobrança mensal nova. */
export function alertasDeRecorrentes(recorrentes) {
  return recorrentes
    .filter((r) => r.natureza === "despesa" && (r.subiu || r.nova))
    .map((r) => ({
      id: `rec-${r.id}`,
      tipo: r.subiu ? "aumento" : "nova",
      titulo: r.nome,
      detalhe: r.subiu ? "subiu no último mês" : "cobrança nova todo mês",
      valor: r.subiu ? r.valorUltimo : r.valorMensal,
      ordem: r.subiu ? 2 : 4,
    }));
}
