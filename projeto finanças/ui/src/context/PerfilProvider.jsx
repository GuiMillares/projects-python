// Perfil compartilhado entre a casca e as Configurações.
//
// Sem isto, as duas telas buscavam /api/perfil por conta própria e o avatar
// da topbar continuava mostrando a foto antiga até recarregar a página:
// cada uma tinha a sua cópia do estado. Com o contexto existe uma cópia só,
// e trocar a foto nas Configurações repinta o avatar na hora.

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { carregarPerfil } from "../services/perfilService";

const PerfilContext = createContext({
  perfil: null,
  carregando: true,
  recarregar: async () => {},
  atualizar: () => {},
});

export function PerfilProvider({ children }) {
  const [perfil, setPerfil] = useState(null);
  const [carregando, setCarregando] = useState(true);

  const recarregar = useCallback(async () => {
    try {
      setPerfil(await carregarPerfil());
    } catch {
      setPerfil(null);
    } finally {
      setCarregando(false);
    }
  }, []);

  useEffect(() => {
    recarregar();
  }, [recarregar]);

  /** Aplica uma mudança já confirmada pelo servidor, sem nova ida à rede. */
  const atualizar = useCallback((campos) => {
    setPerfil((p) => (p ? { ...p, ...campos } : p));
  }, []);

  return (
    <PerfilContext.Provider value={{ perfil, carregando, recarregar, atualizar }}>
      {children}
    </PerfilContext.Provider>
  );
}

export const usePerfil = () => useContext(PerfilContext);
