// Casca do app.
//
// Desktop (≥900px): sidebar fixa à esquerda.
// Mobile: a sidebar some e as mesmas rotas viram bottom navigation: o
// polegar alcança, e o topo fica livre para o conteúdo. Configurações não
// entra na barra de baixo (cinco itens já é o limite legível); vive no menu
// do avatar, em ambos os tamanhos.

import {
  ArrowDownLeft,
  ArrowUpRight,
  LayoutGrid,
  LogOut,
  Moon,
  Settings,
  Sun,
  Target,
  TrendingUp,
  Wallet,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { usePerfil } from "../context/PerfilProvider";
import { useTheme } from "../context/ThemeProvider";
import { sair as encerrarSessao } from "../services/authService";
import { iniciais } from "../services/perfilService";

const NAV = [
  { to: "/app", fim: true, icon: LayoutGrid, label: "Visão geral", curto: "Geral" },
  { to: "/app/entradas", icon: ArrowUpRight, label: "Entradas", curto: "Entradas" },
  { to: "/app/saidas", icon: ArrowDownLeft, label: "Saídas", curto: "Saídas" },
  { to: "/app/investimentos", icon: TrendingUp, label: "Investimentos", curto: "Investir" },
  { to: "/app/metas", icon: Target, label: "Metas", curto: "Metas" },
];

const TITULOS = {
  "/app": "Visão geral",
  "/app/entradas": "Entradas",
  "/app/saidas": "Saídas",
  "/app/investimentos": "Investimentos",
  "/app/metas": "Metas",
  "/app/configuracoes": "Configurações",
};

export default function AppLayout({ children }) {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const { theme, toggleTheme } = useTheme();
  const escuro = theme === "dark";

  const { perfil } = usePerfil();
  const [menuAberto, setMenuAberto] = useState(false);
  const menuRef = useRef(null);

  // Fecha o menu ao clicar fora ou apertar Esc.
  useEffect(() => {
    if (!menuAberto) return;
    const clique = (e) => {
      if (menuRef.current && !menuRef.current.contains(e.target)) setMenuAberto(false);
    };
    const tecla = (e) => e.key === "Escape" && setMenuAberto(false);
    document.addEventListener("mousedown", clique);
    document.addEventListener("keydown", tecla);
    return () => {
      document.removeEventListener("mousedown", clique);
      document.removeEventListener("keydown", tecla);
    };
  }, [menuAberto]);

  const sair = async () => {
    await encerrarSessao();
    navigate("/login", { replace: true });
  };

  return (
    <div className="fin-shell">
      <aside className="fin-sidebar">
        <div className="fin-sidebar__brand">
          <Wallet size={16} /> Finanças
        </div>

        <nav className="fin-sidebar__nav">
          {NAV.map(({ to, fim, icon: Icone, label }) => (
            <NavLink
              key={to}
              to={to}
              end={fim}
              className={({ isActive }) => `fin-nav-item${isActive ? " active" : ""}`}
            >
              <Icone size={15} />
              {label}
            </NavLink>
          ))}

          <div className="fin-sidebar__group">Conta</div>
          <NavLink
            to="/app/configuracoes"
            className={({ isActive }) => `fin-nav-item${isActive ? " active" : ""}`}
          >
            <Settings size={15} />
            Configurações
          </NavLink>
        </nav>

        <div className="fin-sidebar__foot">
          <button className="fin-nav-item fin-nav-item--exit" onClick={sair}>
            <LogOut size={15} /> Sair
          </button>
        </div>
      </aside>

      <div className="fin-main">
        <header className="fin-topbar">
          <div className="fin-topbar__title">
            <Wallet size={15} />
            {TITULOS[pathname] || "Finanças"}
          </div>

          <div className="fin-topbar__right">
            <button
              className="fin-icon-btn"
              onClick={toggleTheme}
              aria-label={escuro ? "Mudar para tema claro" : "Mudar para tema escuro"}
              title={escuro ? "Tema claro" : "Tema escuro"}
            >
              {escuro ? <Sun size={15} /> : <Moon size={15} />}
            </button>

            <div className="fin-menu-wrap" ref={menuRef}>
              <button
                className="fin-avatar-btn"
                onClick={() => setMenuAberto((v) => !v)}
                aria-haspopup="menu"
                aria-expanded={menuAberto}
                aria-label="Menu da conta"
              >
                {perfil?.foto ? (
                  <img src={perfil.foto} alt="" />
                ) : (
                  iniciais(perfil)
                )}
              </button>

              {menuAberto && (
                <div className="fin-menu" role="menu">
                  <div className="fin-menu__head">
                    <div className="fin-avatar-btn fin-avatar-btn--estatico">
                      {perfil?.foto ? <img src={perfil.foto} alt="" /> : iniciais(perfil)}
                    </div>
                    <div style={{ minWidth: 0 }}>
                      <div className="fin-menu__name">
                        {perfil?.nome || perfil?.email?.split("@")[0] || "Minha conta"}
                      </div>
                      <div className="fin-menu__mail">{perfil?.email}</div>
                    </div>
                  </div>

                  <button
                    className="fin-menu__item"
                    role="menuitem"
                    onClick={() => {
                      navigate("/app/configuracoes");
                      setMenuAberto(false);
                    }}
                  >
                    <Settings size={14} /> Configurações
                  </button>

                  <button className="fin-menu__item" role="menuitem" onClick={toggleTheme}>
                    {escuro ? <Sun size={14} /> : <Moon size={14} />}
                    {escuro ? "Tema claro" : "Tema escuro"}
                  </button>

                  <button
                    className="fin-menu__item fin-menu__item--exit"
                    role="menuitem"
                    onClick={sair}
                  >
                    <LogOut size={14} /> Sair
                  </button>
                </div>
              )}
            </div>
          </div>
        </header>

        <main className="fin-content">{children}</main>
      </div>

      <nav className="fin-bottomnav" aria-label="Navegação principal">
        {NAV.map(({ to, fim, icon: Icone, curto }) => (
          <NavLink
            key={to}
            to={to}
            end={fim}
            className={({ isActive }) => `fin-bottomnav__item${isActive ? " active" : ""}`}
          >
            <Icone size={17} />
            {curto}
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
