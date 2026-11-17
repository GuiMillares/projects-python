// Instalação do app na tela inicial (PWA).
//
// O Chrome do Android dispara `beforeinstallprompt` uma vez, cedo, às
// vezes antes de qualquer tela montar. Por isso a escuta mora aqui, no
// carregamento do módulo (importado pelo main.jsx), e a tela só pergunta
// depois se há convite guardado.
//
// O iPhone não tem esse evento: lá a instalação é sempre pelo Safari, em
// Compartilhar > Adicionar à Tela de Início, e o app só pode ensinar.

let convite = null;
const ouvintes = new Set();
const avisar = () => ouvintes.forEach((f) => f());

if (typeof window !== "undefined") {
  window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault();
    convite = e;
    avisar();
  });
  window.addEventListener("appinstalled", () => {
    convite = null;
    avisar();
  });
}

export const jaInstalado = () =>
  window.matchMedia?.("(display-mode: standalone)").matches || window.navigator.standalone === true;

export const ehIOS = () =>
  /iphone|ipad|ipod/i.test(navigator.userAgent) ||
  (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);

export const temConvite = () => convite !== null;

export function aoMudarConvite(f) {
  ouvintes.add(f);
  return () => ouvintes.delete(f);
}

/** Abre o diálogo do Chrome. Devolve true se a pessoa aceitou. */
export async function instalar() {
  if (!convite) return false;
  const e = convite;
  convite = null;
  avisar();
  e.prompt();
  const { outcome } = await e.userChoice;
  return outcome === "accepted";
}
