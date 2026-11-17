// A pergunta "vincular?" de quem pegou um convite.
//
// Aparece ao entrar no app quando há convite pendente: o que veio por
// link nesta aba (quem tinha conta e passou pelo login) ou o que ficou
// preso à conta no cadastro. Fechar no X deixa para depois (a pergunta
// volta na próxima abertura e fica também em Configurações); "Não
// vincular" desfaz o convite.

import { Check, Loader2, Users, X } from "lucide-react";
import { useEffect, useState } from "react";
import {
  aceitarConvite,
  lerEspaco,
  pegarConvite,
  recusarConvite,
  tirarConviteEmTransito,
} from "../services/espacoService";

export default function PerguntaVinculo() {
  const [convite, setConvite] = useState(null);
  const [ocupado, setOcupado] = useState(false);
  const [erro, setErro] = useState("");

  useEffect(() => {
    (async () => {
      const emTransito = tirarConviteEmTransito();
      if (emTransito) {
        try {
          await pegarConvite(emTransito);
        } catch (e) {
          setErro(e.message);
        }
      }
      try {
        const r = await lerEspaco();
        if (r.convitePendente && !r.espaco) setConvite(r.convitePendente);
      } catch {
        // Sem espaço para ler, sem pergunta: nada a fazer aqui.
      }
    })();
  }, []);

  if (!convite) {
    return erro ? (
      <div className="fin-banner" style={{ "--bc": "var(--fin-warn)" }}>
        <Users size={16} />
        <span style={{ flex: 1 }}>{erro}</span>
        <button className="fin-icon-btn" onClick={() => setErro("")} aria-label="Fechar aviso">
          <X size={14} />
        </button>
      </div>
    ) : null;
  }

  const responder = async (sim) => {
    setOcupado(true);
    setErro("");
    try {
      if (sim) {
        await aceitarConvite(convite.id);
        // Recarrega para todas as telas lerem o espaço novo.
        window.location.assign("/app");
        return;
      }
      await recusarConvite(convite.id);
      setConvite(null);
    } catch (e) {
      setErro(e.message);
    } finally {
      setOcupado(false);
    }
  };

  const nome = convite.convidadoPor;

  return (
    <div className="fin-modal-overlay">
      <div className="fin-modal" role="dialog" aria-modal="true" aria-labelledby="vinculo-titulo">
        <div className="fin-modal__cab">
          <span className="fin-modal__icone fin-modal__icone--acento">
            <Users size={17} />
          </span>
          <h2 id="vinculo-titulo" className="fin-modal__titulo">
            Vincular com {nome}?
          </h2>
        </div>

        <p className="fin-modal__texto">
          {nome} te convidou para um espaço compartilhado no Lastro. Vinculando:
        </p>
        <ul className="fin-modal__lista">
          <li>
            vocês veem as contas, lançamentos, investimentos e metas um do outro, e o total de
            vocês juntos;
          </li>
          <li>cada um continua editando só o que é seu;</li>
          <li>o que você marcar como privado fica fora da visão de {nome};</li>
          <li>dá para sair do espaço quando quiser, em Configurações.</li>
        </ul>

        {erro && (
          <div className="fin-alert fin-alert--error" role="alert" style={{ marginBottom: 12 }}>
            {erro}
          </div>
        )}

        <div className="fin-modal__acoes">
          <button
            type="button"
            className="fin-btn fin-btn--ghost"
            onClick={() => responder(false)}
            disabled={ocupado}
          >
            Não vincular
          </button>
          <button
            type="button"
            className="fin-btn fin-btn--primary"
            onClick={() => responder(true)}
            disabled={ocupado}
          >
            {ocupado ? <Loader2 size={14} className="fin-spin" /> : <Check size={14} />} Vincular
          </button>
        </div>
        <button
          type="button"
          className="fin-icon-btn fin-modal__fechar"
          onClick={() => setConvite(null)}
          aria-label="Responder depois"
          title="Responder depois"
        >
          <X size={14} />
        </button>
      </div>
    </div>
  );
}
