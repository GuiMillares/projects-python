// Qual recorte a pessoa está vendo: "eu", o id de um membro ou "juntos".
//
// Os membros vêm de /api/visao (ela + o espaço). Sem espaço, a lista tem
// uma pessoa só e o seletor nem aparece. A escolha fica no aparelho
// (conveniência); se o membro escolhido saiu do espaço, volta para "eu".
// Quem decide o que cada visão mostra é o servidor (api/visao.py).

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api } from "../services/api";

const CHAVE = "fin_visao";

const VisaoContext = createContext({
  visao: "eu",
  setVisao: () => {},
  membros: [],
  nomeDe: () => "",
  temEspaco: false,
  carregado: false,
});

const lerSalva = () => {
  try {
    return localStorage.getItem(CHAVE) || "eu";
  } catch {
    return "eu";
  }
};

export function VisaoProvider({ children }) {
  const [visao, setVisaoEstado] = useState(lerSalva);
  const [membros, setMembros] = useState([]);
  const [carregado, setCarregado] = useState(false);

  useEffect(() => {
    api
      .get("/api/visao")
      .then((r) => {
        const lista = r.membros || [];
        setMembros(lista);
        setCarregado(true);
        // Membro escolhido antes não está mais no espaço: volta para "eu".
        setVisaoEstado((v) =>
          v === "eu" || (v === "juntos" && lista.length > 1) || lista.some((m) => String(m.id) === v && !m.eu)
            ? v
            : "eu",
        );
      })
      .catch(() => setMembros([]));
  }, []);

  const setVisao = useCallback((v) => {
    const valor = String(v);
    setVisaoEstado(valor);
    try {
      localStorage.setItem(CHAVE, valor);
    } catch {
      // Sem armazenamento: vale só nesta visita.
    }
  }, []);

  const nomeDe = useCallback(
    (id) => membros.find((m) => m.id === id)?.nome || "",
    [membros],
  );

  return (
    <VisaoContext.Provider
      value={{ visao, setVisao, membros, nomeDe, temEspaco: membros.length > 1, carregado }}
    >
      {children}
    </VisaoContext.Provider>
  );
}

export const useVisao = () => useContext(VisaoContext);
