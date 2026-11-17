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

import { Eye, EyeOff, Loader2, UserPlus, Users, Wallet } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { guardarToken } from "../services/api";
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
  const [nome, setNome] = useState("");
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [repetir, setRepetir] = useState("");
  const [mostrar, setMostrar] = useState(false);
  const [erro, setErro] = useState("");
  const [enviando, setEnviando] = useState(false);

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

  const criarConta = async (e) => {
    e.preventDefault();
    setErro("");
    if (senha !== repetir) {
      setErro("As senhas não são iguais.");
      return;
    }
    setEnviando(true);
    try {
      const r = await cadastrarPorConvite(token, { nome, email, senha });
      guardarToken(r.token);
      navigate("/login", { replace: true, state: { continuar: "setup2fa", email } });
    } catch (err) {
      setErro(err.message);
    } finally {
      setEnviando(false);
    }
  };

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

              {erro && (
                <div className="fin-alert fin-alert--error" role="alert" style={{ marginBottom: 14 }}>
                  {erro}
                </div>
              )}

              <form className="fin-login__form" onSubmit={criarConta}>
                <div className="fin-field">
                  <label htmlFor="cv-nome">Seu nome</label>
                  <input
                    id="cv-nome"
                    autoComplete="name"
                    value={nome}
                    onChange={(e) => setNome(e.target.value)}
                    maxLength={120}
                    required
                  />
                </div>
                <div className="fin-field">
                  <label htmlFor="cv-email">E-mail</label>
                  <input
                    id="cv-email"
                    type="email"
                    autoComplete="username"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    required
                  />
                </div>
                <div className="fin-field">
                  <label htmlFor="cv-senha">Senha</label>
                  <div className="fin-pwd">
                    <input
                      id="cv-senha"
                      type={mostrar ? "text" : "password"}
                      autoComplete="new-password"
                      value={senha}
                      onChange={(e) => setSenha(e.target.value)}
                      minLength={8}
                      required
                    />
                    <button
                      type="button"
                      className="fin-pwd__toggle"
                      onClick={() => setMostrar((v) => !v)}
                      aria-label={mostrar ? "Ocultar senha" : "Mostrar senha"}
                    >
                      {mostrar ? <EyeOff size={15} /> : <Eye size={15} />}
                    </button>
                  </div>
                  <span className="fin-field__hint">Pelo menos 8 caracteres.</span>
                </div>
                <div className="fin-field">
                  <label htmlFor="cv-repetir">Repita a senha</label>
                  <input
                    id="cv-repetir"
                    type={mostrar ? "text" : "password"}
                    autoComplete="new-password"
                    value={repetir}
                    onChange={(e) => setRepetir(e.target.value)}
                    required
                  />
                </div>

                <p className="fin-field__hint">
                  Ao criar a conta você vai aceitar os{" "}
                  <Link to="/termos" target="_blank">
                    Termos de uso
                  </Link>{" "}
                  e a{" "}
                  <Link to="/privacidade" target="_blank">
                    Política de privacidade
                  </Link>{" "}
                  no primeiro acesso.
                </p>

                <button
                  type="submit"
                  className="fin-btn fin-btn--primary fin-btn--block"
                  disabled={enviando}
                >
                  {enviando ? (
                    <>
                      <Loader2 size={14} className="fin-spin" /> Criando...
                    </>
                  ) : (
                    <>
                      <UserPlus size={14} /> Criar minha conta
                    </>
                  )}
                </button>
              </form>

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
