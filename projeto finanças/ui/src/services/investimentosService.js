import { api } from "./api";

/**
 * Posições + cotação.
 *
 * A resposta traz `aviso` quando a cotação não pôde ser buscada. Isso não é
 * erro de carregamento: os itens vêm completos com quantidade e preço médio,
 * só sem os números de mercado. A tela mostra o aviso e segue funcionando.
 */
export const listarInvestimentos = () => api.get("/api/investimentos");

export const criarInvestimento = (i) => api.post("/api/investimentos", i);

export const apagarInvestimento = (id) => api.del(`/api/investimentos/${id}`);

/** Cotação de um único ticker, para sugerir o preço enquanto o usuário digita. */
export const buscarCotacao = (ticker) =>
  api.get(`/api/cotacoes/${encodeURIComponent(ticker)}`);

/**
 * Números derivados de uma posição.
 *
 * Sem cotação, `atual`, `lucro` e `lucroPct` ficam nulos em vez de zero:
 * zero significaria "não rendeu nada", e o que houve foi "não sabemos".
 */
export function calcularPosicao(item) {
  const preco = item.cotacao?.preco;
  if (preco == null) {
    return { ...item, atual: null, lucro: null, lucroPct: null };
  }
  const atual = item.quantidade * preco;
  const lucro = atual - item.investido;
  return {
    ...item,
    atual,
    lucro,
    lucroPct: item.investido > 0 ? (lucro / item.investido) * 100 : null,
  };
}

/** Totais da carteira. Posições sem cotação entram só no investido. */
export function resumoCarteira(posicoes) {
  const investido = posicoes.reduce((s, p) => s + p.investido, 0);

  const comCotacao = posicoes.filter((p) => p.atual !== null);
  const atual = comCotacao.reduce((s, p) => s + p.atual, 0);
  const investidoComCotacao = comCotacao.reduce((s, p) => s + p.investido, 0);

  return {
    investido,
    // O valor atual só é comparável com o investido das MESMAS posições.
    // Somar o investido de tudo contra o atual de parte daria um prejuízo
    // fantasma sempre que uma cotação faltasse.
    atual: comCotacao.length ? atual : null,
    investidoComCotacao,
    lucro: comCotacao.length ? atual - investidoComCotacao : null,
    lucroPct:
      comCotacao.length && investidoComCotacao > 0
        ? ((atual - investidoComCotacao) / investidoComCotacao) * 100
        : null,
    semCotacao: posicoes.length - comCotacao.length,
  };
}
