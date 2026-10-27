// Regras de negócio do painel: agregações, formatação e leitura da API.
//
// Os cálculos são puros e recebem a lista de transações por parâmetro: dá
// para testar sem servidor no ar e sem mock de rede.
//
// Formato canônico de uma transação:
//   { id, data: "YYYY-MM-DD", nome, valor: number>0,
//     natureza: "receita"|"despesa", categoria, recorrencia: "mensal"|"unica",
//     importada: bool, ignorada: bool, meio: "conta"|"cartao"|null }
//
// `ignorada` = o usuário marcou "não conta". A transação continua na lista
// de Entradas/Saídas (para poder desmarcar), mas TODO cálculo recebe só
// `contaveis(lista)`.

// ── Normalização ─────────────────────────────────────────────────────────────
// A API já devolve tudo normalizado (o MySQL tem DATE e ENUM). Isto aqui é a
// rede de proteção para dado antigo importado do SQLite, que gravava data
// como "DD/MM/AAAA" e natureza capitalizada ("Receita").
const paraISO = (data) => {
  if (!data) return "";
  const s = String(data).trim();
  const br = s.match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
  if (br) return `${br[3]}-${br[2]}-${br[1]}`;
  return s.slice(0, 10);
};

export const normalizarTransacao = (t, i = 0) => ({
  id: t.id ?? `t${i}`,
  data: paraISO(t.data),
  nome: (t.nome || "").trim() || "Sem descrição",
  valor: Math.abs(Number(t.valor) || 0),
  natureza: String(t.natureza || "").toLowerCase().startsWith("rec") ? "receita" : "despesa",
  categoria: (t.categoria || "").trim() || "Sem categoria",
  recorrencia: String(t.recorrencia || "").toLowerCase().startsWith("mens") ? "mensal" : "unica",
  importada: Boolean(t.importada),
  ignorada: Boolean(t.ignorada),
  meio: t.meio || null,
});

/** O que entra nas contas: tudo menos o marcado como "não conta". */
export const contaveis = (transacoes) => transacoes.filter((t) => !t.ignorada);

// ── Datas ────────────────────────────────────────────────────────────────────
export const chaveMes = (d) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;

export const mesDaTransacao = (t) => (t.data || "").slice(0, 7);

const MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];

export const rotuloMes = (ym) => MESES[Number(String(ym).split("-")[1]) - 1] || ym;

export const ultimosMeses = (n, ate = new Date()) => {
  const out = [];
  for (let i = n - 1; i >= 0; i--) {
    out.push(chaveMes(new Date(ate.getFullYear(), ate.getMonth() - i, 1)));
  }
  return out;
};

// ── Formatação ───────────────────────────────────────────────────────────────
export const brl = (v) =>
  Number(v || 0).toLocaleString("pt-BR", {
    style: "currency",
    currency: "BRL",
    maximumFractionDigits: 2,
  });

/** Versão curta para eixos e KPIs: R$ 12,4 mil. */
export const brlCurto = (v) => {
  const n = Number(v || 0);
  const abs = Math.abs(n);
  if (abs >= 1000) {
    const mil = (n / 1000).toLocaleString("pt-BR", { maximumFractionDigits: 1 });
    return `R$ ${mil} mil`;
  }
  return brl(n);
};

export const dataCurta = (iso) => {
  const [, m, d] = String(iso).split("-");
  return d && m ? `${d}/${m}` : iso;
};

// ── Agregações ───────────────────────────────────────────────────────────────
export function resumoDoMes(transacoes, ym) {
  const doMes = transacoes.filter((t) => mesDaTransacao(t) === ym);
  const entradas = doMes.filter((t) => t.natureza === "receita").reduce((s, t) => s + t.valor, 0);
  const saidas = doMes.filter((t) => t.natureza === "despesa").reduce((s, t) => s + t.valor, 0);
  return { entradas, saidas, resultado: entradas - saidas, lancamentos: doMes.length };
}

/**
 * Saldo acumulado desde o primeiro lançamento até o fim de cada mês.
 *
 * Com `saldoHoje` (o saldo real vindo dos bancos), a curva é deslocada para
 * terminar nele: os lançamentos dão a forma, o banco dá a altura. Sem isso,
 * um histórico importado só dos últimos 12 meses começaria do zero.
 */
export function serieSaldoAcumulado(transacoes, meses, saldoHoje = null) {
  const pontos = acumularPorMes(transacoes, meses);
  if (saldoHoje == null) return pontos;
  const ajuste = saldoHoje - saldoAtual(transacoes);
  return pontos.map((p) => ({ ...p, valor: p.valor + ajuste }));
}

function acumularPorMes(transacoes, meses) {
  const porMes = new Map();
  transacoes.forEach((t) => {
    const m = mesDaTransacao(t);
    const delta = t.natureza === "receita" ? t.valor : -t.valor;
    porMes.set(m, (porMes.get(m) || 0) + delta);
  });

  // Tudo que aconteceu ANTES da janela exibida vira o saldo de partida.
  const primeiro = meses[0];
  let acc = 0;
  porMes.forEach((v, m) => {
    if (m < primeiro) acc += v;
  });

  return meses.map((m) => {
    acc += porMes.get(m) || 0;
    return { label: rotuloMes(m), chave: m, valor: acc };
  });
}

export function saldoAtual(transacoes) {
  return transacoes.reduce((s, t) => s + (t.natureza === "receita" ? t.valor : -t.valor), 0);
}

/** Entradas × saídas mês a mês (duas séries para o gráfico de barras). */
export function serieEntradasSaidas(transacoes, meses) {
  return meses.map((m) => {
    const { entradas, saidas } = resumoDoMes(transacoes, m);
    return { label: rotuloMes(m), chave: m, valores: [entradas, saidas] };
  });
}

/** Gastos por categoria num mês, do maior para o menor. */
export function gastosPorCategoria(transacoes, ym) {
  const mapa = new Map();
  transacoes
    .filter((t) => t.natureza === "despesa" && mesDaTransacao(t) === ym)
    .forEach((t) => mapa.set(t.categoria, (mapa.get(t.categoria) || 0) + t.valor));

  return [...mapa.entries()]
    .map(([label, valor]) => ({ label, valor }))
    .sort((a, b) => b.valor - a.valor);
}

export function categorias(transacoes) {
  return [...new Set(transacoes.filter((t) => t.natureza === "despesa").map((t) => t.categoria))].sort();
}

// ── Pontos de atenção ────────────────────────────────────────────────────────
// Dois tipos numa lista só, ordenados por urgência:
//   1. estouro:  categoria que passou do orçamento do mês
//   2. vencendo: despesa mensal recorrente cuja data deste mês ainda não
//                 chegou (ou chegou há pouco) e que ainda não foi lançada
const diasEntre = (a, b) => Math.round((b - a) / 86400000);

export function pontosDeAtencao(transacoes, orcamentos, hoje = new Date(), janelaDias = 10) {
  const ym = chaveMes(hoje);
  const itens = [];

  // 1. Orçamentos estourados / no limite
  gastosPorCategoria(transacoes, ym).forEach(({ label, valor }) => {
    const teto = Number(orcamentos?.[label]) || 0;
    if (teto <= 0) return;
    const uso = valor / teto;
    if (uso < 0.85) return;
    itens.push({
      id: `orc-${label}`,
      tipo: uso > 1 ? "estouro" : "limite",
      titulo: label,
      // Texto curto de propósito: na coluna estreita do dashboard, frase
      // longa é cortada com reticências bem em cima do valor.
      detalhe:
        uso > 1
          ? `${brl(valor - teto)} acima do teto`
          : `${Math.round(uso * 100)}% do teto de ${brlCurto(teto)}`,
      valor,
      ordem: uso > 1 ? 0 : 2,
    });
  });

  // 2. Recorrências mensais a vencer
  const lancadosNoMes = new Set(
    transacoes.filter((t) => mesDaTransacao(t) === ym).map((t) => t.nome.toLowerCase()),
  );
  const vistos = new Set();

  transacoes
    .filter((t) => t.recorrencia === "mensal" && t.natureza === "despesa")
    .forEach((t) => {
      const chave = t.nome.toLowerCase();
      if (vistos.has(chave) || lancadosNoMes.has(chave)) return;
      vistos.add(chave);

      const dia = Number((t.data || "").slice(8, 10)) || 1;
      // Dia 31 num mês de 30 cai no último dia. Date(ano, mes, 0) resolve.
      const ultimoDia = new Date(hoje.getFullYear(), hoje.getMonth() + 1, 0).getDate();
      const venc = new Date(hoje.getFullYear(), hoje.getMonth(), Math.min(dia, ultimoDia));
      const faltam = diasEntre(hoje, venc);
      if (faltam > janelaDias) return;

      itens.push({
        id: `rec-${chave}`,
        tipo: faltam < 0 ? "atrasada" : "vencendo",
        titulo: t.nome,
        detalhe:
          faltam < 0
            ? `venceu dia ${dataCurta(venc.toISOString().slice(0, 10))}`
            : faltam === 0
              ? "vence hoje"
              : `vence em ${faltam} ${faltam === 1 ? "dia" : "dias"}`,
        valor: t.valor,
        ordem: faltam < 0 ? 1 : 3,
      });
    });

  return itens.sort((a, b) => a.ordem - b.ordem || b.valor - a.valor);
}

// ── Acesso à API ─────────────────────────────────────────────────────────────
import { api } from "./api";

export async function listarTransacoes() {
  const linhas = await api.get("/api/transacoes");
  return linhas.map(normalizarTransacao);
}

export const criarTransacao = (t) => api.post("/api/transacoes", t);

export const apagarTransacao = (id) => api.del(`/api/transacoes/${id}`);

/** `{ categoria }` e/ou `{ ignorada }`. Categoria trocada aqui vence regra. */
export const editarTransacao = (id, campos) => api.patch(`/api/transacoes/${id}`, campos);

// ── Regras de categoria ──────────────────────────────────────────────────────
// "Descrição contém X vira Y". Valem para as próximas importações e, ao
// serem criadas, para as importadas que já existem.
export const listarRegras = () => api.get("/api/regras");
export const criarRegra = (padrao, categoria) => api.post("/api/regras", { padrao, categoria });
export const apagarRegra = (id) => api.del(`/api/regras/${id}`);

/**
 * Texto sugerido para a regra a partir de uma descrição: tira número,
 * data e o "PARC 03/10", que mudam de um mês para o outro e fariam a regra
 * nunca casar de novo. O usuário pode editar antes de salvar.
 */
export function padraoSugerido(nome) {
  return String(nome || "")
    .replace(/\bparc(ela)?\b/gi, " ")
    .replace(/[\d/.,:*|-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 60);
}

/** Tetos por categoria, na tabela `orcamentos`, chaveada por usuário. */
export const carregarOrcamentos = () => api.get("/api/orcamentos");

/**
 * Teto sugerido por categoria: média dos últimos `meses` meses FECHADOS
 * (o mês corrente pela metade puxaria a média para baixo), arredondada
 * para cima em dezenas. Categoria com média abaixo de R$ 20 fica de fora:
 * acompanhar trocado vira só ruído de alerta.
 */
export function sugerirOrcamentos(transacoes, hoje = new Date(), meses = 3) {
  const janela = ultimosMeses(meses + 1, hoje).slice(0, meses);
  const soma = new Map();
  transacoes
    .filter((t) => t.natureza === "despesa" && janela.includes(mesDaTransacao(t)))
    .forEach((t) => soma.set(t.categoria, (soma.get(t.categoria) || 0) + t.valor));

  return Object.fromEntries(
    [...soma.entries()]
      .map(([categoria, total]) => [categoria, Math.ceil(total / meses / 10) * 10])
      .filter(([, media]) => media >= 20),
  );
}

/** Substitui o conjunto inteiro: categoria ausente perde o teto. */
export const salvarOrcamentos = (orcamentos) => {
  const limpo = Object.fromEntries(
    Object.entries(orcamentos)
      .map(([k, v]) => [k, Number(v) || 0])
      .filter(([, v]) => v > 0),
  );
  return api.put("/api/orcamentos", limpo);
};
