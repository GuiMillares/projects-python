import { Check, Copy, ExternalLink } from "lucide-react";
import { useState } from "react";

// Cadastro do autenticador no mesmo aparelho (login e Configurações).
// Não dá para ler o QR code com o próprio celular. O link otpauth:// abre o
// autenticador instalado (no iPhone, também as Senhas do sistema). Se nada
// abrir, a chave vai à mão em "inserir chave de configuração".
export default function CadastroNoCelular({ uri }) {
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
