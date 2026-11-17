// Eu / cada pessoa do espaço / Juntos. Quem ainda não está num espaço vê,
// na tela inicial, só o atalho para convidar (prop convite).

import { User, UserPlus, Users } from "lucide-react";
import { Link } from "react-router-dom";
import { useVisao } from "../context/VisaoProvider";

export default function SeletorVisao({ convite = false }) {
  const { visao, setVisao, membros, temEspaco, carregado } = useVisao();
  if (!temEspaco) {
    if (!convite || !carregado) return null;
    return (
      <Link to="/app/configuracoes#espaco" className="fin-btn fin-btn--ghost fin-btn--sm fin-visao">
        <UserPlus size={13} /> Convidar seu par
      </Link>
    );
  }

  const opcoes = [
    { valor: "eu", rotulo: "Eu", icone: User },
    ...membros.filter((m) => !m.eu).map((m) => ({ valor: String(m.id), rotulo: m.nome, icone: User })),
    { valor: "juntos", rotulo: "Juntos", icone: Users },
  ];

  return (
    <div className="fin-seg fin-visao" role="radiogroup" aria-label="De quem ver os números">
      {opcoes.map(({ valor, rotulo, icone: Icone }) => (
        <button
          key={valor}
          role="radio"
          aria-checked={visao === valor}
          className={visao === valor ? "active" : ""}
          onClick={() => setVisao(valor)}
        >
          <Icone size={13} /> {rotulo}
        </button>
      ))}
    </div>
  );
}
