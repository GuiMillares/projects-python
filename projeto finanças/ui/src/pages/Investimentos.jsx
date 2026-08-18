// Carteira de investimentos com cotação da B3 (brapi.dev).
//
// A cotação é acessório sobre um dado que já existe no banco. Quando a brapi
// falha, a tela mostra tudo que foi cadastrado (ticker, quantidade, preço
// médio, investido) e sinaliza o que não deu para calcular, em vez de
// quebrar: é o mesmo princípio do EmptyChart do dashboard, isolar o pedaço
// que faltou em vez de derrubar a página.

import {
  AlertTriangle,
  Check,
  CloudOff,
  Loader2,
  Plus,
  RefreshCw,
  Trash2,
  TrendingDown,
  TrendingUp,
  Wallet,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { brl, dataCurta } from "../services/financasService";
import {
  apagarInvestimento,
  buscarCotacao,
  calcularPosicao,
  criarInvestimento,
  listarInvestimentos,
  resumoCarteira,
} from "../services/investimentosService";

/** B3 usa 4 letras + 1 ou 2 dígitos (PETR4, HGLG11...); abaixo disso não
 * vale a pena consultar a brapi, ainda está no meio da digitação. */
const TICKER_PRONTO = /^[A-Z]{4}\d{1,2}$/;

const hojeISO = () => new Date().toISOString().slice(0, 10);

const formularioVazio = () => ({
  ticker: "",
  quantidade: "",
  precoMedio: "",
  data: hojeISO(),
});

/** Quantidade some as casas decimais que não precisa: 10 e não 10,00000000. */
const qtd = (n) =>
  Number(n).toLocaleString("pt-BR", { maximumFractionDigits: 8 });

const pct = (n) =>
  `${n > 0 ? "+" : ""}${Number(n).toLocaleString("pt-BR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}%`;

export default function Investimentos() {
  const navigate = useNavigate();

  const [itens, setItens] = useState([]);
  const [aviso, setAviso] = useState(null);
  const [carregando, setCarregando] = useState(true);
  const [atualizando, setAtualizando] = useState(false);
  const [falha, setFalha] = useState("");
  const [toast, setToast] = useState(null);

  const [formAberto, setFormAberto] = useState(false);
  const [form, setForm] = useState(formularioVazio);
  const [salvando, setSalvando] = useState(false);
  const [apagando, setApagando] = useState(null);

  const [cotacaoBusca, setCotacaoBusca] = useState({ buscando: false, dados: null, erro: "" });
  // Guarda o último preço que NÓS preenchemos, não o usuário. Assim, se ele
  // digitar um preço próprio (o que realmente pagou), a busca seguinte não
  // atropela a edição dele.
  const autoPreenchidoRef = useRef({ ticker: "", preco: "" });

  useEffect(() => {
    const ticker = form.ticker;
    if (!formAberto || !TICKER_PRONTO.test(ticker)) {
      setCotacaoBusca({ buscando: false, dados: null, erro: "" });
      return;
    }

    let cancelado = false;
    setCotacaoBusca((c) => ({ ...c, buscando: true }));
    const timer = setTimeout(async () => {
      try {
        const r = await buscarCotacao(ticker);
        if (cancelado) return; // o campo já mudou, esta resposta está velha
        setCotacaoBusca({
          buscando: false,
          dados: r.cotacao || null,
          erro: r.cotacao ? "" : r.aviso || "Cotação não encontrada para este ticker.",
        });
        if (r.cotacao?.preco != null) {
          const precoStr = String(r.cotacao.preco);
          setForm((f) => {
            if (f.ticker !== ticker) return f;
            const podeAutoPreencher =
              f.precoMedio === "" ||
              (autoPreenchidoRef.current.ticker === ticker &&
                f.precoMedio === autoPreenchidoRef.current.preco);
            if (!podeAutoPreencher) return f;
            autoPreenchidoRef.current = { ticker, preco: precoStr };
            return { ...f, precoMedio: precoStr };
          });
        }
      } catch {
        if (!cancelado) {
          setCotacaoBusca({ buscando: false, dados: null, erro: "Não consegui buscar a cotação agora." });
        }
      }
    }, 500);

    return () => {
      cancelado = true;
      clearTimeout(timer);
    };
  }, [form.ticker, formAberto]);

  const notificar = (msg, tipo = "success") => {
    setToast({ msg, tipo });
    setTimeout(() => setToast(null), 3000);
  };

  const carregar = useCallback(
    async ({ silencioso = false } = {}) => {
      if (silencioso) setAtualizando(true);
      try {
        const r = await listarInvestimentos();
        setItens(r.itens || []);
        setAviso(r.aviso || null);
        setFalha("");
      } catch (e) {
        if (e.status === 401 || e.status === 403) {
          navigate("/login", { replace: true });
          return;
        }
        setFalha(e.message || "Erro ao carregar a carteira.");
      } finally {
        setCarregando(false);
        setAtualizando(false);
      }
    },
    [navigate],
  );

  useEffect(() => {
    carregar();
  }, [carregar]);

  const { posicoes, resumo } = useMemo(() => {
    const p = itens.map(calcularPosicao);
    return { posicoes: p, resumo: resumoCarteira(p) };
  }, [itens]);

  const salvar = async (e) => {
    e.preventDefault();
    setSalvando(true);
    try {
      await criarInvestimento(form);
      setForm(formularioVazio());
      autoPreenchidoRef.current = { ticker: "", preco: "" };
      setFormAberto(false);
      await carregar();
      notificar("Investimento cadastrado.");
    } catch (err) {
      notificar(err.message, "error");
    } finally {
      setSalvando(false);
    }
  };

  const excluir = async (item) => {
    setApagando(item.id);
    try {
      await apagarInvestimento(item.id);
      setItens((l) => l.filter((x) => x.id !== item.id));
      notificar("Posição removida.");
    } catch (err) {
      notificar(err.message, "error");
    } finally {
      setApagando(null);
    }
  };

  if (carregando) {
    return (
      <div className="fin-loading">
        <Loader2 size={17} className="fin-spin" />
        <span>Buscando cotações...</span>
      </div>
    );
  }

  const positivo = resumo.lucro !== null && resumo.lucro >= 0;

  return (
    <>
      <div className="fin-page-head">
        <div>
          <h1 className="fin-page-title">Investimentos</h1>
          <p className="fin-page-sub">Carteira com cotação da B3</p>
        </div>

        <div className="fin-form__actions">
          <button
            className="fin-btn fin-btn--ghost"
            onClick={() => carregar({ silencioso: true })}
            disabled={atualizando}
            title="Buscar cotações de novo"
          >
            <RefreshCw size={14} className={atualizando ? "fin-spin" : ""} />
            Atualizar
          </button>

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
                <Plus size={14} /> Novo investimento
              </>
            )}
          </button>
        </div>
      </div>

      {falha && (
        <div className="fin-banner" style={{ "--bc": "var(--fin-danger)" }}>
          <AlertTriangle size={16} />
          <span>{falha}</span>
        </div>
      )}

      {/* Cotação indisponível não é erro da tela: é aviso discreto, e os
          dados cadastrados continuam todos visíveis abaixo. */}
      {aviso && (
        <div className="fin-banner" style={{ "--bc": "var(--fin-warn)" }}>
          <CloudOff size={16} />
          <span>{aviso}</span>
        </div>
      )}

      {/* ── KPIs ── */}
      <div className="fin-kpis fin-kpis--3">
        <Kpi
          cor="var(--fin-cat-6)"
          icone={Wallet}
          label="Total investido"
          valor={brl(resumo.investido)}
          sub={`${posicoes.length} ${posicoes.length === 1 ? "posição" : "posições"}`}
        />
        <Kpi
          cor="var(--fin-accent)"
          icone={Wallet}
          label="Valor atual"
          valor={resumo.atual === null ? "n/d" : brl(resumo.atual)}
          sub={
            resumo.atual === null
              ? "cotação indisponível"
              : resumo.semCotacao > 0
                ? `${resumo.semCotacao} sem cotação, fora da conta`
                : "a preço de mercado"
          }
        />
        <Kpi
          cor={
            resumo.lucro === null
              ? "var(--fin-muted)"
              : positivo
                ? "var(--fin-in)"
                : "var(--fin-out)"
          }
          icone={resumo.lucro === null ? Wallet : positivo ? TrendingUp : TrendingDown}
          label="Rentabilidade"
          valor={
            resumo.lucro === null
              ? "n/d"
              : `${positivo ? "+" : ""}${brl(resumo.lucro)}`
          }
          sub={resumo.lucroPct === null ? "sem cotação" : pct(resumo.lucroPct)}
          tingido={resumo.lucro !== null}
        />
      </div>

      {/* ── Formulário ── */}
      {formAberto && (
        <div className="fin-card" style={{ marginBottom: 12 }}>
          <div className="fin-cfg-card__title">
            <Plus size={15} /> Novo investimento
          </div>

          <form className="fin-form" onSubmit={salvar}>
            <div className="fin-lanc-form">
              <div className="fin-field">
                <label htmlFor="i-ticker">Ticker</label>
                <input
                  id="i-ticker"
                  value={form.ticker}
                  // Maiúsculas na digitação: é como a B3 escreve e como a
                  // brapi espera, então não faz sentido aceitar minúscula
                  // e corrigir só no servidor.
                  onChange={(e) =>
                    setForm({
                      ...form,
                      ticker: e.target.value.replace(/[^A-Za-z0-9]/g, "").toUpperCase(),
                    })
                  }
                  placeholder="PETR4"
                  maxLength={16}
                  required
                  autoFocus
                />
                <span className="fin-field__hint">Ações, FIIs, ETFs e BDRs da B3</span>
              </div>

              <div className="fin-field">
                <label htmlFor="i-qtd">Quantidade</label>
                <input
                  id="i-qtd"
                  type="number"
                  step="any"
                  min="0"
                  inputMode="decimal"
                  value={form.quantidade}
                  onChange={(e) => setForm({ ...form, quantidade: e.target.value })}
                  placeholder="100"
                  required
                />
              </div>

              <div className="fin-field">
                <label htmlFor="i-preco">Preço médio (R$)</label>
                <input
                  id="i-preco"
                  type="number"
                  step="any"
                  min="0"
                  inputMode="decimal"
                  value={form.precoMedio}
                  onChange={(e) => {
                    // Editou na mão: a próxima cotação não pisa mais nesse valor.
                    autoPreenchidoRef.current = { ticker: "", preco: "" };
                    setForm({ ...form, precoMedio: e.target.value });
                  }}
                  placeholder="38,50"
                  required
                />
                <span
                  className="fin-field__hint"
                  style={cotacaoBusca.erro ? { color: "var(--fin-warn)" } : undefined}
                >
                  {cotacaoBusca.buscando
                    ? "buscando cotação..."
                    : cotacaoBusca.dados
                      ? `cotação agora: ${brl(cotacaoBusca.dados.preco)}, ajuste se pagou outro valor`
                      : cotacaoBusca.erro || "preenchido com a cotação atual ao digitar o ticker"}
                </span>
              </div>

              <div className="fin-field">
                <label htmlFor="i-data">Data da compra</label>
                <input
                  id="i-data"
                  type="date"
                  value={form.data}
                  onChange={(e) => setForm({ ...form, data: e.target.value })}
                  required
                />
              </div>
            </div>

            <div className="fin-form__actions">
              <button className="fin-btn fin-btn--primary fin-btn--sm" disabled={salvando}>
                {salvando ? (
                  <>
                    <Loader2 size={13} className="fin-spin" /> Salvando...
                  </>
                ) : (
                  <>
                    <Check size={13} /> Cadastrar
                  </>
                )}
              </button>
              <button
                type="button"
                className="fin-btn fin-btn--ghost fin-btn--sm"
                onClick={() => {
                  setFormAberto(false);
                  setForm(formularioVazio());
                  autoPreenchidoRef.current = { ticker: "", preco: "" };
                }}
              >
                Cancelar
              </button>
            </div>
          </form>
        </div>
      )}

      {/* ── Carteira ── */}
      <div className="fin-card fin-card--flush">
        <div className="fin-card__head">
          <div>
            <div className="fin-card__title">Carteira</div>
            <div className="fin-card__sub">
              {resumo.atual === null
                ? "valores de cadastro"
                : "cotação em tempo real, atualizada a cada minuto"}
            </div>
          </div>
        </div>

        {posicoes.length === 0 ? (
          <div className="fin-empty" style={{ paddingTop: 8 }}>
            <Wallet size={26} />
            <strong>Nenhum investimento cadastrado.</strong>
            <span style={{ maxWidth: "44ch" }}>
              Cadastre uma posição com ticker, quantidade e preço médio. A cotação
              atual vem sozinha.
            </span>
          </div>
        ) : (
          <div className="fin-carteira">
            <div className="fin-carteira__cab" aria-hidden="true">
              <span>Ativo</span>
              <span>Posição</span>
              <span>Investido</span>
              <span>Atual</span>
              <span>Resultado</span>
              <span />
            </div>

            {posicoes.map((p) => {
              const bom = p.lucro !== null && p.lucro >= 0;
              return (
                <div key={p.id} className="fin-carteira__linha">
                  <div className="fin-carteira__ativo">
                    <div className="fin-carteira__ticker">{p.ticker}</div>
                    <div className="fin-carteira__nome">
                      {p.cotacao?.nome || `desde ${dataCurta(p.data)}`}
                    </div>
                  </div>

                  <div className="fin-carteira__cel" data-rotulo="Posição">
                    <span className="fin-num">{qtd(p.quantidade)}</span>
                    <small>a {brl(p.precoMedio)}</small>
                  </div>

                  <div className="fin-carteira__cel" data-rotulo="Investido">
                    <span className="fin-num">{brl(p.investido)}</span>
                  </div>

                  <div className="fin-carteira__cel" data-rotulo="Atual">
                    {p.atual === null ? (
                      <span className="fin-carteira__sem">sem cotação</span>
                    ) : (
                      <>
                        <span className="fin-num">{brl(p.atual)}</span>
                        <small>{brl(p.cotacao.preco)} por unid.</small>
                      </>
                    )}
                  </div>

                  <div
                    className="fin-carteira__cel"
                    data-rotulo="Resultado"
                    style={{ color: p.lucro === null ? "var(--fin-muted)" : bom ? "var(--fin-in)" : "var(--fin-out)" }}
                  >
                    {p.lucro === null ? (
                      <span className="fin-carteira__sem">n/d</span>
                    ) : (
                      <>
                        <span className="fin-num">
                          {bom ? "+" : ""}
                          {brl(p.lucro)}
                        </span>
                        <small style={{ color: "inherit" }}>{pct(p.lucroPct)}</small>
                      </>
                    )}
                  </div>

                  <button
                    className="fin-lanc-item__excluir"
                    onClick={() => excluir(p)}
                    disabled={apagando === p.id}
                    aria-label={`Remover ${p.ticker}`}
                    title="Remover"
                  >
                    {apagando === p.id ? (
                      <Loader2 size={14} className="fin-spin" />
                    ) : (
                      <Trash2 size={14} />
                    )}
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {toast && (
        <div className={`fin-toast fin-toast--${toast.tipo}`} role="status">
          {toast.msg}
        </div>
      )}
    </>
  );
}

function Kpi({ cor, icone: Icone, label, valor, sub, tingido = false }) {
  return (
    <div className="fin-kpi" style={{ "--kc": cor }}>
      <div className="fin-kpi__top">
        <span className="fin-kpi__label">{label}</span>
        <Icone size={14} />
      </div>
      <div className={`fin-kpi__val${tingido ? " fin-kpi__val--tinted" : ""}`}>{valor}</div>
      <div className="fin-kpi__sub">{sub}</div>
      <div className="fin-kpi__bar" />
    </div>
  );
}
