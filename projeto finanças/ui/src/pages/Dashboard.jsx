import {
  AlertTriangle,
  ArrowDownLeft,
  ArrowUpRight,
  CalendarClock,
  CheckCircle2,
  Loader2,
  PiggyBank,
  ShieldAlert,
  Wallet,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { BarChart, DonutChart, EmptyChart, LineChart } from "../components/Charts";
import { criarMapaDeCores } from "../services/cores";
import {
  brl,
  brlCurto,
  carregarOrcamentos,
  categorias as extrairCategorias,
  chaveMes,
  gastosPorCategoria,
  listarTransacoes,
  pontosDeAtencao,
  resumoDoMes,
  saldoAtual,
  serieEntradasSaidas,
  serieSaldoAcumulado,
  ultimosMeses,
} from "../services/financasService";

const ICONE_ATENCAO = {
  estouro: ShieldAlert,
  limite: AlertTriangle,
  atrasada: AlertTriangle,
  vencendo: CalendarClock,
};

const COR_ATENCAO = {
  estouro: "var(--fin-danger)",
  limite: "var(--fin-warn)",
  atrasada: "var(--fin-danger)",
  vencendo: "var(--fin-warn)",
};

export default function Dashboard() {
  const navigate = useNavigate();
  const [transacoes, setTransacoes] = useState([]);
  const [orcamentos, setOrcamentos] = useState({});
  const [carregando, setCarregando] = useState(true);
  const [falha, setFalha] = useState("");
  const [janela, setJanela] = useState(12);

  useEffect(() => {
    (async () => {
      try {
        const [ts, orc] = await Promise.all([listarTransacoes(), carregarOrcamentos()]);
        setTransacoes(ts);
        setOrcamentos(orc || {});
      } catch (e) {
        // Sessão que expirou no meio do uso volta para o login em vez de
        // mostrar um erro que o usuário não tem como resolver na tela.
        if (e.status === 401 || e.status === 403) {
          navigate("/login", { replace: true });
          return;
        }
        console.error("Falha ao ler as transações:", e);
        setFalha(e.message || "Erro ao carregar.");
      } finally {
        setCarregando(false);
      }
    })();
  }, [navigate]);

  const hoje = useMemo(() => new Date(), []);
  const mesAtual = chaveMes(hoje);

  const dados = useMemo(() => {
    if (!transacoes.length) return null;

    const meses = ultimosMeses(janela, hoje);
    const mesPassado = chaveMes(new Date(hoje.getFullYear(), hoje.getMonth() - 1, 1));

    // O mapa é montado sobre TODAS as categorias do histórico, não só as do
    // mês: assim a cor de "Moradia" é a mesma em agosto e em março.
    const corDaCategoria = criarMapaDeCores(extrairCategorias(transacoes));

    return {
      saldo: saldoAtual(transacoes),
      mes: resumoDoMes(transacoes, mesAtual),
      anterior: resumoDoMes(transacoes, mesPassado),
      serieSaldo: serieSaldoAcumulado(transacoes, meses),
      serieFluxo: serieEntradasSaidas(transacoes, meses),
      categorias: gastosPorCategoria(transacoes, mesAtual).map((c) => ({
        ...c,
        cor: corDaCategoria(c.label),
      })),
      atencao: pontosDeAtencao(transacoes, orcamentos, hoje),
    };
  }, [transacoes, orcamentos, janela, hoje, mesAtual]);

  if (carregando) {
    return (
      <div className="fin-loading">
        <Loader2 size={17} className="fin-spin" />
        <span>Lendo seus lançamentos...</span>
      </div>
    );
  }

  // Sem dado nenhum não é erro, é conta nova. Ainda assim a tela precisa
  // dizer o que fazer em vez de mostrar quatro zeros sem contexto.
  if (falha || !dados) {
    return (
      <>
        <CabecalhoPagina hoje={hoje} />
        <div className="fin-card">
          <div className="fin-empty">
            <PiggyBank size={30} />
            {falha ? (
              <>
                <strong>Não consegui carregar seus dados.</strong>
                <span>{falha}</span>
              </>
            ) : (
              <>
                <strong>Nenhum lançamento ainda.</strong>
                <span>Registre a primeira entrada ou saída para o painel ganhar vida.</span>
              </>
            )}
          </div>
        </div>
      </>
    );
  }

  const { saldo, mes, anterior, serieSaldo, serieFluxo, categorias, atencao } = dados;
  const estouros = atencao.filter((a) => a.tipo === "estouro");
  const criticos = atencao.filter((a) => a.tipo === "estouro" || a.tipo === "atrasada").length;

  // Variação das saídas contra o mês anterior, contexto para o KPI.
  const varSaidas =
    anterior.saidas > 0 ? Math.round(((mes.saidas - anterior.saidas) / anterior.saidas) * 100) : null;

  return (
    <>
      <CabecalhoPagina hoje={hoje} />

      {saldo < 0 && (
        <div className="fin-banner" style={{ "--bc": "var(--fin-danger)" }}>
          <ShieldAlert size={16} />
          <span>
            <strong>Saldo negativo.</strong> Você está {brl(Math.abs(saldo))} no vermelho
            considerando todo o histórico.
          </span>
        </div>
      )}

      {saldo >= 0 && estouros.length > 0 && (
        <div className="fin-banner" style={{ "--bc": "var(--fin-warn)" }}>
          <AlertTriangle size={16} />
          <span>
            <strong>
              {estouros.length} {estouros.length === 1 ? "categoria estourou" : "categorias estouraram"}
            </strong>{" "}
            o orçamento deste mês.
          </span>
        </div>
      )}

      {/* ── KPIs ── */}
      <div className="fin-kpis">
        <Kpi
          cor={saldo < 0 ? "var(--fin-danger)" : "var(--fin-accent)"}
          icone={Wallet}
          label="Saldo atual"
          valor={brl(saldo)}
          sub={`${transacoes.length} lançamentos no histórico`}
          tingido={saldo < 0}
        />
        <Kpi
          cor="var(--fin-in)"
          icone={ArrowUpRight}
          label="Entradas do mês"
          valor={brl(mes.entradas)}
          sub={anterior.entradas > 0 ? `mês anterior: ${brlCurto(anterior.entradas)}` : "primeiro mês"}
        />
        <Kpi
          cor="var(--fin-out)"
          icone={ArrowDownLeft}
          label="Saídas do mês"
          valor={brl(mes.saidas)}
          sub={
            varSaidas === null
              ? "sem base de comparação"
              : `${varSaidas > 0 ? "+" : ""}${varSaidas}% vs. mês anterior`
          }
        />
        <Kpi
          cor={criticos > 0 ? "var(--fin-danger)" : atencao.length > 0 ? "var(--fin-warn)" : "var(--fin-accent)"}
          icone={atencao.length > 0 ? AlertTriangle : CheckCircle2}
          label="Pontos de atenção"
          valor={String(atencao.length)}
          sub={
            atencao.length === 0
              ? "nada exigindo ação"
              : criticos > 0
                ? `${criticos} ${criticos === 1 ? "exige" : "exigem"} ação agora`
                : "acompanhe abaixo"
          }
          tingido={atencao.length > 0}
        />
      </div>

      {/* ── Saldo + atenção ── */}
      <div className="fin-grid-2">
        <div className="fin-card">
          <div className="fin-card__head">
            <div>
              <div className="fin-card__title">Evolução do saldo</div>
              <div className="fin-card__sub">acumulado ao fim de cada mês</div>
            </div>
            <div className="fin-seg">
              {[6, 12].map((n) => (
                <button
                  key={n}
                  className={janela === n ? "active" : ""}
                  onClick={() => setJanela(n)}
                >
                  {n} meses
                </button>
              ))}
            </div>
          </div>

          <LineChart
            data={serieSaldo}
            color={saldo < 0 ? "var(--fin-out)" : "var(--fin-accent)"}
            format={brl}
          />
        </div>

        <div className="fin-card fin-card--flush">
          <div className="fin-card__head">
            <div>
              <div className="fin-card__title">Precisa de atenção</div>
              <div className="fin-card__sub">vencimentos e orçamentos no limite</div>
            </div>
          </div>

          {atencao.length === 0 ? (
            <div className="fin-empty" style={{ paddingTop: 8 }}>
              <CheckCircle2 size={26} />
              <span>Nada vencendo e nenhum orçamento estourado.</span>
            </div>
          ) : (
            <div className="fin-list">
              {atencao.slice(0, 6).map((item) => {
                const Icone = ICONE_ATENCAO[item.tipo] || AlertTriangle;
                return (
                  <div
                    key={item.id}
                    className="fin-list__item"
                    style={{ "--ic": COR_ATENCAO[item.tipo] }}
                  >
                    <div className="fin-list__ico">
                      <Icone size={15} />
                    </div>
                    <div className="fin-list__body">
                      <div className="fin-list__name">{item.titulo}</div>
                      <div className="fin-list__meta">{item.detalhe}</div>
                    </div>
                    <div className="fin-list__val">{brlCurto(item.valor)}</div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* ── Fluxo + categorias ── */}
      <div className="fin-grid-2 fin-grid-2--even">
        <div className="fin-card">
          <div className="fin-card__head">
            <div>
              <div className="fin-card__title">Entradas e saídas</div>
              <div className="fin-card__sub">comparação mês a mês</div>
            </div>
            <div className="fin-card__aside">
              <div
                className="fin-card__aside-val fin-num"
                style={{ color: mes.resultado >= 0 ? "var(--fin-in)" : "var(--fin-out)" }}
              >
                {mes.resultado >= 0 ? "+" : ""}
                {brl(mes.resultado)}
              </div>
              <div className="fin-card__aside-lbl">resultado do mês</div>
            </div>
          </div>

          <BarChart
            data={serieFluxo}
            series={[
              { nome: "Entradas", cor: "var(--fin-in)" },
              { nome: "Saídas", cor: "var(--fin-out)" },
            ]}
            format={brl}
          />
        </div>

        <div className="fin-card">
          <div className="fin-card__head">
            <div>
              <div className="fin-card__title">Gastos por categoria</div>
              <div className="fin-card__sub">no mês corrente</div>
            </div>
          </div>

          {categorias.length === 0 ? (
            <EmptyChart label="Nenhuma saída registrada neste mês" />
          ) : (
            <DonutChart segments={categorias} format={brlCurto} unidade="em saídas" />
          )}
        </div>
      </div>
    </>
  );
}

function CabecalhoPagina({ hoje }) {
  const mes = hoje.toLocaleDateString("pt-BR", { month: "long", year: "numeric" });
  return (
    <div className="fin-page-head">
      <div>
        <h1 className="fin-page-title">Visão geral</h1>
        <p className="fin-page-sub">
          {mes.charAt(0).toUpperCase() + mes.slice(1)} · atualizado agora
        </p>
      </div>
    </div>
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
