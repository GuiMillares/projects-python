// Criar conta sem convite: /cadastro.
//
// Depois daqui o caminho é o de qualquer primeiro acesso: cadastro do 2FA
// (no próprio celular, se for o caso), aceite dos termos e o passo a passo
// de Contas para ligar a Pluggy. Quem tem um link de convite cai em
// /convite/<código>, que usa o mesmo formulário e já prende o convite.

import { ShieldCheck, UserPlus, Wallet } from "lucide-react";
import { Link } from "react-router-dom";
import FormCadastro from "../components/FormCadastro";
import { criarConta } from "../services/authService";

export default function Cadastro() {
  return (
    <div className="fin-login">
      <aside className="fin-login__aside">
        <div className="fin-login__mark">
          <Wallet size={17} /> Lastro
        </div>
        <div>
          <h1 className="fin-login__headline">
            Comece pelo que <em>é seu</em>.
          </h1>
          <p className="fin-login__sub">
            Conecte seus bancos pela Pluggy, veja entradas, saídas e faturas num lugar só e,
            quando quiser, divida com seu par.
          </p>
        </div>
        <div />
      </aside>

      <main className="fin-login__panel">
        <div className="fin-login__form-wrap">
          <div className="fin-login__brand-mobile">
            <Wallet size={16} /> Lastro
          </div>

          <div className="fin-login__step-head">
            <div className="fin-login__step-badge">
              <UserPlus size={19} />
            </div>
            <div>
              <h1 className="fin-login__title" style={{ marginBottom: 0 }}>
                Criar conta
              </h1>
              <span className="fin-field__hint">leva um minuto</span>
            </div>
          </div>

          <p className="fin-login__hint">
            <ShieldCheck size={13} style={{ verticalAlign: "-2px" }} /> Em seguida você liga a
            verificação em duas etapas com um app autenticador. Dá para fazer tudo pelo celular.
          </p>

          <FormCadastro criar={criarConta} />

          <p className="fin-login__cadastro">
            Já tem conta? <Link to="/login">Entrar</Link>
          </p>
        </div>
      </main>
    </div>
  );
}
