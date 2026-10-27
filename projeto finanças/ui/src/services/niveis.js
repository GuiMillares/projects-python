// A escada de níveis: 300 aparências distintas, uma por nível.
//
// O desenho segue o que os sistemas de rank maduros fazem em três camadas
// (pesquisado em 18/08/2026):
//   1. PATAMARES de pedras preciosas, da menos à mais preciosa (desde
//      27/10/2026; antes eram materiais, de Semente a Lenda). A cor do
//      selo é a da pedra, e o desenho melhora junto com ela: pedra bruta
//      nos 5 primeiros patamares, lapidação simples nos 5 do meio e
//      lapidação brilhante nos 5 últimos.
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

// Ordem de preciosidade. O ícone é o estágio da lapidação:
//   Hexagon  = pedra bruta
//   Diamond  = lapidação simples
//   Gem      = lapidação brilhante
// No topo, o diamante vermelho, a pedra mais rara que existe.
const PEDRAS = [
  ["Quartzo", "Hexagon"],
  ["Ágata", "Hexagon"],
  ["Ametista", "Hexagon"],
  ["Citrino", "Hexagon"],
  ["Granada", "Hexagon"],
  ["Peridoto", "Diamond"],
  ["Água-marinha", "Diamond"],
  ["Turmalina", "Diamond"],
  ["Topázio", "Diamond"],
  ["Tanzanita", "Diamond"],
  ["Esmeralda", "Gem"],
  ["Safira", "Gem"],
  ["Rubi", "Gem"],
  ["Diamante", "Gem"],
  ["Diamante Vermelho", "Gem"],
];

export const PATAMARES = PEDRAS.map(([nome, icone], i) => ({
  nome,
  icone,
  cor: `var(--fin-gema-${i + 1})`,
}));

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
