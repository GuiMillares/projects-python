import { createContext, useCallback, useContext, useEffect, useState } from "react";

// Três modos: "aparelho" segue o tema do celular ou do computador (e muda
// junto, ao vivo, quando ele troca sozinho à noite); "claro" e "escuro"
// fixam. O padrão é seguir o aparelho.
//
// Chave nova de propósito: a antiga (fin_theme) guardava o último clique
// no botão da topbar, e não dá para saber se foi escolha ou acaso. Todo
// mundo recomeça seguindo o aparelho.
const CHAVE = "fin_tema_modo";
const MODOS = ["aparelho", "claro", "escuro"];

const ThemeContext = createContext({
  theme: "dark",
  modo: "aparelho",
  setModo: () => {},
  toggleTheme: () => {},
});

const consulta = () => window.matchMedia?.("(prefers-color-scheme: light)");
const temaDoAparelho = () => (consulta()?.matches ? "light" : "dark");

const modoSalvo = () => {
  try {
    const m = localStorage.getItem(CHAVE);
    return MODOS.includes(m) ? m : "aparelho";
  } catch {
    return "aparelho";
  }
};

const resolver = (modo, aparelho) =>
  modo === "claro" ? "light" : modo === "escuro" ? "dark" : aparelho;

export function ThemeProvider({ children }) {
  const [modo, setModoEstado] = useState(modoSalvo);
  const [aparelho, setAparelho] = useState(temaDoAparelho);
  const theme = resolver(modo, aparelho);

  // Segue a troca do sistema enquanto o app está aberto.
  useEffect(() => {
    const mq = consulta();
    if (!mq) return;
    const mudou = () => setAparelho(temaDoAparelho());
    mq.addEventListener?.("change", mudou);
    return () => mq.removeEventListener?.("change", mudou);
  }, []);

  useEffect(() => {
    // Todos os tokens de cor pendem de :root[data-theme]. Trocar o
    // atributo repinta a aplicação inteira sem re-render de componente.
    document.documentElement.setAttribute("data-theme", theme);

    // A barra do sistema no Android (app instalado) segue o theme-color.
    // Lido do token para não repetir cor fora do tokens.css.
    const meta = document.querySelector('meta[name="theme-color"]');
    const cor = getComputedStyle(document.documentElement).getPropertyValue("--fin-bg-2").trim();
    if (meta && cor) meta.setAttribute("content", cor);
  }, [theme]);

  const setModo = useCallback((m) => {
    if (!MODOS.includes(m)) return;
    setModoEstado(m);
    try {
      localStorage.setItem(CHAVE, m);
    } catch {
      // Sem armazenamento: vale só nesta visita.
    }
  }, []);

  // O botão da topbar inverte o que está na tela e fixa a escolha.
  const toggleTheme = useCallback(
    () => setModo(theme === "dark" ? "claro" : "escuro"),
    [theme, setModo],
  );

  return (
    <ThemeContext.Provider value={{ theme, modo, setModo, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export const useTheme = () => useContext(ThemeContext);
