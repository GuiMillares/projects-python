// Cor de cada categoria nos gráficos.
//
// A primeira versão sorteava a cor por hash do nome. Era estável entre meses,
// mas colidia: com 5 categorias e 6 cores, três caíam na mesma terracota e a
// rosca ficava com três fatias idênticas.
//
// Aqui a cor vem da POSIÇÃO da categoria na lista ordenada de todas as
// categorias existentes. Ordenar (em vez de usar a ordem de aparição no mês)
// mantém a cor estável ao navegar entre meses, e indexar em vez de hashear
// garante que não há repetição enquanto couber na paleta.

const PALETA = [
  "var(--fin-cat-1)",
  "var(--fin-cat-2)",
  "var(--fin-cat-3)",
  "var(--fin-cat-4)",
  "var(--fin-cat-5)",
  "var(--fin-cat-6)",
];

/**
 * @param {string[]} categorias todas as categorias conhecidas
 * @returns {(nome: string) => string} função que devolve a cor de uma categoria
 */
export function criarMapaDeCores(categorias) {
  const ordenadas = [...new Set(categorias)].sort((a, b) => a.localeCompare(b, "pt-BR"));
  const mapa = new Map(ordenadas.map((c, i) => [c, PALETA[i % PALETA.length]]));
  // Passando de 6 categorias a paleta repete, o que é melhor do que inventar
  // cores fora do sistema. Se virar rotina ter mais que isso, o certo é
  // ampliar a paleta em tokens.css, não gerar matiz na hora.
  return (nome) => mapa.get(nome) || "var(--fin-muted)";
}
