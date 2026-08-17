import { createContext, useCallback, useContext, useEffect, useState } from "react";

const STORAGE_KEY = "fin_theme";

const ThemeContext = createContext({
  theme: "dark",
  setTheme: () => {},
  toggleTheme: () => {},
});

// Na primeira execução respeita o sistema; depois, a escolha salva manda.
const temaInicial = () => {
  const salvo = localStorage.getItem(STORAGE_KEY);
  if (salvo === "dark" || salvo === "light") return salvo;
  return window.matchMedia?.("(prefers-color-scheme: light)").matches ? "light" : "dark";
};

export function ThemeProvider({ children }) {
  const [theme, setTheme] = useState(temaInicial);

  useEffect(() => {
    // Todos os tokens de cor pendem de :root[data-theme]. Trocar o
    // atributo repinta a aplicação inteira sem re-render de componente.
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem(STORAGE_KEY, theme);
  }, [theme]);

  const toggleTheme = useCallback(
    () => setTheme((t) => (t === "dark" ? "light" : "dark")),
    [],
  );

  return (
    <ThemeContext.Provider value={{ theme, setTheme, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export const useTheme = () => useContext(ThemeContext);
