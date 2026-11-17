// Convite para pôr o app na tela inicial do celular.
//
// Aparece só no celular, só fora do app instalado e só até a pessoa
// fechar. No Android vira o botão Instalar; no iPhone, o caminho pelo
// Safari, que é o único que existe lá.

import { Download, Share, SquarePlus, X } from "lucide-react";
import { useEffect, useState } from "react";
import { aoMudarConvite, ehIOS, instalar, jaInstalado, temConvite } from "../services/instalar";

const CHAVE = "fin_instalar_dispensado";

const dispensado = () => {
  try {
    return localStorage.getItem(CHAVE) === "1";
  } catch {
    return false;
  }
};

export default function InstalarApp() {
  const [fechado, setFechado] = useState(() => jaInstalado() || dispensado());
  const [convite, setConvite] = useState(temConvite);

  useEffect(() => aoMudarConvite(() => setConvite(temConvite())), []);

  const fechar = () => {
    setFechado(true);
    try {
      localStorage.setItem(CHAVE, "1");
    } catch {
      // Sem armazenamento (aba anônima): fecha só nesta visita.
    }
  };

  if (fechado) return null;

  const ios = ehIOS();
  if (!ios && !convite) return null;

  return (
    <div className="fin-banner fin-instalar" style={{ "--bc": "var(--fin-accent)" }}>
      <SquarePlus size={16} />
      <span style={{ flex: 1 }}>
        {ios ? (
          <>
            Use como app: no Safari, toque em <Share size={13} className="fin-instalar__ico" />{" "}
            Compartilhar e depois em <strong>Adicionar à Tela de Início</strong>.
          </>
        ) : (
          "Instale na tela inicial para abrir como app, sem a barra do navegador."
        )}
      </span>
      {!ios && (
        <button
          className="fin-btn fin-btn--primary fin-btn--sm"
          onClick={async () => {
            if (await instalar()) fechar();
          }}
        >
          <Download size={13} /> Instalar
        </button>
      )}
      <button className="fin-icon-btn" onClick={fechar} aria-label="Fechar aviso" title="Fechar">
        <X size={14} />
      </button>
    </div>
  );
}
