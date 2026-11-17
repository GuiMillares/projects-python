// Configurações → Espaço compartilhado (casal, família).
//
// Sem espaço: gera o link de convite (copiar ou compartilhar).
// Com convite recebido sem resposta: vincular ou não.
// Com espaço: quem está nele; quem administra convida e remove; todo
// mundo pode sair. As regras moram no servidor (api/espacos.py).

import { Check, Copy, Crown, Link2, Loader2, LogOut, Share2, Trash2, UserPlus, Users, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import ConfirmarExclusao from "./ConfirmarExclusao";
import {
  aceitarConvite,
  cancelarConvite,
  gerarConvite,
  lerEspaco,
  linkDoConvite,
  recusarConvite,
  removerMembro,
  sairDoEspaco,
} from "../services/espacoService";

const dataHora = (iso) =>
  new Date(iso).toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });

export default function EspacoCard({ avisar }) {
  const [dados, setDados] = useState(null);
  const [link, setLink] = useState("");
  const [ocupado, setOcupado] = useState(false);
  const [copiado, setCopiado] = useState(false);
  const [paraRemover, setParaRemover] = useState(null);
  const [saindo, setSaindo] = useState(false);
  const [erro, setErro] = useState("");
  const secaoRef = useRef(null);
  const { hash } = useLocation();

  const avisarRef = useRef(avisar);
  avisarRef.current = avisar;

  const carregar = () => {
    setErro("");
    lerEspaco()
      .then(setDados)
      .catch((e) => setErro(e.message));
  };

  useEffect(carregar, []);

  // Atalho do menu da conta e da tela inicial: /app/configuracoes#espaco
  useEffect(() => {
    if (hash === "#espaco") secaoRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [hash, dados]);

  const executar = async (acao, sucesso) => {
    setOcupado(true);
    try {
      const r = await acao();
      if (r && r.membros) setDados(r);
      else setDados(await lerEspaco());
      if (sucesso) avisar(sucesso);
      return true;
    } catch (e) {
      avisar(e.message, "error");
      return false;
    } finally {
      setOcupado(false);
    }
  };

  const convidar = async () => {
    setOcupado(true);
    try {
      const { token } = await gerarConvite();
      setLink(linkDoConvite(token));
      setDados(await lerEspaco());
    } catch (e) {
      avisar(e.message, "error");
    } finally {
      setOcupado(false);
    }
  };

  const copiar = async () => {
    try {
      await navigator.clipboard.writeText(link);
      setCopiado(true);
      setTimeout(() => setCopiado(false), 2500);
    } catch {
      avisar("Não consegui copiar. Selecione o link e copie à mão.", "error");
    }
  };

  // No celular abre a folha de compartilhar do sistema (WhatsApp etc.).
  const compartilhar = async () => {
    try {
      await navigator.share({
        title: "Convite para o Lastro",
        text: "Te convidei para dividirmos as finanças no Lastro:",
        url: link,
      });
    } catch {
      // Cancelado ou indisponível: o botão de copiar segue ali.
    }
  };

  if (!dados) {
    return (
      <section id="espaco" ref={secaoRef} className="fin-card fin-cfg-largo">
        <div className="fin-cfg-card__title">
          <Users size={15} /> Espaço compartilhado
        </div>
        {erro ? (
          <div className="fin-form__actions">
            <span className="fin-field__hint" style={{ flex: 1 }}>
              Não consegui abrir o espaço agora: {erro}
            </span>
            <button className="fin-btn fin-btn--ghost fin-btn--sm" onClick={carregar}>
              Tentar de novo
            </button>
          </div>
        ) : (
          <div className="fin-loading" style={{ padding: "8px 0" }}>
            <Loader2 size={15} className="fin-spin" />
          </div>
        )}
      </section>
    );
  }

  const { espaco, membros, maxMembros, conviteAberto, convitePendente } = dados;
  const souDono = espaco?.papel === "dono";
  const podeConvidar = !espaco || (souDono && membros.length < maxMembros);
  const outros = membros.filter((m) => !m.eu);

  return (
    <section id="espaco" ref={secaoRef} className="fin-card fin-cfg-largo">
      <div className="fin-cfg-card__title">
        <Users size={15} /> Espaço compartilhado
      </div>

      {/* Convite recebido, ainda sem resposta */}
      {!espaco && convitePendente && (
        <div className="fin-banner" style={{ "--bc": "var(--fin-accent)" }}>
          <Users size={16} />
          <span style={{ flex: 1 }}>
            {convitePendente.convidadoPor} te convidou para um espaço compartilhado.
          </span>
          <button
            className="fin-btn fin-btn--ghost fin-btn--sm"
            disabled={ocupado}
            onClick={() => executar(() => recusarConvite(convitePendente.id), "Convite recusado.")}
          >
            Não vincular
          </button>
          <button
            className="fin-btn fin-btn--primary fin-btn--sm"
            disabled={ocupado}
            onClick={async () => {
              if (await executar(() => aceitarConvite(convitePendente.id))) window.location.assign("/app");
            }}
          >
            <Check size={13} /> Vincular
          </button>
        </div>
      )}

      {!espaco ? (
        <p className="fin-field__hint" style={{ marginBottom: 12 }}>
          Convide seu par ou sua família (até {maxMembros} pessoas). Cada um vê o que é seu, o que é
          dos outros e o total de vocês juntos. Cada pessoa continua editando só o que é dela, e o
          que for marcado como privado fica de fora.
        </p>
      ) : (
        <ul className="fin-passkeys">
          {membros.map((m) => (
            <li key={m.id} className="fin-passkeys__item">
              {m.papel === "dono" ? (
                <Crown size={15} className="fin-passkeys__ico" />
              ) : (
                <Users size={15} className="fin-passkeys__ico" />
              )}
              <div className="fin-passkeys__corpo">
                <span className="fin-passkeys__nome">
                  {m.nome}
                  {m.eu ? " (você)" : ""}
                </span>
                <span className="fin-field__hint">
                  {m.email} · {m.papel === "dono" ? "administra" : "membro"} · desde{" "}
                  {dataHora(m.entrouEm)}
                </span>
              </div>
              {souDono && !m.eu && (
                <button
                  className="fin-lanc-item__excluir"
                  onClick={() => setParaRemover(m)}
                  aria-label={`Remover ${m.nome} do espaço`}
                  title="Remover do espaço"
                >
                  <Trash2 size={14} />
                </button>
              )}
            </li>
          ))}
        </ul>
      )}

      {/* Link gerado agora (o código só aparece uma vez, na hora) */}
      {link && (
        <div className="fin-setup2fa__chave" style={{ marginBottom: 12 }}>
          <span className="fin-setup2fa__rotulo">
            Mande este link para quem você quer convidar. Vale 7 dias e uma pessoa só:
          </span>
          <div className="fin-setup2fa__chave-linha">
            <code className="fin-num">{link}</code>
            <button type="button" className="fin-icon-btn" onClick={copiar} aria-label="Copiar o link" title="Copiar">
              {copiado ? <Check size={14} /> : <Copy size={14} />}
            </button>
          </div>
          {typeof navigator !== "undefined" && navigator.share && (
            <button type="button" className="fin-btn fin-btn--primary fin-btn--sm" onClick={compartilhar}>
              <Share2 size={13} /> Compartilhar
            </button>
          )}
        </div>
      )}

      {!link && conviteAberto && (
        <p className="fin-field__hint" style={{ marginBottom: 12 }}>
          <Link2 size={12} style={{ verticalAlign: -2 }} /> Há um link de convite seu ainda não usado,
          válido até {dataHora(conviteAberto.expiraEm)}. Gerar outro invalida esse.
        </p>
      )}

      <div className="fin-form__actions">
        {podeConvidar && (
          <button className="fin-btn fin-btn--primary fin-btn--sm" onClick={convidar} disabled={ocupado}>
            {ocupado ? <Loader2 size={13} className="fin-spin" /> : <UserPlus size={13} />}
            {link || conviteAberto ? "Gerar outro link" : espaco ? "Convidar mais alguém" : "Convidar meu par ou família"}
          </button>
        )}
        {(link || conviteAberto) && (
          <button
            className="fin-btn fin-btn--ghost fin-btn--sm"
            disabled={ocupado}
            onClick={async () => {
              if (await executar(cancelarConvite, "Link cancelado.")) setLink("");
            }}
          >
            <X size={13} /> Cancelar link
          </button>
        )}
        {espaco && (
          <button className="fin-btn fin-btn--danger fin-btn--sm" onClick={() => setSaindo(true)} disabled={ocupado}>
            <LogOut size={13} /> Sair do espaço
          </button>
        )}
      </div>

      {paraRemover && (
        <ConfirmarExclusao
          titulo={`Remover ${paraRemover.nome} do espaço?`}
          mensagem={`${paraRemover.nome} deixa de ver as finanças de vocês, e vocês deixam de ver as dela, na hora. Nada é apagado: cada um continua com os próprios dados.`}
          rotuloConfirmar="Remover"
          ocupado={ocupado}
          onConfirmar={async () => {
            if (await executar(() => removerMembro(paraRemover.id), "Pessoa removida do espaço.")) setParaRemover(null);
          }}
          onCancelar={() => setParaRemover(null)}
        />
      )}

      {saindo && (
        <ConfirmarExclusao
          titulo="Sair do espaço?"
          mensagem={
            outros.length === 1
              ? `Você e ${outros[0].nome} deixam de ver as finanças um do outro, na hora. Nada é apagado. Para voltar, é preciso um convite novo.`
              : "Você deixa de ver as finanças das outras pessoas, e elas as suas, na hora. Nada é apagado. Para voltar, é preciso um convite novo."
          }
          rotuloConfirmar="Sair"
          ocupado={ocupado}
          onConfirmar={async () => {
            if (await executar(sairDoEspaco, "Você saiu do espaço.")) setSaindo(false);
          }}
          onCancelar={() => setSaindo(false)}
        />
      )}
    </section>
  );
}
