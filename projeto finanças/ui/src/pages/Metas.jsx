// Metas gamificadas.
//
// Cada subtarefa concluída dá XP; concluir a meta inteira dá um bônus maior
// que a soma das subtarefas dela (regra em api/gamificacao.py), então nunca
// compensa parar com tudo feito menos o fim.
//
// O XP não é guardado no banco: deriva do que está marcado. As rotas que
// mudam conclusão devolvem o personagem recalculado, e é por isso que dá
// para atualizar a barra sem recarregar a lista toda.
//
// O nível vira aparência em services/niveis.js: 300 combinações únicas de
// patamar + divisão + pips. Aqui só se desenha o que aquele módulo decide.

import {
  Award,
  Check,
  Coins,
  Crown,
  Diamond,
  Gem,
  Hammer,
  Leaf,
  Loader2,
  Medal,
  Mountain,
  Plus,
  Shield,
  Sparkles,
  Sprout,
  Star,
  Target,
  Trash2,
  TreePine,
  Trophy,
  X,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import ConfirmarExclusao from "../components/ConfirmarExclusao";
import { brl } from "../services/financasService";
import {
  alternarSubtarefa,
  apagarMeta,
  apagarSubtarefa,
  atualizarMeta,
  criarMeta,
  criarSubtarefa,
  gerarSubtarefas,
  listarMetas,
  progressoDaMeta,
} from "../services/metasService";
import { infoDoNivel } from "../services/niveis";

// niveis.js guarda o ícone como string para ser testável no Node puro;
// a tradução para componente acontece só aqui.
const ICONES = {
  Sprout,
  Leaf,
  TreePine,
  Mountain,
  Medal,
  Coins,
  Hammer,
  Shield,
  Award,
  Trophy,
  Gem,
  Diamond,
  Sparkles,
  Star,
  Crown,
};

const formularioVazio = () => ({
  titulo: "",
  descricao: "",
  alvo: "",
  prazo: "",
  gerarSubtarefas: true,
});

export default function Metas() {
  const navigate = useNavigate();

  const [metas, setMetas] = useState([]);
  const [personagem, setPersonagem] = useState(null);
  const [iaDisponivel, setIaDisponivel] = useState(false);
  const [carregando, setCarregando] = useState(true);
  const [falha, setFalha] = useState("");
  const [toast, setToast] = useState(null);

  const [filtro, setFiltro] = useState("andamento");
  const [formAberto, setFormAberto] = useState(false);
  const [form, setForm] = useState(formularioVazio);
  const [salvando, setSalvando] = useState(false);
  const [gerando, setGerando] = useState(null);
  const [ocupada, setOcupada] = useState(null);
  const [novaSub, setNovaSub] = useState({});

  // O que está aguardando confirmação de exclusão no modal:
  // { tipo: "meta" | "sub", item } ou null quando fechado.
  const [exclusao, setExclusao] = useState(null);
  const [excluindo, setExcluindo] = useState(false);

  const avisar = (msg, tipo = "success") => {
    setToast({ msg, tipo });
    setTimeout(() => setToast(null), 4000);
  };

  const carregar = async () => {
    try {
      const r = await listarMetas();
      setMetas(r.metas || []);
      setPersonagem(r.personagem);
      setIaDisponivel(r.iaDisponivel);
      setFalha("");
    } catch (e) {
      if (e.status === 401 || e.status === 403) {
        navigate("/login", { replace: true });
        return;
      }
      setFalha(e.message || "Erro ao carregar as metas.");
    } finally {
      setCarregando(false);
    }
  };

  useEffect(() => {
    carregar();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const resumo = useMemo(() => {
    const ativas = metas.filter((m) => !m.concluida);
    const subs = metas.flatMap((m) => m.subtarefas);
    return {
      ativas: ativas.length,
      concluidas: metas.length - ativas.length,
      subsFeitas: subs.filter((s) => s.concluida).length,
      subsTotal: subs.length,
    };
  }, [metas]);

  // A lista obedece o filtro; os KPIs e o personagem continuam globais.
  const visiveis = useMemo(
    () => metas.filter((m) => (filtro === "concluidas" ? m.concluida : !m.concluida)),
    [metas, filtro],
  );

  const salvar = async (e) => {
    e.preventDefault();
    setSalvando(true);
    try {
      const r = await criarMeta(form);
      setForm(formularioVazio());
      setFormAberto(false);
      setFiltro("andamento");
      await carregar();
      // A meta é criada mesmo quando a IA falha; o aviso conta o porquê.
      if (r.aviso) avisar(r.aviso, "error");
      else avisar("Meta criada.");
    } catch (err) {
      avisar(err.message, "error");
    } finally {
      setSalvando(false);
    }
  };

  const gerarPassos = async (meta) => {
    setGerando(meta.id);
    try {
      const r = await gerarSubtarefas(meta.id);
      await carregar();
      if (r.aviso) avisar(r.aviso, "error");
      else avisar(`${r.criadas} ${r.criadas === 1 ? "passo sugerido" : "passos sugeridos"}.`);
    } catch (err) {
      avisar(err.message, "error");
    } finally {
      setGerando(null);
    }
  };

  const alternar = async (meta, sub) => {
    setOcupada(`s${sub.id}`);
    // Atualiza a tela na hora e ajusta com a resposta: marcar uma caixa
    // precisa responder no clique, não depois da ida ao servidor.
    setMetas((lista) =>
      lista.map((m) =>
        m.id !== meta.id
          ? m
          : {
              ...m,
              subtarefas: m.subtarefas.map((s) =>
                s.id === sub.id ? { ...s, concluida: !s.concluida } : s,
              ),
            },
      ),
    );
    try {
      const r = await alternarSubtarefa(sub.id, !sub.concluida);
      setPersonagem(r.personagem);
    } catch (err) {
      avisar(err.message, "error");
      await carregar();
    } finally {
      setOcupada(null);
    }
  };

  const concluirMeta = async (meta) => {
    setOcupada(`m${meta.id}`);
    try {
      const r = await atualizarMeta(meta.id, { concluida: !meta.concluida });
      const nivelAntes = personagem?.nivel ?? 1;
      setPersonagem(r.personagem);
      await carregar();
      if (!meta.concluida) {
        avisar(
          r.personagem.nivel > nivelAntes
            ? `Meta concluída, +${meta.bonusXp} XP. Subiu para ${infoDoNivel(r.personagem.nivel).rotulo}.`
            : `Meta concluída, +${meta.bonusXp} XP. Ela foi para a aba Concluídas.`,
        );
      }
    } catch (err) {
      avisar(err.message, "error");
    } finally {
      setOcupada(null);
    }
  };

  const adicionarSub = async (meta, e) => {
    e.preventDefault();
    const titulo = (novaSub[meta.id] || "").trim();
    if (!titulo) return;
    try {
      await criarSubtarefa(meta.id, titulo);
      setNovaSub((n) => ({ ...n, [meta.id]: "" }));
      await carregar();
    } catch (err) {
      avisar(err.message, "error");
    }
  };

  // A exclusão de verdade só roda depois do modal confirmar.
  const confirmarExclusao = async () => {
    if (!exclusao) return;
    setExcluindo(true);
    try {
      if (exclusao.tipo === "meta") {
        await apagarMeta(exclusao.item.id);
        avisar("Meta removida.");
      } else {
        await apagarSubtarefa(exclusao.item.id);
        avisar("Passo removido.");
      }
      await carregar();
      setExclusao(null);
    } catch (err) {
      avisar(err.message, "error");
    } finally {
      setExcluindo(false);
    }
  };

  const textoDaExclusao = () => {
    if (!exclusao) return { titulo: "", mensagem: "" };
    if (exclusao.tipo === "meta") {
      const m = exclusao.item;
      const n = m.subtarefas.length;
      const xpGanho =
        m.subtarefas.filter((s) => s.concluida).reduce((soma, s) => soma + s.xp, 0) +
        (m.concluida ? m.bonusXp : 0);
      return {
        titulo: `Excluir a meta "${m.titulo}"?`,
        mensagem:
          (n > 0
            ? `Os ${n} ${n === 1 ? "passo dela também será apagado" : "passos dela também serão apagados"}. `
            : "") +
          (xpGanho > 0
            ? `Os ${xpGanho} XP que ela rendeu saem do seu total. `
            : "") +
          "Não dá para desfazer.",
      };
    }
    const s = exclusao.item;
    return {
      titulo: `Excluir o passo "${s.titulo}"?`,
      mensagem:
        (s.concluida ? `Os ${s.xp} XP dele saem do seu total. ` : "") +
        "Não dá para desfazer.",
    };
  };

  if (carregando) {
    return (
      <div className="fin-loading">
        <Loader2 size={17} className="fin-spin" />
        <span>Carregando suas metas...</span>
      </div>
    );
  }

  const nivelInfo = infoDoNivel(personagem?.nivel ?? 1);
  const IconePatamar = ICONES[nivelInfo.icone] ?? Sprout;

  return (
    <>
      <div className="fin-page-head">
        <div>
          <h1 className="fin-page-title">Metas</h1>
          <p className="fin-page-sub">Objetivos divididos em passos, com XP por passo cumprido</p>
        </div>

        <button
          className={`fin-btn fin-btn--${formAberto ? "ghost" : "primary"}`}
          onClick={() => setFormAberto((v) => !v)}
        >
          {formAberto ? (
            <>
              <X size={14} /> Cancelar
            </>
          ) : (
            <>
              <Plus size={14} /> Nova meta
            </>
          )}
        </button>
      </div>

      {falha && (
        <div className="fin-banner" style={{ "--bc": "var(--fin-danger)" }}>
          <span>{falha}</span>
        </div>
      )}

      {/* ── Personagem ── */}
      <div className="fin-card fin-heroi" style={{ "--pc": nivelInfo.cor }}>
        <div className="fin-selo fin-heroi__avatar" data-divisao={nivelInfo.divisao}>
          <IconePatamar size={30} />
          <span className="fin-heroi__nivel">{nivelInfo.nivel}</span>
        </div>

        <div className="fin-heroi__info">
          <div className="fin-heroi__topo">
            <div>
              <div className="fin-heroi__patente">
                {nivelInfo.rotulo}
                <span className="fin-pips" aria-label={`${nivelInfo.pips} de 5 níveis nesta divisão`}>
                  {[1, 2, 3, 4, 5].map((p) => (
                    <i key={p} className={p <= nivelInfo.pips ? "cheio" : ""} />
                  ))}
                </span>
              </div>
              <div className="fin-heroi__sub">
                Nível {nivelInfo.nivel} · {personagem?.xp ?? 0} XP acumulado
              </div>
            </div>
            <div className="fin-heroi__falta">
              {nivelInfo.maximo
                ? "Nível máximo da escada"
                : `${personagem?.xpParaProximo ?? 0} XP para o nível ${(personagem?.nivel ?? 1) + 1}`}
            </div>
          </div>

          <div className="fin-barra" title={`${personagem?.percentual ?? 0}%`}>
            <div
              className="fin-barra__preenchida"
              style={{ width: `${personagem?.percentual ?? 0}%` }}
            />
          </div>
          <div className="fin-heroi__escala">
            <span>{personagem?.xpNoNivel ?? 0} XP</span>
            <span>{personagem?.xpDoNivel ?? 100} XP</span>
          </div>
        </div>
      </div>

      {/* ── KPIs ── */}
      <div className="fin-kpis fin-kpis--3">
        <Kpi
          cor="var(--fin-accent)"
          icone={Target}
          label="Metas ativas"
          valor={String(resumo.ativas)}
          sub={resumo.ativas === 0 ? "nenhuma em andamento" : "em andamento"}
        />
        <Kpi
          cor="var(--fin-in)"
          icone={Trophy}
          label="Concluídas"
          valor={String(resumo.concluidas)}
          sub="metas fechadas"
        />
        <Kpi
          cor="var(--fin-cat-2)"
          icone={Check}
          label="Passos cumpridos"
          valor={`${resumo.subsFeitas}/${resumo.subsTotal}`}
          sub={
            resumo.subsTotal
              ? `${Math.round((resumo.subsFeitas / resumo.subsTotal) * 100)}% do total`
              : "sem passos ainda"
          }
        />
      </div>

      {/* ── Formulário ── */}
      {formAberto && (
        <div className="fin-card" style={{ marginBottom: 12 }}>
          <div className="fin-cfg-card__title">
            <Plus size={15} /> Nova meta
          </div>

          <form className="fin-form" onSubmit={salvar}>
            <div className="fin-field">
              <label htmlFor="m-titulo">Título</label>
              <input
                id="m-titulo"
                value={form.titulo}
                onChange={(e) => setForm({ ...form, titulo: e.target.value })}
                placeholder="Juntar a entrada do apartamento"
                maxLength={160}
                required
                autoFocus
              />
            </div>

            <div className="fin-field">
              <label htmlFor="m-desc">Detalhes (opcional)</label>
              <input
                id="m-desc"
                value={form.descricao}
                onChange={(e) => setForm({ ...form, descricao: e.target.value })}
                placeholder="O que conta como pronto, restrições, contexto"
              />
            </div>

            <div className="fin-lanc-form">
              <div className="fin-field">
                <label htmlFor="m-alvo">Valor alvo (opcional)</label>
                <input
                  id="m-alvo"
                  type="number"
                  step="0.01"
                  min="0"
                  inputMode="decimal"
                  value={form.alvo}
                  onChange={(e) => setForm({ ...form, alvo: e.target.value })}
                  placeholder="20000,00"
                />
                <span className="fin-field__hint">Deixe vazio se a meta não é financeira</span>
              </div>

              <div className="fin-field">
                <label htmlFor="m-prazo">Prazo (opcional)</label>
                <input
                  id="m-prazo"
                  type="date"
                  value={form.prazo}
                  onChange={(e) => setForm({ ...form, prazo: e.target.value })}
                />
              </div>
            </div>

            <label className={`fin-check-linha${iaDisponivel ? "" : " fin-check-linha--off"}`}>
              <input
                type="checkbox"
                checked={form.gerarSubtarefas && iaDisponivel}
                disabled={!iaDisponivel}
                onChange={(e) => setForm({ ...form, gerarSubtarefas: e.target.checked })}
              />
              <Sparkles size={14} />
              <span>
                Sugerir os passos automaticamente
                {!iaDisponivel && (
                  <small>
                    {" "}
                    (indisponível: configure a variável de ambiente GEMINI_API_KEY)
                  </small>
                )}
              </span>
            </label>

            <div className="fin-form__actions">
              <button className="fin-btn fin-btn--primary fin-btn--sm" disabled={salvando}>
                {salvando ? (
                  <>
                    <Loader2 size={13} className="fin-spin" />
                    {form.gerarSubtarefas && iaDisponivel ? "Criando e sugerindo..." : "Criando..."}
                  </>
                ) : (
                  <>
                    <Check size={13} /> Criar meta
                  </>
                )}
              </button>
              <button
                type="button"
                className="fin-btn fin-btn--ghost fin-btn--sm"
                onClick={() => {
                  setFormAberto(false);
                  setForm(formularioVazio());
                }}
              >
                Cancelar
              </button>
            </div>
          </form>
        </div>
      )}

      {/* ── Filtro: em andamento x concluídas ── */}
      <div className="fin-card__head" style={{ marginBottom: 10 }}>
        <div className="fin-seg">
          <button
            className={filtro === "andamento" ? "active" : ""}
            onClick={() => setFiltro("andamento")}
          >
            Em andamento ({resumo.ativas})
          </button>
          <button
            className={filtro === "concluidas" ? "active" : ""}
            onClick={() => setFiltro("concluidas")}
          >
            Concluídas ({resumo.concluidas})
          </button>
        </div>
      </div>

      {/* ── Metas ── */}
      {visiveis.length === 0 ? (
        <div className="fin-card">
          <div className="fin-empty">
            {filtro === "concluidas" ? (
              <>
                <Trophy size={30} />
                <strong>Nenhuma meta concluída ainda.</strong>
                <span style={{ maxWidth: "46ch" }}>
                  Quando você concluir uma meta, ela vem para cá com o histórico dos
                  passos e o XP que rendeu.
                </span>
              </>
            ) : metas.length > 0 ? (
              <>
                <Target size={30} />
                <strong>Nada em andamento.</strong>
                <span style={{ maxWidth: "46ch" }}>
                  Todas as suas metas estão concluídas. Crie a próxima.
                </span>
              </>
            ) : (
              <>
                <Target size={30} />
                <strong>Nenhuma meta ainda.</strong>
                <span style={{ maxWidth: "46ch" }}>
                  Crie uma meta e divida em passos. Cada passo cumprido dá XP, e fechar a
                  meta inteira dá um bônus maior que a soma deles.
                </span>
              </>
            )}
          </div>
        </div>
      ) : (
        <div className="fin-metas">
          {visiveis.map((meta) => {
            const p = progressoDaMeta(meta);
            const ocupadaAqui = ocupada === `m${meta.id}`;
            return (
              <div
                key={meta.id}
                className={`fin-card fin-meta${meta.concluida ? " concluida" : ""}`}
              >
                <div className="fin-meta__cab">
                  <div className="fin-meta__titulo-area">
                    <div className="fin-meta__titulo">{meta.titulo}</div>
                    {meta.descricao && <div className="fin-meta__desc">{meta.descricao}</div>}
                    <div className="fin-meta__meta">
                      {meta.alvo != null && <span>{brl(meta.alvo)}</span>}
                      {meta.prazo && <span>até {meta.prazo.split("-").reverse().join("/")}</span>}
                      {!meta.concluida && <span>+{p.xpRestante} XP disponíveis</span>}
                    </div>
                  </div>

                  <button
                    className="fin-lanc-item__excluir"
                    onClick={() => setExclusao({ tipo: "meta", item: meta })}
                    disabled={ocupadaAqui}
                    aria-label={`Remover meta ${meta.titulo}`}
                    title="Remover meta"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>

                {p.total > 0 && (
                  <>
                    <div className="fin-barra fin-barra--fina">
                      <div
                        className="fin-barra__preenchida"
                        style={{ width: `${p.percentual}%` }}
                      />
                    </div>
                    <div className="fin-meta__progresso">
                      {p.feitas} de {p.total} passos · {p.percentual}%
                    </div>
                  </>
                )}

                <div className="fin-subs">
                  {meta.subtarefas.map((sub) => (
                    <div key={sub.id} className="fin-sub">
                      <label className="fin-sub__marca">
                        <input
                          type="checkbox"
                          checked={sub.concluida}
                          disabled={ocupada === `s${sub.id}`}
                          onChange={() => alternar(meta, sub)}
                        />
                        <span className={sub.concluida ? "feita" : ""}>{sub.titulo}</span>
                      </label>

                      <span className="fin-sub__xp">
                        {sub.geradaPorIa && (
                          <Sparkles size={10} aria-label="sugerida pela IA" />
                        )}
                        {sub.xp} XP
                      </span>

                      <button
                        className="fin-sub__excluir"
                        onClick={() => setExclusao({ tipo: "sub", item: sub })}
                        aria-label={`Remover passo ${sub.titulo}`}
                        title="Remover passo"
                      >
                        <X size={12} />
                      </button>
                    </div>
                  ))}
                </div>

                <form className="fin-sub-nova" onSubmit={(e) => adicionarSub(meta, e)}>
                  <input
                    value={novaSub[meta.id] || ""}
                    onChange={(e) => setNovaSub((n) => ({ ...n, [meta.id]: e.target.value }))}
                    placeholder="Adicionar um passo"
                    maxLength={200}
                    aria-label={`Novo passo para ${meta.titulo}`}
                  />
                  <button
                    className="fin-btn fin-btn--ghost fin-btn--sm"
                    disabled={!(novaSub[meta.id] || "").trim()}
                  >
                    <Plus size={13} />
                  </button>
                </form>

                <div className="fin-meta__acoes">
                  <button
                    className={`fin-btn fin-btn--sm fin-btn--${meta.concluida ? "ghost" : "primary"}`}
                    onClick={() => concluirMeta(meta)}
                    disabled={ocupadaAqui}
                  >
                    {meta.concluida ? (
                      <>
                        <X size={13} /> Reabrir
                      </>
                    ) : (
                      <>
                        <Trophy size={13} /> Concluir (+{meta.bonusXp} XP)
                      </>
                    )}
                  </button>

                  {iaDisponivel && !meta.concluida && (
                    <button
                      className="fin-btn fin-btn--outline fin-btn--sm"
                      onClick={() => gerarPassos(meta)}
                      disabled={gerando === meta.id}
                    >
                      {gerando === meta.id ? (
                        <>
                          <Loader2 size={13} className="fin-spin" /> Pensando...
                        </>
                      ) : (
                        <>
                          <Sparkles size={13} />
                          {p.total ? "Sugerir mais passos" : "Sugerir passos"}
                        </>
                      )}
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {exclusao && (
        <ConfirmarExclusao
          {...textoDaExclusao()}
          ocupado={excluindo}
          onConfirmar={confirmarExclusao}
          onCancelar={() => setExclusao(null)}
        />
      )}

      {toast && (
        <div className={`fin-toast fin-toast--${toast.tipo}`} role="status">
          {toast.msg}
        </div>
      )}
    </>
  );
}

function Kpi({ cor, icone: Icone, label, valor, sub }) {
  return (
    <div className="fin-kpi" style={{ "--kc": cor }}>
      <div className="fin-kpi__top">
        <span className="fin-kpi__label">{label}</span>
        <Icone size={14} />
      </div>
      <div className="fin-kpi__val">{valor}</div>
      <div className="fin-kpi__sub">{sub}</div>
      <div className="fin-kpi__bar" />
    </div>
  );
}
