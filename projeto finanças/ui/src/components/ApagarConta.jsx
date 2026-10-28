// Apagar a conta: mesmo véu do ConfirmarExclusao, mas pedindo a senha (e o
// código, com o 2FA ativo). Uma sessão esquecida aberta não pode bastar
// para apagar tudo. Usado em Configurações e na tela de aceite: quem não
// aceita os termos também tem o direito de apagar o que é dele.

import { Loader2, Trash2, TriangleAlert, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { limparToken } from "../services/api";
import { apagarConta } from "../services/perfilService";

export default function ApagarConta({ pedirCodigo, onCancelar }) {
  const navigate = useNavigate();
  const senhaRef = useRef(null);

  const [senha, setSenha] = useState("");
  const [codigo, setCodigo] = useState("");
  const [ocupado, setOcupado] = useState(false);
  const [erro, setErro] = useState("");

  useEffect(() => {
    senhaRef.current?.focus();
    const tecla = (e) => {
      if (e.key === "Escape" && !ocupado) onCancelar();
    };
    document.addEventListener("keydown", tecla);
    return () => document.removeEventListener("keydown", tecla);
  }, [onCancelar, ocupado]);

  const confirmar = async (e) => {
    e.preventDefault();
    setErro("");
    setOcupado(true);
    try {
      await apagarConta(senha, pedirCodigo ? codigo : undefined);
      limparToken();
      navigate("/login", { replace: true });
    } catch (err) {
      setErro(err.message);
      setCodigo("");
      setOcupado(false);
    }
  };

  return (
    <div
      className="fin-modal-overlay"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget && !ocupado) onCancelar();
      }}
    >
      <form
        className="fin-modal"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="fin-apagar-titulo"
        onSubmit={confirmar}
      >
        <div className="fin-modal__cab">
          <span className="fin-modal__icone">
            <TriangleAlert size={17} />
          </span>
          <h2 id="fin-apagar-titulo" className="fin-modal__titulo">
            Apagar sua conta?
          </h2>
        </div>

        <p className="fin-modal__texto">
          Somem de vez seu perfil, lançamentos, orçamentos, investimentos, metas, regras e
          conexões. Não tem como desfazer. Se quiser guardar uma cópia, exporte seus dados antes.
          O consentimento do Open Finance continua no banco até você revogar no Meu Pluggy.
        </p>

        {erro && (
          <div className="fin-alert fin-alert--error" role="alert">
            <TriangleAlert size={14} />
            <span>{erro}</span>
          </div>
        )}

        <div className="fin-form fin-apagar__campos">
          <div className="fin-field">
            <label htmlFor="apagar-senha">Sua senha</label>
            <input
              id="apagar-senha"
              ref={senhaRef}
              type="password"
              autoComplete="current-password"
              value={senha}
              onChange={(e) => setSenha(e.target.value)}
              required
            />
          </div>
          {pedirCodigo && (
            <div className="fin-field">
              <label htmlFor="apagar-codigo">Código do autenticador</label>
              <input
                id="apagar-codigo"
                type="text"
                inputMode="numeric"
                autoComplete="one-time-code"
                maxLength={6}
                className="fin-otp-input"
                placeholder="000000"
                value={codigo}
                onChange={(e) => setCodigo(e.target.value.replace(/\D/g, "").slice(0, 6))}
                required
              />
            </div>
          )}
        </div>

        <div className="fin-modal__acoes">
          <button
            type="button"
            className="fin-btn fin-btn--ghost"
            onClick={onCancelar}
            disabled={ocupado}
          >
            <X size={14} /> Cancelar
          </button>
          <button
            className="fin-btn fin-btn--danger"
            disabled={ocupado || !senha || (pedirCodigo && codigo.length < 6)}
          >
            {ocupado ? (
              <>
                <Loader2 size={14} className="fin-spin" /> Apagando...
              </>
            ) : (
              <>
                <Trash2 size={14} /> Apagar tudo
              </>
            )}
          </button>
        </div>
      </form>
    </div>
  );
}
