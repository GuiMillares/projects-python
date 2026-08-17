import { useEffect, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import AppLayout from "./components/AppLayout";
import { PerfilProvider } from "./context/PerfilProvider";
import EmBreve from "./pages/EmBreve";
import { Target } from "lucide-react";
import Configuracoes from "./pages/Configuracoes";
import Dashboard from "./pages/Dashboard";
import Investimentos from "./pages/Investimentos";
import Lancamentos from "./pages/Lancamentos";
import Login from "./pages/Login";
import { sessaoValida } from "./services/authService";

/**
 * Porteiro das rotas internas.
 *
 * Quem decide é o servidor: `sessaoValida` bate na API e só passa se a
 * sessão existir, não tiver expirado E já tiver passado pelo 2FA. Um
 * token forjado no sessionStorage não abre nada: as rotas de dado
 * exigem a mesma checagem do outro lado.
 */
function ExigeSessao({ children }) {
  const [estado, setEstado] = useState("verificando");

  useEffect(() => {
    sessaoValida().then((ok) => setEstado(ok ? "ok" : "negado"));
  }, []);

  if (estado === "verificando") return null;
  if (estado === "negado") return <Navigate to="/login" replace />;
  return children;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />

      <Route
        path="/app/*"
        element={
          <ExigeSessao>
            <PerfilProvider>
              <AppLayout>
                <Routes>
                  <Route index element={<Dashboard />} />
                  {/* Entradas e Saídas são a mesma tela com `natureza`
                      trocada; ver pages/Lancamentos.jsx. A key força a
                      remontagem ao navegar de uma para a outra, senão o
                      React reaproveita o componente e o estado do
                      formulário atravessa a troca de aba. */}
                  <Route
                    path="entradas"
                    element={<Lancamentos key="receita" natureza="receita" />}
                  />
                  <Route
                    path="saidas"
                    element={<Lancamentos key="despesa" natureza="despesa" />}
                  />
                  <Route path="investimentos" element={<Investimentos />} />
                  <Route
                    path="metas"
                    element={
                      <EmBreve
                        titulo="Metas"
                        icone={Target}
                        descricao="Objetivos com valor-alvo, prazo e quanto já foi guardado."
                      />
                    }
                  />
                  <Route path="configuracoes" element={<Configuracoes />} />
                  <Route path="*" element={<Navigate to="/app" replace />} />
                </Routes>
              </AppLayout>
            </PerfilProvider>
          </ExigeSessao>
        }
      />

      <Route path="*" element={<Navigate to="/app" replace />} />
    </Routes>
  );
}
