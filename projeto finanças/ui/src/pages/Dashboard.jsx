import {
  AlertTriangle,
  ArrowDownLeft,
  ArrowRight,
  ArrowUpRight,
  CalendarClock,
  CheckCircle2,
  Landmark,
  Loader2,
  PiggyBank,
  Repeat,
  ShieldAlert,
  TrendingUp,
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
  contaveis,
  dataCurta,
  gastosPorCategoria,
  listarTransacoes,
  pontosDeAtencao,
  resumoDoMes,
  saldoAtual,
  serieEntradasSaidas,
  serieSaldoAcumulado,
  ultimosMeses,
} from "../services/financasService";
import { calcularPosicao, listarInvestimentos } from "../services/investimentosService";
import {
  faturasAVencer,
  importarSeFaltar,
  lerOpenFinance,
  resumoOpenFinance,
} from "../services/openfinanceService";
import {
  alertasDeRecorrentes,
  detectarRecorrentes,
  previsaoDoMes,
} from "../services/previsaoService";

const ICONE_ATENCAO = {
  estouro: ShieldAlert,
  limite: AlertTriangle,
  atrasada: AlertTriangle,
  vencendo: CalendarClock,
  aumento: TrendingUp,
  nova: Repeat,
};

const COR_ATENCAO = {
  estouro: "var(--fin-danger)",
  limite: "var(--fin-warn)",
  atrasada: "var(--fin-danger)",
  vencendo: "var(--fin-warn)",
  aumento: "var(--fin-warn)",
  nova: "var(--fin-muted)",
};

// O que o cabeçalho diz sobre a conversa com os bancos.
const TEXTO_SYNC = {
  lendo: "lendo os bancos...",
  importando: "trazendo transações dos bancos...",
  ok: "bancos sincronizados",
  falhou: "não consegui falar com os bancos agora",
};

export default function Dashboard() {
  const navigate = useNavigate();
  const [transacoes, setTransacoes] = useState([]);
  const [orcamentos, setOrcamentos] = useState({});
  const [carregando, setCarregando] = useState(true);
  const [falha, setFalha] = useState("");
  const [janela, setJanela] = useState(12);

  // Open Finance e carteira chegam depois e só acrescentam: a tela não
  // espera a Pluggy nem a brapi para mostrar o que já está no banco local.
  const [openFinance, setOpenFinance] = useState(null);
  const [sync, setSync] = useState("");
  const [carteira, setCarteira] = useState([]);

  useEffect(() => {
    (async () => {
      try {
        const [ts, orc] = await Promise.all([listarTransacoes(), carregarOrcamentos()]);
        setTransacoes(contaveis(ts));
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

  useEffect(() => {
    let viva = true;

    (async () => {
      try {
        setSync("lendo");
        const r = await lerOpenFinance();
        if (!viva) return;
        setOpenFinance(r);
        if (!r.conexoes?.length) {
          setSync("");
          return;
        }
        setSync("importando");
        const importacao = await importarSeFaltar(r);
        if (!viva) return;
        if (importacao?.novas > 0 || importacao?.removidas > 0) {
          setTransacoes(contaveis(await listarTransacoes()));
        }
        if (viva) setSync("ok");
      } catch (e) {
        console.error("Falha ao sincronizar com os bancos:", e);
        if (viva) setSync("falhou");
      }
    })();

    listarInvestimentos()
      .then((r) => viva && setCarteira((r.itens || []).map(calcularPosicao)))
      .catch((e) => console.error("Falha ao ler a carteira:", e));

    return () => {
      viva = false;
    };
  }, []);

  const hoje = useMemo(() => new Date(), []);
  const mesAtual = chaveMes(hoje);

  const bancos = useMemo(() => {
    const r = openFinance ? resumoOpenFinance(openFinance.conexoes) : null;
    // Conexão cadastrada que não respondeu não conta: sem nenhum saldo
    // lido, a tela volta para o saldo calculado pelos lançamentos.
    return r && r.contas > 0 ? r : null;
  }, [openFinance]);

  const dados = useMemo(() => {
    if (!transacoes.length) return null;

    const meses = ultimosMeses(janela, hoje);
    const mesPassado = chaveMes(new Date(hoje.getFullYear(), hoje.getMonth() - 1, 1));

    // O mapa é montado sobre TODAS as categorias do histórico, não só as do
    // mês: assim a cor de "Moradia" é a mesma em agosto e em março.
    const corDaCategoria = criarMapaDeCores(extrairCategorias(transacoes));

    // Com banco conectado, a curva termina no dinheiro livre de verdade:
    // saldo das contas menos o que já está gasto nas faturas abertas. As
    // compras do cartão já são saídas nos lançamentos, então é essa a
    // conta que bate com eles.
    const ancora = bancos ? bancos.saldo - bancos.emAberto : null;
    const saldo = bancos ? bancos.saldo : saldoAtual(transacoes);
    const recorrentes = detectarRecorrentes(transacoes, hoje);

    return {
      saldo,
      recorrentes,
      previsao: previsaoDoMes({
        saldoHoje: saldo,
        recorrentes,
        cartoes: (openFinance?.conexoes || []).flatMap((c) => c.dados?.cartoes || []),
        hoje,
      }),
      mes: resumoDoMes(transacoes, mesAtual),
      anterior: resumoDoMes(transacoes, mesPassado),
      serieSaldo: serieSaldoAcumulado(transacoes, meses, ancora),
      serieFluxo: serieEntradasSaidas(transacoes, meses),
      categorias: gastosPorCategoria(transacoes, mesAtual).map((c) => ({
        ...c,
        cor: corDaCategoria(c.label),
      })),
      atencao: [
        ...pontosDeAtencao(transacoes, orcamentos, hoje),
        ...faturasAVencer(openFinance?.conexoes || [], hoje),
        ...alertasDeRecorrentes(recorrentes),
      ].sort((a, b) => a.ordem - b.ordem || b.valor - a.valor),
    };
  }, [transacoes, orcamentos, janela, hoje, mesAtual, bancos, openFinance]);

  const patrimonio = useMemo(() => {
    const valorCarteira = carteira.reduce((s, p) => s + (p.atual ?? p.investido), 0);
    if (!bancos && !carteira.length) return null;
    return {
      bancos,
      carteira: carteira.length ? valorCarteira : null,
      ativos: carteira.length,
      cotadaParcial: carteira.some((p) => p.atual == null),
      total:
        (bancos ? bancos.saldo + bancos.investido - bancos.emAberto : 0) + valorCarteira,
    };
  }, [bancos, carteira]);

  if (carregando) {
    return (
      <div className="fin-loading">
        <Loader2 size={17} className="fin-spin" />
        <span>Lendo seus lançamentos...</span>
      </div>
    );
  }

  // Primeira importação de um banco recém-conectado: a lista local ainda
  // está vazia, mas os lançamentos estão a caminho.
  if (!falha && !dados && (sync === "lendo" || sync === "importando")) {
    return (
      <>
        <CabecalhoPagina hoje={hoje} sync={sync} />
        <div className="fin-loading">
          <Loader2 size={17} className="fin-spin" />
          <span>Trazendo suas transações dos bancos...</span>
        </div>
      </>
    );
  }

  // Sem dado nenhum não é erro, é conta nova. Ainda assim a tela precisa
  // dizer o que fazer em vez de mostrar quatro zeros sem contexto.
  if (falha || !dados) {
    return (
      <>
        <CabecalhoPagina hoje={hoje} sync={sync} />
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
                <span>
                  Registre a primeira entrada ou saída, ou conecte seus bancos em Contas, para o
                  painel ganhar vida.
                </span>
              </>
            )}
          </div>
        </div>
      </>
    );
  }

  const { saldo, mes, anterior, serieSaldo, serieFluxo, categorias, atencao, recorrentes, previsao } =
    dados;
  const estouros = atencao.filter((a) => a.tipo === "estouro");
  const criticos = atencao.filter((a) => a.tipo === "estouro" || a.tipo === "atrasada").length;
  const saldoFinalSerie = serieSaldo.length ? serieSaldo[serieSaldo.length - 1].valor : saldo;

  // Variação das saídas contra o mês anterior, contexto para o KPI.
  const varSaidas =
    anterior.saidas > 0 ? Math.round(((mes.saidas - anterior.saidas) / anterior.saidas) * 100) : null;

  return (
    <>
      <CabecalhoPagina hoje={hoje} sync={sync} />

      {saldo < 0 && (
        <div className="fin-banner" style={{ "--bc": "var(--fin-danger)" }}>
          <ShieldAlert size={16} />
          <span>
            <strong>Saldo negativo.</strong> Você está {brl(Math.abs(saldo))} no vermelho
            {bancos ? " somando as contas conectadas." : " considerando todo o histórico."}
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
          icone={bancos ? Landmark : Wallet}
          label={bancos ? "Saldo em contas" : "Saldo atual"}
          valor={brl(saldo)}
          sub={
            bancos
              ? `${bancos.contas} ${bancos.contas === 1 ? "conta conectada" : "contas conectadas"}`
              : `${transacoes.length} lançamentos no histórico`
          }
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

      {patrimonio && <Patrimonio p={patrimonio} onVerContas={() => navigate("/app/contas")} />}

      {/* ── Previsão + recorrentes ── */}
      <div className="fin-grid-2 fin-grid-2--even">
        <Previsao p={previsao} comBanco={Boolean(bancos)} />
        <Recorrentes lista={recorrentes} />
      </div>

      {/* ── Saldo + atenção ── */}
      <div className="fin-grid-2">
        <div className="fin-card">
          <div className="fin-card__head">
            <div>
              <div className="fin-card__title">Evolução do saldo</div>
              <div className="fin-card__sub">
                {bancos ? "contas menos faturas em aberto, ao fim de cada mês" : "acumulado ao fim de cada mês"}
              </div>
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
            color={saldoFinalSerie < 0 ? "var(--fin-out)" : "var(--fin-accent)"}
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

function CabecalhoPagina({ hoje, sync }) {
  const mes = hoje.toLocaleDateString("pt-BR", { month: "long", year: "numeric" });
  return (
    <div className="fin-page-head">
      <div>
        <h1 className="fin-page-title">Visão geral</h1>
        <p className="fin-page-sub">
          {mes.charAt(0).toUpperCase() + mes.slice(1)} · {TEXTO_SYNC[sync] || "atualizado agora"}
        </p>
      </div>
    </div>
  );
}

/** Onde o dinheiro está agora: bancos, investimentos e o que as faturas já comeram. */
function Patrimonio({ p, onVerContas }) {
  const { bancos } = p;
  return (
    <div className="fin-card" style={{ marginBottom: 12 }}>
      <div className="fin-card__head">
        <div>
          <div className="fin-card__title">Patrimônio</div>
          <div className="fin-card__sub">onde está seu dinheiro agora</div>
        </div>
        {bancos && (
          <button className="fin-btn fin-btn--ghost fin-btn--sm" onClick={onVerContas}>
            Ver contas <ArrowRight size={13} />
          </button>
        )}
      </div>

      <div className="fin-patri">
        {bancos && (
          <>
            <ItemPatrimonio
              label="Contas"
              valor={bancos.saldo}
              sub={`${bancos.contas} ${bancos.contas === 1 ? "conta" : "contas"}`}
            />
            <ItemPatrimonio
              label="Investimentos nos bancos"
              valor={bancos.investido}
              sub={
                bancos.investimentos
                  ? `${bancos.investimentos} ${bancos.investimentos === 1 ? "aplicação" : "aplicações"}, líquido`
                  : "nenhuma aplicação"
              }
            />
          </>
        )}
        {p.carteira != null && (
          <ItemPatrimonio
            label="Carteira B3"
            valor={p.carteira}
            sub={`${p.ativos} ${p.ativos === 1 ? "posição" : "posições"}${p.cotadaParcial ? ", parte a preço médio" : ""}`}
          />
        )}
        {bancos && (
          <ItemPatrimonio
            label="Faturas em aberto"
            valor={-bancos.emAberto}
            cor="var(--fin-out)"
            sub={
              bancos.parcelado > 0
                ? `mais ${brlCurto(bancos.parcelado)} parcelados à frente`
                : `${bancos.cartoes} ${bancos.cartoes === 1 ? "cartão" : "cartões"}`
            }
          />
        )}
        <ItemPatrimonio
          total
          label="Patrimônio líquido"
          valor={p.total}
          cor={p.total < 0 ? "var(--fin-out)" : "var(--fin-in)"}
          sub="tudo somado, faturas descontadas"
        />
      </div>
    </div>
  );
}

/** Saldo de hoje até o fim do mês, com cada parcela da conta à vista. */
function Previsao({ p, comBanco }) {
  const linhas = [
    ...p.entradas.map((r) => ({ id: r.id, nome: r.nome, quando: `dia ${r.dia}`, valor: r.falta, sinal: 1 })),
    ...p.faturas.map((c) => ({
      id: `fat-${c.id}`,
      nome: `Fatura ${c.nome.trim()}`,
      quando: `vence ${dataCurta(c.faturaAtual.vencimento)}`,
      valor: c.faturaAtual.valor,
      sinal: -1,
    })),
    ...p.saidas.map((r) => ({
      id: r.id,
      nome: r.nome,
      quando: r.variavel ? `dia ${r.dia}, valor estimado` : `dia ${r.dia}`,
      valor: r.falta,
      sinal: -1,
    })),
  ];

  return (
    <div className="fin-card fin-card--flush">
      <div className="fin-card__head">
        <div>
          <div className="fin-card__title">Previsão até {dataCurta(p.fim)}</div>
          <div className="fin-card__sub">
            {comBanco ? "saldo das contas" : "saldo dos lançamentos"} + o que ainda deve entrar e sair
          </div>
        </div>
        <div className="fin-card__aside">
          <div
            className="fin-card__aside-val fin-num"
            style={{ color: p.saldoFinal < 0 ? "var(--fin-out)" : "var(--fin-in)" }}
          >
            {brl(p.saldoFinal)}
          </div>
          <div className="fin-card__aside-lbl">no fim do mês</div>
        </div>
      </div>

      <div className="fin-list">
        <div className="fin-list__item">
          <div className="fin-list__ico" style={{ "--ic": "var(--fin-accent)" }}>
            <Wallet size={14} />
          </div>
          <div className="fin-list__body">
            <div className="fin-list__name">Saldo de hoje</div>
          </div>
          <div className="fin-list__val">{brl(p.saldoHoje)}</div>
        </div>

        {linhas.length === 0 ? (
          <div className="fin-empty" style={{ paddingTop: 4 }}>
            <span>Nada recorrente pendente até o fim do mês.</span>
          </div>
        ) : (
          linhas.slice(0, 7).map((l) => (
            <div key={l.id} className="fin-list__item" style={{ "--ic": l.sinal > 0 ? "var(--fin-in)" : "var(--fin-out)" }}>
              <div className="fin-list__ico">
                {l.sinal > 0 ? <ArrowUpRight size={14} /> : <ArrowDownLeft size={14} />}
              </div>
              <div className="fin-list__body">
                <div className="fin-list__name">{l.nome}</div>
                <div className="fin-list__meta">{l.quando}</div>
              </div>
              <div className="fin-list__val">
                {l.sinal > 0 ? "+" : "−"} {brl(l.valor)}
              </div>
            </div>
          ))
        )}
      </div>
      {linhas.length > 7 && (
        <p className="fin-of-nota" style={{ padding: "0 15px 14px" }}>
          E mais {linhas.length - 7}. A previsão só conta o que se repete todo mês; gasto avulso não entra.
        </p>
      )}
    </div>
  );
}

/** O que se repete todo mês, com o total fixo de saídas. */
function Recorrentes({ lista }) {
  const saidas = lista.filter((r) => r.natureza === "despesa");
  const total = saidas.reduce((s, r) => s + r.valorMensal, 0);

  return (
    <div className="fin-card fin-card--flush">
      <div className="fin-card__head">
        <div>
          <div className="fin-card__title">Recorrentes</div>
          <div className="fin-card__sub">o que se repete nos últimos 6 meses</div>
        </div>
        {saidas.length > 0 && (
          <div className="fin-card__aside">
            <div className="fin-card__aside-val fin-num" style={{ color: "var(--fin-out)" }}>
              {brl(total)}
            </div>
            <div className="fin-card__aside-lbl">de saídas por mês</div>
          </div>
        )}
      </div>

      {saidas.length === 0 ? (
        <div className="fin-empty" style={{ paddingTop: 8 }}>
          <Repeat size={24} />
          <span>Ainda não há meses suficientes para achar o que se repete.</span>
        </div>
      ) : (
        <div className="fin-list">
          {saidas.slice(0, 8).map((r) => (
            <div key={r.id} className="fin-list__item" style={{ "--ic": "var(--fin-out)" }}>
              <div className="fin-list__ico">
                <Repeat size={14} />
              </div>
              <div className="fin-list__body">
                <div className="fin-list__name">{r.nome}</div>
                <div className="fin-list__meta">
                  {r.categoria} · {r.meio === "cartao" ? "cartão" : "conta"} · dia {r.dia}
                  {r.subiu && <span className="fin-tag fin-tag--alerta">subiu</span>}
                  {r.nova && <span className="fin-tag">nova</span>}
                  {r.variavel && <span className="fin-tag">varia</span>}
                </div>
              </div>
              <div className="fin-list__val">
                {brl(r.valorMensal)}
                <small>por mês</small>
              </div>
            </div>
          ))}
        </div>
      )}
      {saidas.length > 8 && (
        <p className="fin-of-nota" style={{ padding: "0 15px 14px" }}>
          E mais {saidas.length - 8} menores.
        </p>
      )}
    </div>
  );
}

function ItemPatrimonio({ label, valor, sub, cor = "var(--fin-text)", total = false }) {
  return (
    <div className={`fin-patri__item${total ? " fin-patri__item--total" : ""}`}>
      <div className="fin-patri__lbl">{label}</div>
      <div className="fin-patri__val" style={{ "--pc": cor }}>
        {brl(valor)}
      </div>
      <div className="fin-patri__sub">{sub}</div>
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
