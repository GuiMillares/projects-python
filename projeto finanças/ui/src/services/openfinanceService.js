import { api } from "./api";

/**
 * Conexões do Open Finance com saldos e faturas, lidos da Pluggy na hora.
 *
 * Cada conexão vem com `dados` (ou nulo) e o próprio `aviso`: uma conexão
 * fora do ar não impede as outras de aparecer.
 */
export const lerOpenFinance = () => api.get("/api/openfinance");

/** Token do widget Pluggy Connect. Com `conexaoId`, abre para reconectar. */
export const tokenDoWidget = (conexaoId) =>
  api.post("/api/openfinance/connect-token", conexaoId ? { conexaoId } : {});

export const conectar = (itemId) => api.post("/api/openfinance/conexoes", { itemId });

export const desconectar = (id) => api.del(`/api/openfinance/conexoes/${id}`);

/** Pede para a Pluggy buscar no banco agora. Volta antes de terminar. */
export const sincronizar = (id) => api.post(`/api/openfinance/conexoes/${id}/atualizar`);

export const importarTransacoes = (desde) => api.post("/api/openfinance/importar", { desde });

// A visão geral importa sozinha ao abrir, mas não a cada troca de tela:
// cada importação lê todas as contas na Pluggy.
const INTERVALO_IMPORTACAO_MS = 15 * 60 * 1000;
let ultimaImportacao = 0;

/**
 * Importa o que entrou nos bancos desde a última vez, se já passou o
 * intervalo. Devolve o resultado da importação, ou null quando não rodou.
 * Erro sobe para quem chamou decidir se mostra.
 */
export async function importarSeFaltar(resposta) {
  const conexoes = resposta?.conexoes || [];
  if (!resposta?.disponivel || !conexoes.some((c) => c.dados)) return null;
  if (Date.now() - ultimaImportacao < INTERVALO_IMPORTACAO_MS) return null;

  ultimaImportacao = Date.now();
  try {
    return await importarTransacoes(resposta.importarDesde);
  } catch (e) {
    // Falhou: a próxima abertura tenta de novo em vez de esperar 15 min.
    ultimaImportacao = 0;
    throw e;
  }
}

/** Totais da tela. Conta sem saldo informado fica fora em vez de virar zero. */
export function resumoOpenFinance(conexoes) {
  const dados = conexoes.map((c) => c.dados).filter(Boolean);
  const contas = dados.flatMap((d) => d.contas);
  const cartoes = dados.flatMap((d) => d.cartoes);
  const investimentos = dados.flatMap((d) => d.investimentos || []);

  const soma = (lista) => lista.reduce((s, v) => s + (v ?? 0), 0);
  const futuras = cartoes.flatMap((c) => c.faturasFuturas);

  return {
    saldo: soma(contas.map((c) => c.saldo)),
    contas: contas.filter((c) => c.saldo != null).length,
    emAberto: soma(cartoes.map((c) => c.faturaAtual.valor)),
    cartoes: cartoes.length,
    parcelado: soma(futuras.map((f) => f.valor)),
    mesesParcelados: new Set(futuras.map((f) => f.mes)).size,
    investido: soma(investimentos.map((i) => i.saldo)),
    investimentos: investimentos.length,
  };
}

/**
 * Faturas atuais que vencem nos próximos `janelaDias`, no formato dos pontos
 * de atenção do dashboard. Vencida não entra: o Open Finance não diz se foi
 * paga, e alarme falso de atraso ensina a ignorar o alarme.
 */
export function faturasAVencer(conexoes, hoje = new Date(), janelaDias = 10) {
  const inicio = new Date(hoje.getFullYear(), hoje.getMonth(), hoje.getDate());
  return conexoes
    .flatMap((c) => c.dados?.cartoes || [])
    .filter((c) => c.faturaAtual.vencimento && c.faturaAtual.valor > 0)
    .map((c) => {
      const [a, m, d] = c.faturaAtual.vencimento.split("-").map(Number);
      const faltam = Math.round((new Date(a, m - 1, d) - inicio) / 86400000);
      return { c, faltam };
    })
    .filter(({ faltam }) => faltam >= 0 && faltam <= janelaDias)
    .map(({ c, faltam }) => ({
      id: `fat-${c.id}`,
      tipo: "vencendo",
      titulo: `Fatura ${c.nome.trim()}`,
      detalhe:
        faltam === 0 ? "vence hoje" : `vence em ${faltam} ${faltam === 1 ? "dia" : "dias"}`,
      valor: c.faturaAtual.valor,
      ordem: 3,
    }));
}

/** "há 5 min", "há 3 h", "em 12/10". Para dizer quão velho está o saldo. */
export function haQuanto(iso, agora = new Date()) {
  if (!iso) return "nunca sincronizado";
  const d = new Date(iso);
  const min = Math.round((agora - d) / 60000);
  if (min < 1) return "agora mesmo";
  if (min < 60) return `há ${min} min`;
  if (min < 24 * 60) return `há ${Math.round(min / 60)} h`;
  return `em ${d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" })}`;
}
