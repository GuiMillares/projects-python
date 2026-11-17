// Fluxo em três etapas, controlado por `step`:
//   login → setup2fa (primeiro acesso, com QR) → dashboard
//   login → 2fa       (acessos seguintes)      → dashboard
//
// O 2FA é obrigatório e não é decorativo: a sessão devolvida pelo login
// só abre as rotas de 2FA. Nenhum dado financeiro é acessível antes de o
// servidor validar o código (ver api/app.py → exige_sessao).

import {
  ArrowLeft,
  Check,
  Copy,
  ExternalLink,
  Eye,
  EyeOff,
  KeyRound,
  Loader2,
  ShieldCheck,
  Wallet,
} from "lucide-react";
import QRCode from "qrcode";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { limparToken } from "../services/api";
import {
  entrar,
  iniciarSetup2FA,
  sessaoValida,
  verificar2FA,
} from "../services/authService";

// Alturas do extrato decorativo do painel esquerdo. Fixas de propósito:
// é uma marca-d'água, não um gráfico, e não pode parecer dado real.
const LEDGER = [
  [34, "up"], [52, "up"], [28, "down"], [66, "up"], [41, "down"],
  [74, "up"], [37, "down"], [58, "up"], [46, "up"], [30, "down"],
];

export default function Login() {
  const navigate = useNavigate();

  const [step, setStep] = useState("login");
  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [mostrarSenha, setMostrarSenha] = useState(false);
  const [codigo, setCodigo] = useState("");
  const [qrDataUrl, setQrDataUrl] = useState("");
  const [otpauth, setOtpauth] = useState("");
  const [erro, setErro] = useState("");
  const [carregando, setCarregando] = useState(false);
  const codigoRef = useRef(null);

  // Token de uma sessão já completa (voltou para /login com o app aberto)
  // manda direto para o painel. Token parcial ou vencido é descartado:
  // a etapa em que ele parou não sobrevive ao reload, e repetir a senha é
  // mais seguro do que tentar adivinhar onde o fluxo estava.
  useEffect(() => {
    (async () => {
      if (await sessaoValida()) navigate("/app", { replace: true });
      else limparToken();
    })();
  }, [navigate]);

  useEffect(() => {
    if (step === "2fa" || step === "setup2fa") codigoRef.current?.focus();
  }, [step]);

  const abrirSetup2FA = async () => {
    const uri = await iniciarSetup2FA();
    setOtpauth(uri);
    setQrDataUrl(await QRCode.toDataURL(uri, { margin: 0, width: 320 }));
    setStep("setup2fa");
  };

  const handleEntrar = async (e) => {
    e.preventDefault();
    setErro("");
    setCarregando(true);
    try {
      const etapa = await entrar(email, senha);
      if (etapa === "setup2fa") await abrirSetup2FA();
      else setStep("2fa");
    } catch (err) {
      setErro(err.message);
      limparToken();
    } finally {
      setCarregando(false);
    }
  };

  // Uma função para as duas etapas: quem sabe se é cadastro ou verificação
  // é o servidor, que conhece o estado do segredo.
  const confirmarCodigo = async (e) => {
    e.preventDefault();
    setErro("");
    setCarregando(true);
    try {
      await verificar2FA(codigo);
      navigate("/app", { replace: true });
    } catch (err) {
      setErro(
        err.status === 401 && step === "setup2fa"
          ? "Código incorreto. Confira se o app leu o QR code."
          : err.message,
      );
      setCodigo("");
    } finally {
      setCarregando(false);
    }
  };

  const voltarParaLogin = () => {
    limparToken();
    setStep("login");
    setCodigo("");
    setSenha("");
    setQrDataUrl("");
    setOtpauth("");
    setErro("");
  };

  return (
    <div className="fin-login">
      <aside className="fin-login__aside">
        <div className="fin-login__mark">
          <Wallet size={17} /> Lastro
        </div>

        <div>
          <h1 className="fin-login__headline">
            Cada real, <em>onde você deixou</em>.
          </h1>
          <p className="fin-login__sub">
            Entradas, saídas, contas, investimentos e metas num lugar só, com a sua
            conta protegida em duas etapas.
          </p>
        </div>

        <div className="fin-login__ledger" aria-hidden="true">
          {LEDGER.map(([h, dir], i) => (
            <i key={i} className={dir} style={{ height: `${h}%` }} />
          ))}
        </div>
      </aside>

      <main className="fin-login__panel">
        <div className="fin-login__form-wrap">
          <div className="fin-login__brand-mobile">
            <Wallet size={16} /> Lastro
          </div>

          {step === "login" && (
            <>
              <h1 className="fin-login__title">Entrar</h1>
              <p className="fin-login__hint">Acesso ao seu painel financeiro.</p>

              {erro && <ErroBox texto={erro} />}

              <form className="fin-login__form" onSubmit={handleEntrar}>
                <div className="fin-field">
                  <label htmlFor="email">E-mail</label>
                  <input
                    id="email"
                    type="email"
                    autoComplete="username"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    required
                    autoFocus
                  />
                </div>

                <div className="fin-field">
                  <label htmlFor="senha">Senha</label>
                  <div className="fin-pwd">
                    <input
                      id="senha"
                      type={mostrarSenha ? "text" : "password"}
                      autoComplete="current-password"
                      value={senha}
                      onChange={(e) => setSenha(e.target.value)}
                      required
                    />
                    <button
                      type="button"
                      className="fin-pwd__toggle"
                      onClick={() => setMostrarSenha((v) => !v)}
                      aria-label={mostrarSenha ? "Ocultar senha" : "Mostrar senha"}
                    >
                      {mostrarSenha ? <EyeOff size={15} /> : <Eye size={15} />}
                    </button>
                  </div>
                </div>

                <button
                  type="submit"
                  className="fin-btn fin-btn--primary fin-btn--block"
                  disabled={carregando}
                  style={{ marginTop: 4 }}
                >
                  {carregando ? (
                    <>
                      <Loader2 size={14} className="fin-spin" /> Entrando...
                    </>
                  ) : (
                    "Entrar"
                  )}
                </button>
              </form>
            </>
          )}

          {step === "2fa" && (
            <>
              <div className="fin-login__step-head">
                <div className="fin-login__step-badge">
                  <ShieldCheck size={19} />
                </div>
                <div>
                  <h1 className="fin-login__title" style={{ marginBottom: 0 }}>
                    Código de acesso
                  </h1>
                  <span className="fin-field__hint">{email}</span>
                </div>
              </div>

              <p className="fin-login__hint">
                Abra seu autenticador e digite os 6 dígitos do momento.
              </p>

              {erro && <ErroBox texto={erro} />}

              <form className="fin-login__form" onSubmit={confirmarCodigo}>
                <CampoCodigo inputRef={codigoRef} valor={codigo} onChange={setCodigo} />

                <button
                  type="submit"
                  className="fin-btn fin-btn--primary fin-btn--block"
                  disabled={carregando || codigo.length < 6}
                >
                  {carregando ? (
                    <>
                      <Loader2 size={14} className="fin-spin" /> Verificando...
                    </>
                  ) : (
                    <>
                      <KeyRound size={14} /> Confirmar
                    </>
                  )}
                </button>

                <button
                  type="button"
                  className="fin-btn fin-btn--ghost fin-btn--block"
                  onClick={voltarParaLogin}
                >
                  <ArrowLeft size={14} /> Usar outra conta
                </button>
              </form>
            </>
          )}

          {step === "setup2fa" && (
            <>
              <div className="fin-login__step-head">
                <div className="fin-login__step-badge">
                  <ShieldCheck size={19} />
                </div>
                <div>
                  <h1 className="fin-login__title" style={{ marginBottom: 0 }}>
                    Proteger a conta
                  </h1>
                  <span className="fin-field__hint">primeiro acesso</span>
                </div>
              </div>

              <p className="fin-login__hint">
                Cadastre o Lastro num app autenticador (Google Authenticator, Authy, 1Password
                ou as Senhas do iPhone) e digite o código de 6 dígitos que ele mostrar. A partir
                daí o código é pedido a cada login.
              </p>

              {/* No celular não dá para ler o QR com o próprio celular: lá o
                  link e a chave vêm primeiro (ordem no CSS). */}
              <div className="fin-setup2fa">
                {qrDataUrl && (
                  <div className="fin-setup2fa__qr">
                    <span className="fin-setup2fa__rotulo">Em outro aparelho, leia o QR code:</span>
                    <img src={qrDataUrl} alt="QR code para configurar o autenticador" className="fin-qr" />
                  </div>
                )}
                {otpauth && <CadastroNoCelular uri={otpauth} />}
              </div>

              {erro && <ErroBox texto={erro} />}

              <form className="fin-login__form" onSubmit={confirmarCodigo} style={{ marginTop: 18 }}>
                <CampoCodigo inputRef={codigoRef} valor={codigo} onChange={setCodigo} />

                <button
                  type="submit"
                  className="fin-btn fin-btn--primary fin-btn--block"
                  disabled={carregando || codigo.length < 6}
                >
                  {carregando ? (
                    <>
                      <Loader2 size={14} className="fin-spin" /> Confirmando...
                    </>
                  ) : (
                    <>
                      <ShieldCheck size={14} /> Confirmar e entrar
                    </>
                  )}
                </button>

                <button
                  type="button"
                  className="fin-btn fin-btn--ghost fin-btn--block"
                  onClick={voltarParaLogin}
                >
                  <ArrowLeft size={14} /> Cancelar
                </button>
              </form>
            </>
          )}

          <p className="fin-login__legal">
            <Link to="/termos">Termos de uso</Link> · <Link to="/privacidade">Privacidade</Link>
          </p>
        </div>
      </main>
    </div>
  );
}

// Cadastro do autenticador no mesmo aparelho. O link otpauth:// abre o app
// autenticador instalado (no iPhone, também as Senhas do sistema). Se nada
// abrir, a chave vai à mão em "inserir chave de configuração".
function CadastroNoCelular({ uri }) {
  const [copiada, setCopiada] = useState(false);

  let chave = "";
  try {
    chave = new URL(uri).searchParams.get("secret") || "";
  } catch {
    chave = "";
  }
  // Em grupos de 4, como os apps mostram: menos chance de pular letra.
  const chaveLegivel = chave.replace(/(.{4})/g, "$1 ").trim();

  const copiar = async () => {
    try {
      await navigator.clipboard.writeText(chave);
      setCopiada(true);
      setTimeout(() => setCopiada(false), 2500);
    } catch {
      // Sem permissão de área de transferência: a chave segue na tela,
      // selecionável, para copiar à mão.
    }
  };

  return (
    <div className="fin-setup2fa__celular">
      <span className="fin-setup2fa__rotulo">Neste aparelho:</span>
      <a href={uri} className="fin-btn fin-btn--primary fin-btn--block">
        <ExternalLink size={14} /> Abrir no app autenticador
      </a>
      {chave && (
        <div className="fin-setup2fa__chave">
          <span className="fin-setup2fa__rotulo">
            Não abriu? No app, escolha inserir chave de configuração e use:
          </span>
          <div className="fin-setup2fa__chave-linha">
            <code className="fin-num">{chaveLegivel}</code>
            <button
              type="button"
              className="fin-icon-btn"
              onClick={copiar}
              aria-label="Copiar a chave"
              title="Copiar"
            >
              {copiada ? <Check size={14} /> : <Copy size={14} />}
            </button>
          </div>
        </div>
      )}
      <span className="fin-field__hint">
        Depois volte para cá e digite o código de 6 dígitos.
      </span>
    </div>
  );
}

function ErroBox({ texto }) {
  return (
    <div className="fin-alert fin-alert--error" role="alert" style={{ marginBottom: 14 }}>
      {texto}
    </div>
  );
}

function CampoCodigo({ inputRef, valor, onChange }) {
  return (
    <div className="fin-field">
      <label htmlFor="codigo">Código de 6 dígitos</label>
      <input
        id="codigo"
        ref={inputRef}
        type="text"
        inputMode="numeric"
        autoComplete="one-time-code"
        maxLength={6}
        className="fin-otp-input"
        placeholder="000000"
        value={valor}
        onChange={(e) => onChange(e.target.value.replace(/\D/g, "").slice(0, 6))}
        required
      />
    </div>
  );
}
