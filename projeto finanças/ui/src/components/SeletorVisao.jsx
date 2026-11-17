// Eu / cada pessoa do espaço / Juntos. Só aparece para quem está num espaço.

import { User, Users } from "lucide-react";
import { useVisao } from "../context/VisaoProvider";

export default function SeletorVisao() {
  const { visao, setVisao, membros, temEspaco } = useVisao();
  if (!temEspaco) return null;

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
