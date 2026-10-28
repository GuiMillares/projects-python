// /termos e /privacidade: o texto inteiro, aberto sem login. O login, a tela
// de aceite e as Configurações apontam para cá.

import { ArrowLeft, Loader2, TriangleAlert, Wallet } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import DocumentoTexto from "../components/DocumentoTexto";
import { lerDocumentos } from "../services/perfilService";

export default function Documento({ tipo }) {
  const navigate = useNavigate();
  const [docs, setDocs] = useState(null);
  const [erro, setErro] = useState("");

  useEffect(() => {
    lerDocumentos()
      .then(setDocs)
      .catch((e) => setErro(e.message));
  }, []);

  // Veio de outra tela do app: volta para ela. Abriu o link direto: login.
  const voltar = () => (window.history.length > 1 ? navigate(-1) : navigate("/login"));

  return (
    <div className="fin-legal">
      <div className="fin-legal__col">
        <div className="fin-legal__topo">
          <div className="fin-login__mark">
            <Wallet size={17} /> Finanças
          </div>
          <button className="fin-btn fin-btn--ghost fin-btn--sm" onClick={voltar}>
            <ArrowLeft size={13} /> Voltar
          </button>
        </div>

        {docs ? (
          <div className="fin-card fin-legal__papel">
            <DocumentoTexto doc={docs[tipo]} versaoPorExtenso={docs.versaoPorExtenso} />
          </div>
        ) : (
          <div className="fin-loading">
            {erro ? <TriangleAlert size={17} /> : <Loader2 size={17} className="fin-spin" />}
            <span>{erro || "Carregando..."}</span>
          </div>
        )}
      </div>
    </div>
  );
}
