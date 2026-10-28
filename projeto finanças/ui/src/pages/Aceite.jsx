// Aceite dos termos de uso e da política de privacidade.
//
// Fica entre o login e o painel: a API devolve 428 em toda rota de dado
// enquanto a pessoa não aceitar a versão atual (ver exige_sessao), e esta
// tela é para onde o app manda nesse caso. O aceite vira uma linha com
// data e versão no banco, que é a prova do consentimento.
//
// Quem não aceita pode sair, ou apagar a conta: o direito de apagar não
// depende de aceitar nada.

import { Check, Loader2, LogOut, Trash2, TriangleAlert, Wallet } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import ApagarConta from "../components/ApagarConta";
import DocumentoTexto from "../components/DocumentoTexto";
import { sair } from "../services/authService";
import { aceitarDocumentos, carregarPerfil, lerDocumentos } from "../services/perfilService";

const RESUMO = [
  "O app só lê seus bancos, pelo Open Finance via Pluggy. Nunca movimenta dinheiro.",
  "Seus dados não são vendidos nem usados para publicidade. Pelo app, só você os vê.",
  "Pedir sugestão de passos para uma meta manda o texto dela para o Google Gemini.",
  "Você exporta ou apaga tudo quando quiser, em Configurações.",
];

export default function Aceite() {
  const navigate = useNavigate();

  const [docs, setDocs] = useState(null);
  const [perfil, setPerfil] = useState(null);
  const [aba, setAba] = useState("termos");
  const [li, setLi] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState("");
  const [apagando, setApagando] = useState(false);

  const carregar = useCallback(async () => {
    let p;
    try {
      p = await carregarPerfil();
    } catch {
      navigate("/login", { replace: true });
      return;
    }
    if (!p.aceitePendente) {
      navigate("/app", { replace: true });
      return;
    }
    setPerfil(p);
    try {
      setDocs(await lerDocumentos());
    } catch (e) {
      setErro(e.message);
    }
  }, [navigate]);

  useEffect(() => {
    carregar();
  }, [carregar]);

  const aceitar = async (e) => {
    e.preventDefault();
    setErro("");
    setEnviando(true);
    try {
      await aceitarDocumentos(docs.versao);
      navigate("/app", { replace: true });
    } catch (err) {
      setErro(err.message);
      // 409: o texto mudou enquanto a pessoa lia. Mostra o novo e pede de novo.
      if (err.status === 409) {
        setLi(false);
        setDocs(await lerDocumentos().catch(() => docs));
      }
      setEnviando(false);
    }
  };

  const recusar = async () => {
    await sair();
    navigate("/login", { replace: true });
  };

  if (!docs) {
    return (
      <div className="fin-legal">
        <div className="fin-loading">
          {erro ? <TriangleAlert size={17} /> : <Loader2 size={17} className="fin-spin" />}
          <span>{erro || "Carregando os termos..."}</span>
        </div>
      </div>
    );
  }

  return (
    <div className="fin-legal">
      <div className="fin-legal__col">
        <div className="fin-login__mark fin-legal__marca">
          <Wallet size={17} /> Finanças
        </div>

        <h1 className="fin-page-title">Antes de continuar</h1>
        <p className="fin-page-sub">
          {perfil?.aceite
            ? "Os termos de uso e a política de privacidade mudaram. Leia a versão nova."
            : "Leia como o app trata seus dados. O aceite fica registrado com a data e a versão."}
        </p>

        <ul className="fin-aceite__resumo">
          {RESUMO.map((r) => (
            <li key={r}>
              <Check size={13} /> <span>{r}</span>
            </li>
          ))}
        </ul>

        <div className="fin-seg" role="tablist">
          {[
            ["termos", "Termos de uso"],
            ["privacidade", "Política de privacidade"],
          ].map(([id, rotulo]) => (
            <button
              key={id}
              role="tab"
              aria-selected={aba === id}
              className={aba === id ? "active" : ""}
              onClick={() => setAba(id)}
            >
              {rotulo}
            </button>
          ))}
        </div>

        <div className="fin-aceite__leitura" tabIndex={0}>
          <DocumentoTexto doc={docs[aba]} versaoPorExtenso={docs.versaoPorExtenso} />
        </div>

        {erro && (
          <div className="fin-alert fin-alert--error" role="alert" style={{ marginTop: 12 }}>
            <TriangleAlert size={14} />
            <span>{erro}</span>
          </div>
        )}

        <form className="fin-aceite__form" onSubmit={aceitar}>
          <label className="fin-check-linha">
            <input type="checkbox" checked={li} onChange={(e) => setLi(e.target.checked)} />
            <span>
              Li e aceito os termos de uso e a política de privacidade, versão de{" "}
              {docs.versaoPorExtenso}.
            </span>
          </label>

          <div className="fin-form__actions">
            <button className="fin-btn fin-btn--primary" disabled={!li || enviando}>
              {enviando ? (
                <>
                  <Loader2 size={14} className="fin-spin" /> Registrando...
                </>
              ) : (
                <>
                  <Check size={14} /> Aceitar e continuar
                </>
              )}
            </button>
            <button type="button" className="fin-btn fin-btn--ghost" onClick={recusar}>
              <LogOut size={14} /> Não aceito, sair
            </button>
          </div>

          <button type="button" className="fin-aceite__apagar" onClick={() => setApagando(true)}>
            <Trash2 size={12} /> Prefiro apagar minha conta
          </button>
        </form>
      </div>

      {apagando && (
        <ApagarConta
          pedirCodigo={perfil?.twoFactorEnrolled}
          onCancelar={() => setApagando(false)}
        />
      )}
    </div>
  );
}
