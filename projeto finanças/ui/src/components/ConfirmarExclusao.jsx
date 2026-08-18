// Modal de confirmação para exclusões.
//
// Um só componente para o app inteiro: metas, subtarefas, lançamentos e
// posições da carteira confirmam do mesmo jeito, com o botão de confirmar
// sempre em estilo de perigo e o Cancelar sempre com o foco inicial (Enter
// por reflexo cancela, não apaga).

import { Loader2, Trash2, TriangleAlert, X } from "lucide-react";
import { useEffect, useRef } from "react";

export default function ConfirmarExclusao({
  titulo,
  mensagem,
  rotuloConfirmar = "Excluir",
  ocupado = false,
  onConfirmar,
  onCancelar,
}) {
  const cancelarRef = useRef(null);

  useEffect(() => {
    // Foco no Cancelar, não no Excluir: quem aperta Enter sem ler mantém
    // o dado. Destruir precisa de intenção.
    cancelarRef.current?.focus();

    const tecla = (e) => {
      if (e.key === "Escape") onCancelar();
    };
    document.addEventListener("keydown", tecla);
    return () => document.removeEventListener("keydown", tecla);
  }, [onCancelar]);

  return (
    <div
      className="fin-modal-overlay"
      onMouseDown={(e) => {
        // Só o clique no próprio véu fecha; clique dentro do cartão não.
        if (e.target === e.currentTarget) onCancelar();
      }}
    >
      <div
        className="fin-modal"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="fin-modal-titulo"
      >
        <div className="fin-modal__cab">
          <span className="fin-modal__icone">
            <TriangleAlert size={17} />
          </span>
          <h2 id="fin-modal-titulo" className="fin-modal__titulo">
            {titulo}
          </h2>
        </div>

        <p className="fin-modal__texto">{mensagem}</p>

        <div className="fin-modal__acoes">
          <button
            ref={cancelarRef}
            type="button"
            className="fin-btn fin-btn--ghost"
            onClick={onCancelar}
            disabled={ocupado}
          >
            <X size={14} /> Cancelar
          </button>
          <button
            type="button"
            className="fin-btn fin-btn--danger"
            onClick={onConfirmar}
            disabled={ocupado}
          >
            {ocupado ? (
              <>
                <Loader2 size={14} className="fin-spin" /> Excluindo...
              </>
            ) : (
              <>
                <Trash2 size={14} /> {rotuloConfirmar}
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
