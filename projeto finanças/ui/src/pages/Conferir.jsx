// Conferir números: mede a regra que tira da soma o dinheiro que só muda de
// conta (pagamento de fatura, transferência entre as próprias contas).
//
// Duas listas. "Saíram da soma" são os descartes da importação, com o par
// que a regra achou; "Ficaram na soma" são importadas que parecem o mesmo
// dinheiro dos dois lados e continuam contando. Cada decisão é marcada como
// certa ou errada, e o placar sai daí. Marcar um descarte como errado o
// devolve para Entradas e Saídas; marcar um suspeito como errado tira os
// dois da soma.

import {
  AlertTriangle,
  ArrowDownLeft,
  ArrowLeft,
  ArrowUpRight,
  Check,
  CheckCheck,
  Loader2,
  SearchCheck,
  Target,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { brl, dataCurta } from "../services/financasService";
import {
  julgarDescarte,
  julgarSuspeito,
  lerConferencia,
  placarDaRegra,
} from "../services/openfinanceService";

const POR_PAGINA = 25;

const MOTIVO = {
  pagamentoFatura: "Pagamento de fatura",
  transferencias: "Transferência entre suas contas",
};

const chave = (g) => g.itens.map((i) => i.id).join("-");
const contar = (n, um, varios) => `${n} ${n === 1 ? um : varios}`;
const pendente = (g) => g.itens.some((i) => !i.veredito);

function comoDecidiu(g) {
  if (g.itens.length === 2) return "Os dois lados casaram: mesmo valor, até 5 dias de diferença";
  return g.motivo === "pagamentoFatura"
    ? "O banco marcou como pagamento; o outro lado não está nas contas conectadas"
    : "O banco marcou como transferência entre contas do mesmo CPF";
}

export default function Conferir() {
  const navigate = useNavigate();

  const [dados, setDados] = useState(null);
  const [carregando, setCarregando] = useState(true);
  const [falha, setFalha] = useState("");
  const [toast, setToast] = useState(null);

  const [aba, setAba] = useState("fora");
  const [limite, setLimite] = useState(POR_PAGINA);
  // Grupo julgado agora continua na aba até ela ser trocada: sumir no
  // clique faz a lista pular embaixo do dedo.
  const [tocados, setTocados] = useState(() => new Set());
  const [ocupados, setOcupados] = useState(() => new Set());

  const notificar = (msg, tipo = "success") => {
    setToast({ msg, tipo });
    setTimeout(() => setToast(null), 3500);
  };

  const ocupar = (ids, sim) =>
    setOcupados((s) => {
      const n = new Set(s);
      ids.forEach((id) => (sim ? n.add(id) : n.delete(id)));
      return n;
    });

  const carregar = useCallback(async () => {
    try {
      setDados(await lerConferencia());
      setFalha("");
    } catch (e) {
      if (e.status === 401 || e.status === 403) {
        navigate("/login", { replace: true });
        return;
      }
      setFalha(e.message || "Erro ao carregar a conferência.");
    } finally {
      setCarregando(false);
    }
  }, [navigate]);

  useEffect(() => {
    carregar();
  }, [carregar]);

  const grupos = dados?.grupos || [];
  const suspeitos = dados?.suspeitos || [];

  // certos e errados vêm dos grupos, que mudam na hora; mantidos e
  // faltaram vêm do servidor e são corrigidos a cada julgamento de suspeito.
  const resumo = useMemo(() => {
    const itens = grupos.flatMap((g) => g.itens);
    return {
      ...(dados?.resumo || { mantidos: 0, faltaram: 0 }),
      descartes: itens.length,
      certos: itens.filter((i) => i.veredito === "certo").length,
      errados: itens.filter((i) => i.veredito === "errado").length,
      aConferir: itens.filter((i) => !i.veredito).length,
    };
  }, [grupos, dados]);
  const placar = placarDaRegra(resumo);

  const visiveis = useMemo(() => {
    if (aba === "fora") return grupos.filter((g) => pendente(g) || tocados.has(chave(g)));
    if (aba === "conferidos") return grupos.filter((g) => !pendente(g));
    return [];
  }, [aba, grupos, tocados]);

  const trocarAba = (nova) => {
    setAba(nova);
    setTocados(new Set());
    setLimite(POR_PAGINA);
  };

  const marcarItem = (id, veredito) =>
    setDados((d) => ({
      ...d,
      grupos: d.grupos.map((g) => ({
        ...g,
        itens: g.itens.map((i) => (i.id === id ? { ...i, veredito } : i)),
      })),
    }));

  // Clicar no voto que já está marcado desfaz.
  const votar = async (g, item, voto) => {
    const novo = item.veredito === voto ? null : voto;
    setTocados((s) => new Set(s).add(chave(g)));
    ocupar([item.id], true);
    try {
      await julgarDescarte(item.id, novo);
      marcarItem(item.id, novo);
      if (novo === "errado") notificar("Voltou para Entradas e Saídas.");
      else if (item.veredito === "errado") notificar("Saiu de novo de Entradas e Saídas.");
    } catch (err) {
      notificar(err.message, "error");
    } finally {
      ocupar([item.id], false);
    }
  };

  const tudoCerto = async (g) => {
    const falta = g.itens.filter((i) => !i.veredito);
    setTocados((s) => new Set(s).add(chave(g)));
    ocupar(falta.map((i) => i.id), true);
    try {
      for (const i of falta) {
        await julgarDescarte(i.id, "certo");
        marcarItem(i.id, "certo");
      }
    } catch (err) {
      notificar(err.message, "error");
    } finally {
      ocupar(falta.map((i) => i.id), false);
    }
  };

  const julgarPar = async (s, voto) => {
    const ids = s.itens.map((i) => i.id);
    ocupar(ids, true);
    try {
      await julgarSuspeito(ids, voto);
      setDados((d) => ({
        ...d,
        suspeitos: d.suspeitos.filter((x) => x !== s),
        resumo: {
          ...d.resumo,
          suspeitos: d.resumo.suspeitos - 1,
          mantidos: d.resumo.mantidos + (voto === "certo" ? 2 : 0),
          faltaram: d.resumo.faltaram + (voto === "errado" ? 2 : 0),
        },
      }));
      notificar(voto === "errado" ? "Os dois saíram da soma." : "Os dois continuam contando.");
    } catch (err) {
      notificar(err.message, "error");
    } finally {
      ocupar(ids, false);
    }
  };

  if (carregando) {
    return (
      <div className="fin-loading">
        <Loader2 size={17} className="fin-spin" />
        <span>Juntando os descartes...</span>
      </div>
    );
  }

  const conferidos = grupos.filter((g) => !pendente(g)).length;
  const lista = aba === "dentro" ? suspeitos : visiveis;

  return (
    <>
      <div className="fin-page-head">
        <div>
          <h1 className="fin-page-title">Conferir números</h1>
          <p className="fin-page-sub">O que a importação tirou da soma, e o que deixou</p>
        </div>
        <div className="fin-form__actions">
          <button className="fin-btn fin-btn--ghost" onClick={() => navigate("/app/contas")}>
            <ArrowLeft size={14} /> Contas
          </button>
        </div>
      </div>

      {falha && (
        <div className="fin-banner" style={{ "--bc": "var(--fin-danger)" }}>
          <AlertTriangle size={16} />
          <span>{falha}</span>
        </div>
      )}

      <p className="fin-of-nota fin-conf-intro">
        Para não contar o mesmo dinheiro duas vezes, a importação tira da soma o que só muda de
        conta, como o pagamento da fatura. Confira cada decisão: o placar diz quanto dá para
        confiar nos totais.
      </p>

      <div className="fin-kpis fin-kpis--3">
        <Kpi
          cor="var(--fin-accent)"
          icone={Target}
          label="Acerto da regra"
          valor={placar.acerto == null ? "—" : `${placar.acerto}%`}
          sub={
            placar.julgados
              ? `${placar.acertos} de ${placar.julgados} lançamentos conferidos`
              : "confira alguns para medir"
          }
        />
        <Kpi
          cor="var(--fin-warn)"
          icone={SearchCheck}
          label="A conferir"
          valor={resumo.aConferir + 2 * resumo.suspeitos}
          sub={`${contar(resumo.aConferir, "descartado", "descartados")} · ${contar(
            resumo.suspeitos,
            "par suspeito",
            "pares suspeitos",
          )}`}
        />
        <Kpi
          cor="var(--fin-out)"
          icone={AlertTriangle}
          label="Erros achados"
          valor={resumo.errados + resumo.faltaram}
          sub={`${contar(resumo.errados, "tirado", "tirados")} sem dever · ${contar(
            resumo.faltaram,
            "contado",
            "contados",
          )} duas vezes`}
        />
      </div>

      <div className="fin-conf-abas">
        <div className="fin-seg" role="tablist">
          {[
            ["fora", `Saíram da soma (${grupos.filter(pendente).length})`],
            ["dentro", `Ficaram na soma (${suspeitos.length})`],
            ["conferidos", `Conferidos (${conferidos})`],
          ].map(([id, rotulo]) => (
            <button
              key={id}
              role="tab"
              aria-selected={aba === id}
              className={aba === id ? "active" : ""}
              onClick={() => trocarAba(id)}
            >
              {rotulo}
            </button>
          ))}
        </div>
        <p className="fin-of-nota">
          {aba === "fora" &&
            "Certo: era mesmo o mesmo dinheiro mudando de conta. Errado: era gasto ou entrada de verdade, e o lançamento volta para Entradas e Saídas."}
          {aba === "dentro" &&
            "Mesmo valor, um saindo e outro entrando, até 5 dias de diferença, e os dois contando. Se for o mesmo dinheiro mudando de conta, os dois saem da soma."}
          {aba === "conferidos" && "Clique de novo num voto para desfazer."}
        </p>
      </div>

      {lista.length === 0 ? (
        <Vazio aba={aba} semDescartes={grupos.length === 0} onContas={() => navigate("/app/contas")} />
      ) : (
        <div className="fin-conf-lista">
          {aba === "dentro"
            ? lista.slice(0, limite).map((s) => (
                <Suspeito
                  key={chave(s)}
                  s={s}
                  ocupado={s.itens.some((i) => ocupados.has(i.id))}
                  onJulgar={(voto) => julgarPar(s, voto)}
                />
              ))
            : lista.slice(0, limite).map((g) => (
                <Grupo
                  key={chave(g)}
                  g={g}
                  ocupados={ocupados}
                  onVotar={(item, voto) => votar(g, item, voto)}
                  onTudoCerto={() => tudoCerto(g)}
                />
              ))}
          {lista.length > limite && (
            <button
              className="fin-btn fin-btn--ghost fin-conf-mais"
              onClick={() => setLimite((n) => n + POR_PAGINA)}
            >
              Mostrar mais ({lista.length - limite})
            </button>
          )}
        </div>
      )}

      {toast && (
        <div className={`fin-toast fin-toast--${toast.tipo}`} role="status">
          {toast.msg}
        </div>
      )}
    </>
  );
}

function Grupo({ g, ocupados, onVotar, onTudoCerto }) {
  const faltam = g.itens.filter((i) => !i.veredito).length;
  const algumOcupado = g.itens.some((i) => ocupados.has(i.id));

  return (
    <div className="fin-card fin-card--flush">
      <div className="fin-conf-cab">
        <div style={{ minWidth: 0 }}>
          <div className="fin-card__title">{MOTIVO[g.motivo] || g.motivo}</div>
          <div className="fin-card__sub">{comoDecidiu(g)}</div>
        </div>
        {faltam > 1 && (
          <button
            className="fin-btn fin-btn--ghost fin-btn--sm"
            onClick={onTudoCerto}
            disabled={algumOcupado}
          >
            <CheckCheck size={13} /> Os dois certos
          </button>
        )}
      </div>
      {g.itens.map((i) => (
        <Linha key={i.id} i={i}>
          <Voto i={i} ocupado={ocupados.has(i.id)} onVotar={(voto) => onVotar(i, voto)} />
        </Linha>
      ))}
    </div>
  );
}

function Suspeito({ s, ocupado, onJulgar }) {
  return (
    <div className="fin-card fin-card--flush">
      {s.itens.map((i) => (
        <Linha key={i.id} i={i} />
      ))}
      <div className="fin-conf-pe">
        <span>É o mesmo dinheiro mudando de conta?</span>
        <div className="fin-conf-pe__acoes">
          <button
            className="fin-btn fin-btn--ghost fin-btn--sm"
            onClick={() => onJulgar("certo")}
            disabled={ocupado}
          >
            <Check size={13} /> Não, os dois contam
          </button>
          <button
            className="fin-btn fin-btn--ghost fin-btn--sm fin-conf-tirar"
            onClick={() => onJulgar("errado")}
            disabled={ocupado}
          >
            {ocupado ? <Loader2 size={13} className="fin-spin" /> : <X size={13} />} Sim, tirar os
            dois
          </button>
        </div>
      </div>
    </div>
  );
}

function Linha({ i, children }) {
  const saida = i.natureza === "despesa";
  const onde = i.conta || (i.meio === "cartao" ? "Cartão" : "Conta");
  return (
    <div className="fin-conf-item">
      <div className="fin-list__ico" style={{ "--ic": saida ? "var(--fin-out)" : "var(--fin-in)" }}>
        {saida ? <ArrowDownLeft size={14} /> : <ArrowUpRight size={14} />}
      </div>
      <div className="fin-list__body">
        <div className="fin-list__name" title={i.nome}>
          {i.nome}
        </div>
        <div className="fin-list__meta">
          {dataCurta(i.data)} · {onde}
          {i.categoria ? ` · ${i.categoria}` : ""}
        </div>
      </div>
      <div className="fin-list__val" style={{ "--ic": saida ? "var(--fin-out)" : "var(--fin-in)" }}>
        {brl(i.valor)}
        <small>{saida ? "saída" : "entrada"}</small>
      </div>
      {children && <div className="fin-conf-item__acoes">{children}</div>}
    </div>
  );
}

function Voto({ i, ocupado, onVotar }) {
  return (
    <div className="fin-conf-voto" role="group" aria-label={`Conferir ${i.nome}`}>
      <button
        data-v="certo"
        aria-pressed={i.veredito === "certo"}
        onClick={() => onVotar("certo")}
        disabled={ocupado}
        title={i.veredito === "certo" ? "Desfazer" : "Certo tirar da soma"}
      >
        <Check size={13} /> Certo
      </button>
      <button
        data-v="errado"
        aria-pressed={i.veredito === "errado"}
        onClick={() => onVotar("errado")}
        disabled={ocupado}
        title={i.veredito === "errado" ? "Desfazer" : "Era de verdade: volta para a soma"}
      >
        <X size={13} /> Errado
      </button>
    </div>
  );
}

function Vazio({ aba, semDescartes, onContas }) {
  if (aba === "fora" && semDescartes) {
    return (
      <div className="fin-empty">
        <SearchCheck size={22} />
        <span>Nada descartado ainda. Importe as transações em Contas e volte aqui.</span>
        <button className="fin-btn fin-btn--ghost fin-btn--sm" onClick={onContas}>
          <ArrowLeft size={13} /> Ir para Contas
        </button>
      </div>
    );
  }
  const texto = {
    fora: "Tudo o que saiu da soma já foi conferido.",
    dentro: "Nada que ficou na soma parece o mesmo dinheiro passando entre contas.",
    conferidos: "Nada conferido ainda.",
  }[aba];
  return (
    <div className="fin-empty">
      <CheckCheck size={22} />
      <span>{texto}</span>
    </div>
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
