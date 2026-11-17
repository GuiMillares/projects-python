// Formulário de conta nova: nome, e-mail e senha. Usado no cadastro aberto
// (/cadastro) e no link de convite. Quem chama decide para onde vai o
// pedido (`criar` recebe {nome, email, senha} e devolve o token); daqui
// segue sempre para o cadastro do 2FA, como qualquer primeiro acesso.

import { Eye, EyeOff, Loader2, UserPlus } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { guardarToken } from "../services/api";

export default function FormCadastro({ criar }) {
  const navigate = useNavigate();
  const [nome, setNome] = useState("");
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [repetir, setRepetir] = useState("");
  const [mostrar, setMostrar] = useState(false);
  const [erro, setErro] = useState("");
  const [enviando, setEnviando] = useState(false);

  const enviar = async (e) => {
    e.preventDefault();
    setErro("");
    if (senha !== repetir) {
      setErro("As senhas não são iguais.");
      return;
    }
    setEnviando(true);
    try {
      const r = await criar({ nome: nome.trim(), email: email.trim(), senha });
      guardarToken(r.token);
      navigate("/login", { replace: true, state: { continuar: "setup2fa", email } });
    } catch (err) {
      setErro(err.message);
    } finally {
      setEnviando(false);
    }
  };

  return (
    <>
      {erro && (
        <div className="fin-alert fin-alert--error" role="alert" style={{ marginBottom: 14 }}>
          {erro}
        </div>
      )}

      <form className="fin-login__form" onSubmit={enviar}>
        <div className="fin-field">
          <label htmlFor="cad-nome">Seu nome</label>
          <input
            id="cad-nome"
            autoComplete="name"
            value={nome}
            onChange={(e) => setNome(e.target.value)}
            maxLength={120}
            required
          />
        </div>
        <div className="fin-field">
          <label htmlFor="cad-email">E-mail</label>
          <input
            id="cad-email"
            type="email"
            autoComplete="username"
            inputMode="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </div>
        <div className="fin-field">
          <label htmlFor="cad-senha">Senha</label>
          <div className="fin-pwd">
            <input
              id="cad-senha"
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
          <label htmlFor="cad-repetir">Repita a senha</label>
          <input
            id="cad-repetir"
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

        <button type="submit" className="fin-btn fin-btn--primary fin-btn--block" disabled={enviando}>
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
    </>
  );
}
