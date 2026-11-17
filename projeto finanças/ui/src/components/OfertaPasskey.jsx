// Convite para ligar a passkey neste aparelho.
//
// Aparece só onde há leitor (Face ID, digital, Windows Hello), só se este
// aparelho ainda não tem passkey e só até a pessoa fechar. O cadastro em
// si fica em Configurações; aqui é o atalho.

import { Fingerprint, Loader2, X } from "lucide-react";
import { useEffect, useState } from "react";
import {
  aparelhoTemPasskey,
  cadastrarPasskey,
  marcarAparelho,
  temLeitorNoAparelho,
  textoDoErro,
} from "../services/passkeyService";

const CHAVE = "fin_passkey_dispensada";

const dispensada = () => {
  try {
    return localStorage.getItem(CHAVE) === "1";
  } catch {
    return false;
  }
};

export default function OfertaPasskey() {
  const [visivel, setVisivel] = useState(false);
  const [ocupado, setOcupado] = useState(false);
  const [aviso, setAviso] = useState("");
  const [pronto, setPronto] = useState(false);

  useEffect(() => {
    if (aparelhoTemPasskey() || dispensada()) return;
    temLeitorNoAparelho().then(setVisivel);
  }, []);

  const fechar = () => {
    setVisivel(false);
    try {
      localStorage.setItem(CHAVE, "1");
    } catch {
      // Sem armazenamento: fecha só nesta visita.
    }
  };

  const ativar = async () => {
    setAviso("");
    setOcupado(true);
    try {
      await cadastrarPasskey();
      setPronto(true);
      setTimeout(() => setVisivel(false), 3000);
    } catch (e) {
      if (e?.name === "InvalidStateError") {
        // O aparelho já tinha passkey deste app: só faltava a marca.
        marcarAparelho(true);
        setVisivel(false);
        return;
      }
      const texto = e?.status ? e.message : textoDoErro(e);
      if (texto) setAviso(texto);
    } finally {
      setOcupado(false);
    }
  };

  if (!visivel) return null;

  return (
    <div className="fin-banner fin-instalar" style={{ "--bc": "var(--fin-accent)" }}>
      <Fingerprint size={16} />
      <span style={{ flex: 1 }}>
        {pronto
          ? "Pronto. Na próxima vez, é só o Face ID ou a digital."
          : aviso || "Entrar com Face ID ou digital da próxima vez, sem senha nem código?"}
      </span>
      {!pronto && (
        <button className="fin-btn fin-btn--primary fin-btn--sm" onClick={ativar} disabled={ocupado}>
          {ocupado ? <Loader2 size={13} className="fin-spin" /> : <Fingerprint size={13} />} Ativar
        </button>
      )}
      <button className="fin-icon-btn" onClick={fechar} aria-label="Fechar aviso" title="Fechar">
        <X size={14} />
      </button>
    </div>
  );
}
