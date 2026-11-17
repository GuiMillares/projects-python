// Configurações → Notificações: ligar neste aparelho, escolher o que
// receber e mandar um teste. O que dispara cada aviso mora no servidor
// (api/notificacoes.py): transações novas pelo webhook da Pluggy e faturas
// pela rotina diária.

import { Bell, BellOff, Check, Loader2, Send, Smartphone } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { apelidoDoAparelho } from "../services/passkeyService";
import { ativar, desativar, enviarTeste, impedimento, lerEstado, salvarPreferencias } from "../services/pushService";

const TEXTO_IMPEDIMENTO = {
  iosSemInstalar:
    "No iPhone, as notificações só funcionam com o Lastro instalado: no Safari, Compartilhar e depois Adicionar à Tela de Início. Abra pelo ícone e volte aqui.",
  semSuporte: "Este navegador não recebe notificações push.",
  negado:
    "As notificações do Lastro estão bloqueadas neste aparelho. Libere nos ajustes do navegador (ou do sistema) e volte aqui.",
};

const OPCOES = [
  ["entradas", "Entradas", "Dinheiro que entrou nas contas"],
  ["saidas", "Saídas", "Compras, Pix e débitos"],
  ["faturas", "Faturas vencendo", "3 dias antes, na véspera e no dia"],
];

export default function NotificacoesCard({ avisar }) {
  const [estado, setEstado] = useState(null);
  const [ocupado, setOcupado] = useState(false);
  const [erro, setErro] = useState("");
  const bloqueio = impedimento();

  const avisarRef = useRef(avisar);
  avisarRef.current = avisar;

  const recarregar = () =>
    lerEstado()
      .then((e) => {
        setErro("");
        setEstado(e);
      })
      .catch((e) => {
        setErro(e.message);
        avisarRef.current(e.message, "error");
      });

  useEffect(() => {
    recarregar();
  }, []);

  const ligar = async () => {
    setOcupado(true);
    try {
      const r = await ativar(estado.chavePublica, apelidoDoAparelho());
      await recarregar();
      avisar(
        r.bancos === "ok"
          ? "Notificações ligadas neste aparelho."
          : "Notificações ligadas. Os avisos de transação chegam pela rotina diária até a Pluggy confirmar o webhook.",
      );
    } catch (e) {
      avisar(e.message, "error");
    } finally {
      setOcupado(false);
    }
  };

  const desligar = async () => {
    setOcupado(true);
    try {
      await desativar();
      await recarregar();
      avisar("Notificações desligadas neste aparelho.");
    } catch (e) {
      avisar(e.message, "error");
    } finally {
      setOcupado(false);
    }
  };

  const alternar = async (tipo) => {
    const novas = { ...estado.preferencias, [tipo]: !estado.preferencias[tipo] };
    setEstado({ ...estado, preferencias: novas });
    try {
      await salvarPreferencias({ [tipo]: novas[tipo] });
    } catch (e) {
      avisar(e.message, "error");
      recarregar();
    }
  };

  const testar = async () => {
    setOcupado(true);
    try {
      await enviarTeste();
      avisar("Teste enviado. Deve chegar em alguns segundos.");
    } catch (e) {
      avisar(e.message, "error");
    } finally {
      setOcupado(false);
    }
  };

  return (
    <section className="fin-card">
      <div className="fin-cfg-card__title">
        <Bell size={15} /> Notificações
      </div>

      {!estado && erro ? (
        <div className="fin-form__actions">
          <span className="fin-field__hint" style={{ flex: 1 }}>
            Não consegui abrir as notificações agora: {erro}
          </span>
          <button className="fin-btn fin-btn--ghost fin-btn--sm" onClick={recarregar}>
            Tentar de novo
          </button>
        </div>
      ) : !estado ? (
        <div className="fin-loading" style={{ padding: "8px 0" }}>
          <Loader2 size={15} className="fin-spin" />
        </div>
      ) : !estado.disponivel ? (
        <p className="fin-field__hint">O servidor ainda não está pronto para enviar notificações.</p>
      ) : (
        <>
          <p className="fin-field__hint" style={{ marginBottom: 12 }}>
            Avisos de entradas, saídas e faturas vencendo, mesmo com o app fechado. As transações
            chegam quando o seu banco sincroniza com a Pluggy (no Meu Pluggy, uma vez por dia).
          </p>

          {bloqueio && !estado.esteAparelho ? (
            <div className="fin-banner" style={{ "--bc": "var(--fin-warn)" }}>
              <Smartphone size={16} />
              <span>{TEXTO_IMPEDIMENTO[bloqueio]}</span>
            </div>
          ) : (
            <div className="fin-form__actions" style={{ marginBottom: 12 }}>
              {estado.esteAparelho ? (
                <>
                  <span className="fin-status-pill" style={{ "--pc": "var(--fin-in)" }}>
                    <Check size={12} /> Ligadas neste aparelho
                  </span>
                  <button className="fin-btn fin-btn--ghost fin-btn--sm" onClick={testar} disabled={ocupado}>
                    <Send size={13} /> Enviar teste
                  </button>
                  <button className="fin-btn fin-btn--ghost fin-btn--sm" onClick={desligar} disabled={ocupado}>
                    <BellOff size={13} /> Desligar aqui
                  </button>
                </>
              ) : (
                <button className="fin-btn fin-btn--primary fin-btn--sm" onClick={ligar} disabled={ocupado}>
                  {ocupado ? <Loader2 size={13} className="fin-spin" /> : <Bell size={13} />} Ativar neste
                  aparelho
                </button>
              )}
            </div>
          )}

          {estado.aparelhos > 0 && (
            <ul className="fin-passkeys">
              {OPCOES.map(([tipo, rotulo, ajuda]) => (
                <li key={tipo} className="fin-passkeys__item">
                  <label className="fin-notif-opcao">
                    <input
                      type="checkbox"
                      checked={estado.preferencias[tipo]}
                      onChange={() => alternar(tipo)}
                    />
                    <span className="fin-passkeys__corpo">
                      <span className="fin-passkeys__nome">{rotulo}</span>
                      <span className="fin-field__hint">{ajuda}</span>
                    </span>
                  </label>
                </li>
              ))}
            </ul>
          )}

          {estado.aparelhos > 0 && (
            <p className="fin-field__hint">
              {estado.aparelhos} {estado.aparelhos === 1 ? "aparelho recebe" : "aparelhos recebem"}.{" "}
              {estado.bancosAvisam
                ? "A Pluggy avisa o Lastro quando chegam transações novas."
                : "Transações novas são conferidas uma vez por dia (cadastre a credencial da Pluggy em Contas para receber assim que chegarem)."}
            </p>
          )}
        </>
      )}
    </section>
  );
}
