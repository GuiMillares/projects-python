// A escada de níveis: 300 aparências distintas, uma por nível.
//
// O desenho segue o que os sistemas de rank maduros fazem em três camadas
// (pesquisado em 18/08/2026):
//   1. PATAMARES com nome de material, do humilde ao lendário: é o modelo
//      Duolingo (Bronze -> ... -> Obsidiana -> Diamante) e Overwatch.
//   2. DIVISÕES em algarismo romano dentro do patamar (IV -> I), como
//      League of Legends: subir de Ouro III para Ouro II é progresso
//      visível mesmo longe da troca de patamar. A divisão também muda a
//      BORDA do selo (ver .fin-selo em app.css): o anel ganha espessura,
//      depois um segundo anel, depois brilho. Assim a promoção de IV para
//      III se vê no desenho, não só no texto.
//   3. PIPS estilo insígnia militar dentro da divisão (1 a 5 bolinhas):
//      o grão mais fino, muda a cada nível.
//
// 15 patamares x 4 divisões x 5 pips = 300 combinações únicas. Nível 1 e
// nível 2 diferem nos pips; 5 e 6 diferem na divisão; 20 e 21 trocam de
// patamar inteiro (nome, ícone e cor).
//
// Os ícones ficam aqui como STRING e viram componente no Metas.jsx: assim
// este módulo não importa nada e dá para testá-lo no Node puro.
// As cores são tokens de tokens.css, nunca hex, como todo o resto do app.

export const NIVEL_MAXIMO = 300;

export const NIVEIS_POR_PATAMAR = 20; // 4 divisões de 5 níveis
const NIVEIS_POR_DIVISAO = 5;

// Ordem: brotar -> material bruto -> metais -> preciosos -> lendário.
export const PATAMARES = [
  { nome: "Semente", icone: "Sprout", cor: "var(--fin-cat-3)" },
  { nome: "Broto", icone: "Leaf", cor: "var(--fin-cat-4)" },
  { nome: "Madeira", icone: "TreePine", cor: "var(--fin-cat-1)" },
  { nome: "Pedra", icone: "Mountain", cor: "var(--fin-cat-6)" },
  { nome: "Bronze", icone: "Medal", cor: "var(--fin-cat-2)" },
  { nome: "Cobre", icone: "Coins", cor: "var(--fin-out)" },
  { nome: "Ferro", icone: "Hammer", cor: "var(--fin-muted)" },
  { nome: "Aço", icone: "Shield", cor: "var(--fin-cat-6)" },
  { nome: "Prata", icone: "Award", cor: "var(--fin-muted)" },
  { nome: "Ouro", icone: "Trophy", cor: "var(--fin-warn)" },
  { nome: "Jade", icone: "Gem", cor: "var(--fin-cat-4)" },
  { nome: "Rubi", icone: "Diamond", cor: "var(--fin-danger)" },
  { nome: "Granada", icone: "Sparkles", cor: "var(--fin-cat-5)" },
  { nome: "Mestre", icone: "Star", cor: "var(--fin-warn)" },
  { nome: "Lenda", icone: "Crown", cor: "var(--fin-accent)" },
];

// Divisão 0 é a IV (entrada do patamar) e 3 é a I (topo), como nos ranks
// de jogo: o numeral DESCE enquanto você sobe.
const DIVISOES = ["IV", "III", "II", "I"];

/**
 * Tudo que a tela precisa para desenhar um nível.
 *
 * @returns {{
 *   nivel: number, patamar: string, icone: string, cor: string,
 *   divisao: string, divisaoIndice: number, pips: number,
 *   rotulo: string, maximo: boolean
 * }}
 */
export function infoDoNivel(nivel) {
  const n = Math.max(1, Math.min(Number(nivel) || 1, NIVEL_MAXIMO));
  const indice = n - 1;

  const patamar = PATAMARES[Math.floor(indice / NIVEIS_POR_PATAMAR)];
  const dentroDoPatamar = indice % NIVEIS_POR_PATAMAR;
  const divisaoIndice = Math.floor(dentroDoPatamar / NIVEIS_POR_DIVISAO);
  const divisao = DIVISOES[divisaoIndice];
  const pips = (dentroDoPatamar % NIVEIS_POR_DIVISAO) + 1;

  return {
    nivel: n,
    patamar: patamar.nome,
    icone: patamar.icone,
    cor: patamar.cor,
    divisao,
    divisaoIndice,
    pips,
    rotulo: `${patamar.nome} ${divisao}`,
    maximo: n >= NIVEL_MAXIMO,
  };
}
