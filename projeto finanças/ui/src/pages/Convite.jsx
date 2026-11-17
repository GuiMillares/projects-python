// Página do link de convite: /convite/<código>.
//
// Três caminhos:
// * já está logado: o convite fica preso a esta conta e o app abre com a
//   pergunta "vincular?";
// * não tem conta: cria aqui (e-mail, nome, senha) e segue para o
//   cadastro do 2FA, como qualquer primeiro acesso;
// * tem conta mas não está logado: o código espera nesta aba e a pergunta
//   aparece depois do login.
//
// O vínculo em si nunca acontece nesta página: só depois que a pessoa
// entrou de verdade (com 2FA e aceite dos termos) e respondeu que sim.

import { Loader2, Users, Wallet } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import FormCadastro from "../components/FormCadastro";
import { sessaoValida } from "../services/authService";
import {
  cadastrarPorConvite,
  guardarConviteEmTransito,
  pegarConvite,
  verConvite,
} from "../services/espacoService";

export default function Convite() {
  const { token } = useParams();
  const navigate = useNavigate();

  const [convite, setConvite] = useState(null);
  const [falha, setFalha] = useState("");
  useEffect(() => {
    (async () => {
      // Logado: prende o convite à conta e vai para o app, onde a
      // pergunta aparece.
      const sessao = await sessaoValida();
      if (sessao === "ok") {
        try {
          await pegarConvite(token);
          navigate("/app", { replace: true });
        } catch (e) {
          setFalha(e.message);
        }
        return;
      }
      // Logado, mas falta aceitar a versão nova dos termos: o convite
      // espera e a pergunta aparece depois do aceite.
      if (sessao === "aceite") {
        guardarConviteEmTransito(token);
        navigate("/aceite", { replace: true });
        return;
      }
      try {
        setConvite(await verConvite(token));
      } catch (e) {
        setFalha(e.message);
      }
    })();
  }, [token, navigate]);

  const jaTenhoConta = () => {
    guardarConviteEmTransito(token);
    navigate("/login");
  };

  return (
    <div className="fin-login">
      <aside className="fin-login__aside">
        <div className="fin-login__mark">
          <Wallet size={17} /> Lastro
        </div>
        <div>
          <h1 className="fin-login__headline">
            As contas da casa, <em>juntas</em>.
          </h1>
          <p className="fin-login__sub">
            Cada um vê o que é seu, o que é do outro e o total de vocês. O que for privado fica
            de fora.
          </p>
        </div>
        <div />
      </aside>

      <main className="fin-login__panel">
        <div className="fin-login__form-wrap">
          <div className="fin-login__brand-mobile">
            <Wallet size={16} /> Lastro
          </div>

          {falha ? (
            <>
              <h1 className="fin-login__title">Convite</h1>
              <div className="fin-alert fin-alert--error" role="alert" style={{ marginBottom: 14 }}>
                {falha}
              </div>
              <Link to="/login" className="fin-btn fin-btn--ghost fin-btn--block">
                Ir para o login
              </Link>
            </>
          ) : !convite ? (
            <div className="fin-loading">
              <Loader2 size={17} className="fin-spin" />
            </div>
          ) : (
            <>
              <div className="fin-login__step-head">
                <div className="fin-login__step-badge">
                  <Users size={19} />
                </div>
                <div>
                  <h1 className="fin-login__title" style={{ marginBottom: 0 }}>
                    {convite.convidadoPor} te convidou
                  </h1>
                  <span className="fin-field__hint">para dividir as finanças no Lastro</span>
                </div>
              </div>

              <p className="fin-login__hint">
                Crie sua conta. Depois de entrar, você decide se vincula com{" "}
                {convite.convidadoPor}.
              </p>

              <FormCadastro criar={(dados) => cadastrarPorConvite(token, dados)} />

              <div className="fin-login__ou">
                <span>já tem conta no Lastro?</span>
              </div>
              <button type="button" className="fin-btn fin-btn--ghost fin-btn--block" onClick={jaTenhoConta}>
                Entrar e responder ao convite
              </button>
            </>
          )}
        </div>
      </main>
    </div>
  );
}
