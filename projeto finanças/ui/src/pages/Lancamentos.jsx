// Tela de Entradas e de Saídas.
//
// As duas são a mesma coisa com `natureza` trocada: mesma rota, mesmos
// campos, mesmos totais. Manter um componente só evita que uma ganhe um
// ajuste e a outra fique para trás.
//
// A diferença fica em `PERFIS`: cor, textos e ícones.

import {
  ArrowDownLeft,
  ArrowUpRight,
  CalendarDays,
  Check,
  Loader2,
  Plus,
  Repeat,
  Trash2,
  X,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { criarMapaDeCores } from "../services/cores";
import {
  apagarTransacao,
  brl,
  chaveMes,
  criarTransacao,
  dataCurta,
  listarTransacoes,
  mesDaTransacao,
  rotuloMes,
  ultimosMeses,
} from "../services/financasService";

const PERFIS = {
  receita: {
    titulo: "Entradas",
    subtitulo: "Tudo que entra: salário, freelas, rendimentos",
    cor: "var(--fin-in)",
    icone: ArrowUpRight,
    rotuloNovo: "Nova entrada",
    vazio: "Nenhuma entrada registrada ainda.",
    exemploNome: "Salário",
    exemploCategoria: "Salário",
  },
  despesa: {
    titulo: "Saídas",
    subtitulo: "Tudo que sai: contas, compras, assinaturas",
    cor: "var(--fin-out)",
    icone: ArrowDownLeft,
    rotuloNovo: "Nova saída",
    vazio: "Nenhuma saída registrada ainda.",
    exemploNome: "Aluguel",
    exemploCategoria: "Moradia",
  },
};

const hojeISO = () => new Date().toISOString().slice(0, 10);

const formularioVazio = () => ({
  nome: "",
  valor: "",
  data: hojeISO(),
  categoria: "",
  recorrencia: "unica",
});

export default function Lancamentos({ natureza }) {
  const navigate = useNavigate();
  const perfil = PERFIS[natureza];

  const [transacoes, setTransacoes] = useState([]);
  const [carregando, setCarregando] = useState(true);
  const [falha, setFalha] = useState("");
  const [toast, setToast] = useState(null);

  const [mes, setMes] = useState(() => chaveMes(new Date()));
  const [formAberto, setFormAberto] = useState(false);
  const [form, setForm] = useState(formularioVazio);
  const [salvando, setSalvando] = useState(false);
  const [apagando, setApagando] = useState(null);

  const avisar = (msg, tipo = "success") => {
    setToast({ msg, tipo });
    setTimeout(() => setToast(null), 3000);
  };

  const carregar = async () => {
    try {
      setTransacoes(await listarTransacoes());
      setFalha("");
    } catch (e) {
      if (e.status === 401 || e.status === 403) {
        navigate("/login", { replace: true });
        return;
      }
      setFalha(e.message || "Erro ao carregar.");
    } finally {
      setCarregando(false);
    }
  };

  useEffect(() => {
    carregar();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [natureza]);

  // Ao trocar de aba o formulário aberto e o mês escolhido não fazem mais
  // sentido: são de outro contexto.
  useEffect(() => {
    setFormAberto(false);
    setForm(formularioVazio());
    setMes(chaveMes(new Date()));
  }, [natureza]);

  const dados = useMemo(() => {
    const minhas = transacoes.filter((t) => t.natureza === natureza);
    const meses = ultimosMeses(12);

    const doMes = minhas
      .filter((t) => mesDaTransacao(t) === mes)
      .sort((a, b) => b.data.localeCompare(a.data));

    const totalMes = doMes.reduce((s, t) => s + t.valor, 0);

    const totalUltimos12 = minhas
      .filter((t) => meses.includes(mesDaTransacao(t)))
      .reduce((s, t) => s + t.valor, 0);

    const ano = mes.slice(0, 4);
    const totalAno = minhas
      .filter((t) => mesDaTransacao(t).startsWith(ano))
      .reduce((s, t) => s + t.valor, 0);

    // Só meses que existem no histórico entram no seletor, mais o mês
    // atual. Listar 12 meses vazios seria ruído.
    const mesesComDado = [...new Set(minhas.map(mesDaTransacao))];
    const opcoes = [...new Set([...mesesComDado, chaveMes(new Date())])]
      .sort()
      .reverse();

    return {
      doMes,
      totalMes,
      mediaMensal: totalUltimos12 / 12,
      totalAno,
      ano,
      opcoes,
      categorias: [...new Set(minhas.map((t) => t.categoria))].sort(),
      corDaCategoria: criarMapaDeCores(minhas.map((t) => t.categoria)),
    };
  }, [transacoes, natureza, mes]);

  const salvar = async (e) => {
    e.preventDefault();
    setSalvando(true);
    try {
      await criarTransacao({
        nome: form.nome,
        valor: form.valor,
        data: form.data,
        natureza,
        categoria: form.categoria,
        recorrencia: form.recorrencia,
      });
      setForm(formularioVazio());
      setFormAberto(false);
      // Recarrega da API em vez de inserir na lista local: assim o id e os
      // valores normalizados vêm do banco, não de um palpite do cliente.
      await carregar();
      // Pula para o mês do lançamento, senão ele "somem" ao ser salvo num
      // mês diferente do que está sendo visto.
      setMes(form.data.slice(0, 7));
      avisar("Lançamento adicionado.");
    } catch (err) {
      avisar(err.message, "error");
    } finally {
      setSalvando(false);
    }
  };

  const excluir = async (t) => {
    setApagando(t.id);
    try {
      await apagarTransacao(t.id);
      setTransacoes((lista) => lista.filter((x) => x.id !== t.id));
      avisar("Lançamento excluído.");
    } catch (err) {
      avisar(err.message, "error");
    } finally {
      setApagando(null);
    }
  };

  if (carregando) {
    return (
      <div className="fin-loading">
        <Loader2 size={17} className="fin-spin" />
        <span>Carregando lançamentos...</span>
      </div>
    );
  }

  const Icone = perfil.icone;

  return (
    <>
      <div className="fin-page-head">
        <div>
          <h1 className="fin-page-title">{perfil.titulo}</h1>
          <p className="fin-page-sub">{perfil.subtitulo}</p>
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
              <Plus size={14} /> {perfil.rotuloNovo}
            </>
          )}
        </button>
      </div>

      {falha && (
        <div className="fin-banner" style={{ "--bc": "var(--fin-danger)" }}>
          <span>{falha}</span>
        </div>
      )}

      {/* ── KPIs ── */}
      <div className="fin-kpis">
        <Kpi
          cor={perfil.cor}
          icone={Icone}
          label={`Total de ${rotuloMes(mes)}`}
          valor={brl(dados.totalMes)}
          sub={`${dados.doMes.length} ${dados.doMes.length === 1 ? "lançamento" : "lançamentos"}`}
        />
        <Kpi
          cor="var(--fin-cat-6)"
          icone={CalendarDays}
          label="Média mensal"
          valor={brl(dados.mediaMensal)}
          sub="últimos 12 meses"
        />
        <Kpi
          cor={perfil.cor}
          icone={Icone}
          label={`Total em ${dados.ano}`}
          valor={brl(dados.totalAno)}
          sub="acumulado no ano"
        />
      </div>

      {/* ── Formulário ── */}
      {formAberto && (
        <div className="fin-card" style={{ marginBottom: 12 }}>
          <div className="fin-cfg-card__title">
            <Plus size={15} /> {perfil.rotuloNovo}
          </div>

          <form className="fin-form" onSubmit={salvar}>
            <div className="fin-lanc-form">
              <div className="fin-field">
                <label htmlFor="l-nome">Descrição</label>
                <input
                  id="l-nome"
                  value={form.nome}
                  onChange={(e) => setForm({ ...form, nome: e.target.value })}
                  placeholder={perfil.exemploNome}
                  maxLength={160}
                  required
                  autoFocus
                />
              </div>

              <div className="fin-field">
                <label htmlFor="l-valor">Valor (R$)</label>
                <input
                  id="l-valor"
                  type="number"
                  step="0.01"
                  min="0.01"
                  inputMode="decimal"
                  value={form.valor}
                  onChange={(e) => setForm({ ...form, valor: e.target.value })}
                  placeholder="0,00"
                  required
                />
              </div>

              <div className="fin-field">
                <label htmlFor="l-data">Data</label>
                <input
                  id="l-data"
                  type="date"
                  value={form.data}
                  onChange={(e) => setForm({ ...form, data: e.target.value })}
                  required
                />
              </div>

              <div className="fin-field">
                <label htmlFor="l-cat">Categoria</label>
                {/* datalist e não select: sugere o que já existe sem
                    impedir uma categoria nova. */}
                <input
                  id="l-cat"
                  list="categorias-existentes"
                  value={form.categoria}
                  onChange={(e) => setForm({ ...form, categoria: e.target.value })}
                  placeholder={perfil.exemploCategoria}
                  maxLength={80}
                />
                <datalist id="categorias-existentes">
                  {dados.categorias.map((c) => (
                    <option key={c} value={c} />
                  ))}
                </datalist>
              </div>

              <div className="fin-field">
                <label htmlFor="l-rec">Recorrência</label>
                <select
                  id="l-rec"
                  value={form.recorrencia}
                  onChange={(e) => setForm({ ...form, recorrencia: e.target.value })}
                >
                  <option value="unica">Única</option>
                  <option value="mensal">Mensal</option>
                </select>
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
                    <Check size={13} /> Adicionar
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

      {/* ── Lista ── */}
      <div className="fin-card fin-card--flush">
        <div className="fin-card__head">
          <div>
            <div className="fin-card__title">Lançamentos</div>
            <div className="fin-card__sub">{rotuloMes(mes)} de {mes.slice(0, 4)}</div>
          </div>

          <select
            className="fin-select-mes"
            value={mes}
            onChange={(e) => setMes(e.target.value)}
            aria-label="Escolher mês"
          >
            {dados.opcoes.map((m) => (
              <option key={m} value={m}>
                {rotuloMes(m)}/{m.slice(2, 4)}
              </option>
            ))}
          </select>
        </div>

        {dados.doMes.length === 0 ? (
          <div className="fin-empty" style={{ paddingTop: 8 }}>
            <Icone size={26} />
            <span>
              {transacoes.some((t) => t.natureza === natureza)
                ? `Nada em ${rotuloMes(mes)}. Escolha outro mês ou adicione um lançamento.`
                : perfil.vazio}
            </span>
          </div>
        ) : (
          <div className="fin-lanc-lista">
            {dados.doMes.map((t) => (
              <div key={t.id} className="fin-lanc-item">
                <div className="fin-lanc-item__data">{dataCurta(t.data)}</div>

                <div className="fin-lanc-item__info">
                  <div className="fin-lanc-item__nome">{t.nome}</div>
                  <div className="fin-lanc-item__meta">
                    <span
                      className="fin-lanc-item__ponto"
                      style={{ background: dados.corDaCategoria(t.categoria) }}
                    />
                    {t.categoria}
                    {t.recorrencia === "mensal" && (
                      <span className="fin-tag">
                        <Repeat size={10} /> mensal
                      </span>
                    )}
                  </div>
                </div>

                <div className="fin-lanc-item__valor" style={{ color: perfil.cor }}>
                  {natureza === "receita" ? "+" : "−"} {brl(t.valor)}
                </div>

                <button
                  className="fin-lanc-item__excluir"
                  onClick={() => excluir(t)}
                  disabled={apagando === t.id}
                  aria-label={`Excluir ${t.nome}`}
                  title="Excluir"
                >
                  {apagando === t.id ? (
                    <Loader2 size={14} className="fin-spin" />
                  ) : (
                    <Trash2 size={14} />
                  )}
                </button>
              </div>
            ))}
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
