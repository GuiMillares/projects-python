// Contas e cartões pelo Open Finance (Pluggy, via Meu Pluggy).
//
// Saldo e fatura não moram no banco local: cada carga da tela lê da Pluggy
// (com um minuto de cache na API). A Pluggy por sua vez só sabe o que o
// banco entregou na última sincronização, por isso cada conexão mostra
// quando foi atualizada e tem o botão de sincronizar na hora.
//
// As faturas futuras são PROJEÇÃO das compras parceladas: o Open Finance não
// entrega fatura futura pronta. A tela diz isso com todas as letras.

import {
  AlertTriangle,
  Check,
  ChevronDown,
  CloudOff,
  CreditCard,
  Download,
  KeyRound,
  Landmark,
  Link2,
  Loader2,
  Lock,
  PiggyBank,
  Plug,
  RefreshCw,
  SearchCheck,
  Trash2,
  Unlock,
  Users,
  Wallet,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { PluggyConnect } from "react-pluggy-connect";
import { useNavigate } from "react-router-dom";
import SeletorVisao from "../components/SeletorVisao";
import { useVisao } from "../context/VisaoProvider";
import ConfirmarExclusao from "../components/ConfirmarExclusao";
import { brl, dataCurta, rotuloMes } from "../services/financasService";
import {
  conectar,
  desconectar,
  haQuanto,
  importarTransacoes,
  lerOpenFinance,
  marcarContaPrivada,
  removerCredencial,
  resumoOpenFinance,
  salvarCredencial,
  sincronizar,
  tokenDoWidget,
} from "../services/openfinanceService";

// Sincronização em andamento: relê a cada 5s, por no máximo 3 minutos.
const INTERVALO_MS = 5000;
const MAX_RELEITURAS = 36;

const hojeISO = () => new Date().toISOString().slice(0, 10);

const mesAno = (ym) => `${rotuloMes(ym)}/${String(ym).slice(2, 4)}`;

const COR_STATUS = {
  UPDATED: "var(--fin-in)",
  UPDATING: "var(--fin-muted)",
  LOGIN_ERROR: "var(--fin-danger)",
  OUTDATED: "var(--fin-warn)",
  WAITING_USER_INPUT: "var(--fin-warn)",
};

export default function Contas() {
  const navigate = useNavigate();
  // No Juntos e na visão do par, as contas dos outros vêm só para ler: cada
  // uma lida com a credencial Pluggy do dono dela, no servidor.
  const { visao, temEspaco } = useVisao();

  const [resposta, setResposta] = useState(null);
  const [carregando, setCarregando] = useState(true);
  const [atualizando, setAtualizando] = useState(false);
  const [falha, setFalha] = useState("");
  const [toast, setToast] = useState(null);

  const [novoId, setNovoId] = useState("");
  const [conectando, setConectando] = useState(false);
  // { token, conexaoId }: conexaoId presente = widget aberto para reconectar.
  const [widget, setWidget] = useState(null);
  const [abrindoWidget, setAbrindoWidget] = useState(false);
  const [sincronizando, setSincronizando] = useState(() => new Set());
  const [paraRemover, setParaRemover] = useState(null);
  const [removendo, setRemovendo] = useState(false);

  const [importAberto, setImportAberto] = useState(false);
  const [desde, setDesde] = useState("");
  const [importando, setImportando] = useState(false);
  const [resultado, setResultado] = useState(null);

  const releiturasRef = useRef(0);

  const notificar = (msg, tipo = "success") => {
    setToast({ msg, tipo });
    setTimeout(() => setToast(null), 3500);
  };

  const carregar = useCallback(
    async ({ silencioso = false } = {}) => {
      if (silencioso) setAtualizando(true);
      try {
        const r = await lerOpenFinance(visao);
        setResposta(r);
        setDesde((d) => d || r.importarDesde);
        setFalha("");
      } catch (e) {
        if (e.status === 401 || e.status === 403) {
          navigate("/login", { replace: true });
          return;
        }
        setFalha(e.message || "Erro ao carregar as contas.");
      } finally {
        setCarregando(false);
        setAtualizando(false);
      }
    },
    [navigate, visao],
  );

  useEffect(() => {
    carregar();
  }, [carregar]);

  const conexoes = resposta?.conexoes || [];
  const minhas = conexoes.filter((c) => c.minha !== false);
  const algumSincronizando = conexoes.some((c) => c.dados?.status === "UPDATING");

  // Enquanto a Pluggy sincroniza, a tela relê sozinha até o status mudar.
  useEffect(() => {
    if (!algumSincronizando) {
      releiturasRef.current = 0;
      return;
    }
    if (releiturasRef.current >= MAX_RELEITURAS) return;
    const t = setTimeout(() => {
      releiturasRef.current += 1;
      carregar({ silencioso: true });
    }, INTERVALO_MS);
    return () => clearTimeout(t);
  }, [algumSincronizando, resposta, carregar]);

  const resumo = useMemo(() => resumoOpenFinance(conexoes), [conexoes]);

  const adicionar = async (e) => {
    e.preventDefault();
    setConectando(true);
    try {
      const r = await conectar(novoId.trim());
      setNovoId("");
      await carregar();
      notificar(`${r.instituicao} conectado.`);
    } catch (err) {
      notificar(err.message, "error");
    } finally {
      setConectando(false);
    }
  };

  const abrirWidget = async (conexaoId = null) => {
    setAbrindoWidget(true);
    try {
      const { accessToken } = await tokenDoWidget(conexaoId);
      setWidget({ token: accessToken, conexaoId });
    } catch (err) {
      notificar(err.message, "error");
    } finally {
      setAbrindoWidget(false);
    }
  };

  // O widget avisa o sucesso antes de fechar. Conexão nova é gravada aqui;
  // reconexão mantém o mesmo id, então basta reler.
  const widgetConectou = async ({ item }) => {
    try {
      if (widget?.conexaoId) {
        notificar("Conexão renovada.");
      } else {
        const primeira = conexoes.length === 0;
        const r = await conectar(item.id);
        // Fim do guia: a primeira conexão já abre a importação, que é o
        // que faz as transações aparecerem em Entradas e Saídas.
        if (primeira) {
          setImportAberto(true);
          notificar(`${r.instituicao} conectado. Agora traga suas transações.`);
        } else {
          notificar(`${r.instituicao} conectado.`);
        }
      }
      releiturasRef.current = 0;
      await carregar({ silencioso: true });
    } catch (err) {
      notificar(err.message, "error");
    }
  };

  const sincronizarConexao = async (c) => {
    setSincronizando((s) => new Set(s).add(c.id));
    try {
      const r = await sincronizar(c.id);
      // Meu Pluggy: a busca no banco é dele, uma vez por dia. O servidor
      // trouxe o que ele já tinha.
      if (r?.meuPluggy) {
        notificar(
          r.novas
            ? `${c.instituicao}: ${r.novas} ${r.novas === 1 ? "lançamento novo" : "lançamentos novos"}. O Meu Pluggy busca no banco uma vez por dia.`
            : `${c.instituicao} já está em dia com o Meu Pluggy, que busca no banco uma vez por dia.`,
        );
      }
      releiturasRef.current = 0;
      await carregar({ silencioso: true });
    } catch (err) {
      notificar(err.message, "error");
    } finally {
      setSincronizando((s) => {
        const n = new Set(s);
        n.delete(c.id);
        return n;
      });
    }
  };

  const sincronizarTudo = async () => {
    await Promise.all(minhas.map(sincronizarConexao));
  };

  // Cadeado da conta inteira: privada some do Juntos com tudo o que veio dela.
  const alternarPrivada = async (c) => {
    try {
      await marcarContaPrivada(c.id, !c.privada);
      await carregar({ silencioso: true });
      notificar(
        c.privada
          ? `${c.instituicao} volta a aparecer no espaço.`
          : `${c.instituicao} agora é só sua: some do Juntos, com os lançamentos dela.`,
      );
    } catch (err) {
      notificar(err.message, "error");
    }
  };

  const remover = async () => {
    const c = paraRemover;
    if (!c) return;
    setRemovendo(true);
    try {
      await desconectar(c.id);
      setParaRemover(null);
      await carregar();
      notificar("Conexão removida.");
    } catch (err) {
      notificar(err.message, "error");
    } finally {
      setRemovendo(false);
    }
  };

  const importar = async (e) => {
    e.preventDefault();
    setImportando(true);
    setResultado(null);
    try {
      setResultado(await importarTransacoes(desde));
      await carregar({ silencioso: true });
    } catch (err) {
      notificar(err.message, "error");
    } finally {
      setImportando(false);
    }
  };

  if (carregando) {
    return (
      <div className="fin-loading">
        <Loader2 size={17} className="fin-spin" />
        <span>Lendo suas contas...</span>
      </div>
    );
  }

  const disponivel = resposta?.disponivel;
  const credencial = resposta?.credencial;
  // Sem chave no servidor, a pessoa não tem o que cadastrar: só o aviso.
  const mostrarCredencial = credencial && credencial.situacao !== "semChave";
  const credencialPronta = credencial?.situacao === "ok";
  const cartaoCredencial = mostrarCredencial && (
    <CredencialPluggy
      credencial={credencial}
      notificar={notificar}
      onMudou={() => carregar({ silencioso: true })}
    />
  );

  return (
    <>
      <div className="fin-page-head">
        <div>
          <h1 className="fin-page-title">Contas</h1>
          <p className="fin-page-sub">Saldos e faturas pelo Open Finance</p>
        </div>

        <SeletorVisao />

        {minhas.length > 0 && (
          <div className="fin-form__actions">
            <button
              className="fin-btn fin-btn--ghost"
              onClick={() => navigate("/app/contas/conferir")}
              title="Conferir o que a importação tirou da soma"
            >
              <SearchCheck size={14} /> Conferir números
            </button>
            <button
              className="fin-btn fin-btn--ghost"
              onClick={sincronizarTudo}
              disabled={atualizando || sincronizando.size > 0}
              title="Pedir aos bancos os dados de agora"
            >
              <RefreshCw
                size={14}
                className={atualizando || sincronizando.size > 0 || algumSincronizando ? "fin-spin" : ""}
              />
              Sincronizar
            </button>
            <button
              className={`fin-btn fin-btn--${importAberto ? "ghost" : "primary"}`}
              onClick={() => setImportAberto((v) => !v)}
            >
              {importAberto ? (
                <>
                  <X size={14} /> Fechar
                </>
              ) : (
                <>
                  <Download size={14} /> Importar transações
                </>
              )}
            </button>
          </div>
        )}
      </div>

      {falha && (
        <div className="fin-banner" style={{ "--bc": "var(--fin-danger)" }}>
          <AlertTriangle size={16} />
          <span>{falha}</span>
        </div>
      )}

      {/* Credencial ausente não vira banner: o próprio cartão de cadastro,
          logo abaixo, explica o que falta. */}
      {/* Sem conexão nenhuma, o guia mostra o aviso no passo certo. */}
      {minhas.length > 0 && !disponivel && credencial?.situacao !== "ausente" && (
        <div className="fin-banner" style={{ "--bc": "var(--fin-warn)" }}>
          <CloudOff size={16} />
          <span>{resposta?.aviso}</span>
        </div>
      )}

      {/* ── Importação ── */}
      {importAberto && (
        <div className="fin-card" style={{ marginBottom: 12 }}>
          <div className="fin-cfg-card__title">
            <Download size={15} /> Importar para Entradas e Saídas
          </div>
          <form className="fin-form" onSubmit={importar}>
            <div className="fin-field" style={{ maxWidth: 260 }}>
              <label htmlFor="of-desde">A partir de</label>
              <input
                id="of-desde"
                type="date"
                value={desde}
                max={hojeISO()}
                onChange={(e) => setDesde(e.target.value)}
                required
              />
              <span className="fin-field__hint">
                Pode repetir o mesmo período: o que já foi importado não duplica.
              </span>
            </div>
            <p className="fin-of-nota">
              Ficam de fora o pagamento da fatura (as compras do cartão já entram uma a uma),
              transferências entre contas do seu CPF e lançamentos ainda pendentes.
            </p>
            <div className="fin-form__actions">
              <button className="fin-btn fin-btn--primary fin-btn--sm" disabled={importando || !desde}>
                {importando ? (
                  <>
                    <Loader2 size={13} className="fin-spin" /> Importando...
                  </>
                ) : (
                  <>
                    <Check size={13} /> Importar
                  </>
                )}
              </button>
            </div>
          </form>

          {resultado && (
            <ResultadoImportacao r={resultado} onConferir={() => navigate("/app/contas/conferir")} />
          )}
        </div>
      )}

      {/* ── KPIs ── */}
      {conexoes.length > 0 && (
        <div className="fin-kpis fin-kpis--3">
          <Kpi
            cor="var(--fin-in)"
            icone={Landmark}
            label="Saldo em contas"
            valor={brl(resumo.saldo)}
            sub={`${resumo.contas} ${resumo.contas === 1 ? "conta" : "contas"}`}
          />
          <Kpi
            cor="var(--fin-out)"
            icone={CreditCard}
            label="Faturas atuais"
            valor={brl(resumo.emAberto)}
            sub={`${resumo.cartoes} ${resumo.cartoes === 1 ? "cartão" : "cartões"}`}
          />
          <Kpi
            cor="var(--fin-warn)"
            icone={CreditCard}
            label="Parcelas a vencer"
            valor={brl(resumo.parcelado)}
            sub={
              resumo.mesesParcelados
                ? `projeção em ${resumo.mesesParcelados} ${resumo.mesesParcelados === 1 ? "mês" : "meses"}`
                : "nenhuma compra parcelada"
            }
          />
        </div>
      )}

      {/* ── Conexões ── */}
      {minhas.length === 0 && (visao === "eu" || conexoes.length === 0) ? (
        <PrimeirosPassos
          credencial={credencial}
          disponivel={disponivel}
          aviso={resposta?.aviso}
          abrindoWidget={abrindoWidget}
          onConectar={() => abrirWidget()}
          notificar={notificar}
          onMudou={() => carregar({ silencioso: true })}
        />
      ) : (
        <div className="fin-of-lista">
          {/* Sem credencial, cadastrar é o primeiro passo; com ela, o cartão
              desce para o fim e vira só "trocar / remover". */}
          {!credencialPronta && cartaoCredencial}

          {conexoes.map((c) => (
            <Conexao
              key={c.id}
              c={c}
              ocupado={sincronizando.has(c.id)}
              onSincronizar={() => sincronizarConexao(c)}
              onReconectar={() => abrirWidget(c.id)}
              onRemover={() => setParaRemover(c)}
              comEspaco={temEspaco}
              onAlternarPrivada={() => alternarPrivada(c)}
            />
          ))}

          <div className="fin-card">
            <div className="fin-cfg-card__title">
              <Plug size={15} /> {conexoes.length ? "Adicionar outra conexão" : "Conectar o Open Finance"}
            </div>
            <p className="fin-of-nota" style={{ marginTop: 0, marginBottom: 12 }}>
              Abre a janela da Pluggy. Escolha Meu Pluggy para trazer de uma vez todos os bancos
              que você já ligou lá, ou um banco direto. O consentimento é dado no app do banco.
            </p>
            <button
              className="fin-btn fin-btn--primary fin-btn--sm"
              onClick={() => abrirWidget()}
              disabled={!disponivel || abrindoWidget}
            >
              {abrindoWidget ? (
                <>
                  <Loader2 size={13} className="fin-spin" /> Abrindo...
                </>
              ) : (
                <>
                  <Link2 size={13} /> Conectar banco
                </>
              )}
            </button>

            <form className="fin-form fin-of-manual" onSubmit={adicionar}>
              <div className="fin-field">
                <label htmlFor="of-item">Ou cole o id de uma conexão que já existe</label>
                <input
                  id="of-item"
                  value={novoId}
                  onChange={(e) => setNovoId(e.target.value.trim())}
                  placeholder="00000000-0000-0000-0000-000000000000"
                  spellCheck={false}
                  autoComplete="off"
                  disabled={!disponivel}
                  required
                />
                <span className="fin-field__hint">O id do item, no formato 8-4-4-4-12.</span>
              </div>
              <div className="fin-form__actions">
                <button
                  className="fin-btn fin-btn--ghost fin-btn--sm"
                  disabled={!disponivel || conectando || !novoId}
                >
                  {conectando ? (
                    <>
                      <Loader2 size={13} className="fin-spin" /> Conferindo...
                    </>
                  ) : (
                    <>
                      <Check size={13} /> Adicionar
                    </>
                  )}
                </button>
              </div>
            </form>
          </div>

          {credencialPronta && cartaoCredencial}
        </div>
      )}

      {/* Sem includeSandbox: os bancos de teste da Pluggy só confundiriam
          a lista de um app que usa dado real. */}
      {widget && (
        <PluggyConnect
          connectToken={widget.token}
          updateItem={
            widget.conexaoId
              ? conexoes.find((c) => c.id === widget.conexaoId)?.itemId
              : undefined
          }
          includeSandbox={false}
          onSuccess={widgetConectou}
          onError={(e) => notificar(e?.message || "A conexão não foi concluída.", "error")}
          onClose={() => setWidget(null)}
          onLoadError={() => {
            setWidget(null);
            notificar("Não consegui carregar a janela da Pluggy. Confira a internet.", "error");
          }}
        />
      )}

      {paraRemover && (
        <ConfirmarExclusao
          titulo={`Desconectar ${paraRemover.instituicao}?`}
          mensagem="Saldos e faturas dessa conexão param de aparecer aqui. As transações já importadas continuam em Entradas e Saídas, e o consentimento no banco continua valendo até você revogar no Meu Pluggy."
          rotuloConfirmar="Desconectar"
          ocupado={removendo}
          onConfirmar={remover}
          onCancelar={() => setParaRemover(null)}
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

function ResultadoImportacao({ r, onConferir }) {
  const ig = r.ignoradas || {};
  const fora = [
    ig.pagamentoFatura && `${ig.pagamentoFatura} pagamentos de fatura`,
    ig.transferencias && `${ig.transferencias} transferências entre suas contas`,
    ig.pendentes && `${ig.pendentes} pendentes`,
    ig.semValor && `${ig.semValor} sem valor`,
  ].filter(Boolean);

  return (
    <div className="fin-banner" style={{ "--bc": "var(--fin-accent)", marginTop: 13, marginBottom: 0 }}>
      <Check size={16} />
      <span style={{ flex: 1 }}>
        <strong>
          {r.novas} {r.novas === 1 ? "transação nova" : "transações novas"}
        </strong>
        {r.jaExistiam > 0 && `, ${r.jaExistiam} já estavam no app`}.
        {fora.length > 0 && ` Ficaram de fora: ${fora.join(", ")}.`}
      </span>
      {(ig.pagamentoFatura > 0 || ig.transferencias > 0) && (
        <button className="fin-btn fin-btn--ghost fin-btn--sm" onClick={onConferir}>
          <SearchCheck size={13} /> Conferir
        </button>
      )}
    </div>
  );
}

// ── Primeiros passos ──
// Quem chega sem nenhuma conexão vê um guia em vez dos cartões soltos. O
// app só consegue ver sozinho os passos 3 (credencial salva) e 4 (banco
// conectado); os dois primeiros acontecem no site da Pluggy, e a própria
// pessoa marca "já fiz". Essa marca é conveniência deste aparelho, por
// isso fica no localStorage e falhar ao ler não quebra nada.
const CHAVE_PASSOS = "fin_passos_pluggy";

const lerPassosFeitos = () => {
  try {
    return JSON.parse(localStorage.getItem(CHAVE_PASSOS)) || {};
  } catch {
    return {};
  }
};

function PrimeirosPassos({ credencial, disponivel, aviso, abrindoWidget, onConectar, notificar, onMudou }) {
  const [marcados, setMarcados] = useState(lerPassosFeitos);
  const [abertos, setAbertos] = useState(() => new Set());

  const semChave = credencial?.situacao === "semChave";
  const credencialPronta = credencial?.situacao === "ok";

  const feito = {
    1: credencialPronta || !!marcados[1],
    2: credencialPronta || !!marcados[2],
    3: credencialPronta,
    4: false,
  };
  const atual = [1, 2, 3, 4].find((n) => !feito[n]);

  const marcar = (n) => {
    const novos = { ...marcados, [n]: true };
    setMarcados(novos);
    try {
      localStorage.setItem(CHAVE_PASSOS, JSON.stringify(novos));
    } catch {
      // Sem armazenamento: vale só nesta visita.
    }
  };

  const alternar = (n) =>
    setAbertos((s) => {
      const novo = new Set(s);
      novo.has(n) ? novo.delete(n) : novo.add(n);
      return novo;
    });

  const passos = [
    {
      n: 1,
      titulo: "Crie sua conta no Meu Pluggy e ligue seus bancos",
      corpo: (
        <>
          <p>
            Entre em{" "}
            <a href="https://meu.pluggy.ai/" target="_blank" rel="noreferrer">
              meu.pluggy.ai
            </a>
            , crie a conta com o seu e-mail e conecte cada banco seu. A autorização é dada no app do
            próprio banco.
          </p>
          <p className="fin-passos__nota">
            É gratuito, pessoal e intransferível: só contas no seu nome, até 5. Cada pessoa da casa
            faz o próprio.
          </p>
        </>
      ),
      acao: !feito[1] && (
        <button className="fin-btn fin-btn--primary fin-btn--sm" onClick={() => marcar(1)}>
          <Check size={13} /> Já fiz
        </button>
      ),
    },
    {
      n: 2,
      titulo: "Crie sua aplicação na Pluggy",
      corpo: (
        <>
          <ol className="fin-passos__sub">
            <li>
              Crie uma conta em{" "}
              <a href="https://dashboard.pluggy.ai/" target="_blank" rel="noreferrer">
                dashboard.pluggy.ai
              </a>
              . Começa um teste de 15 dias; a leitura dos seus bancos continua depois dele.
            </li>
            <li>
              Na aba <strong>Customization</strong>, inclua o conector <strong>MeuPluggy</strong> na
              lista de conectores.
            </li>
            <li>
              Em <strong>Applications</strong>, crie uma aplicação de desenvolvimento.
            </li>
          </ol>
          <div className="fin-banner fin-passos__alerta" style={{ "--bc": "var(--fin-warn)" }}>
            <AlertTriangle size={15} />
            <span>
              O <strong>Client Secret</strong> aparece uma vez só, quando a aplicação é criada.
              Copie antes de fechar a janela e guarde num lugar seguro.
            </span>
          </div>
          <p className="fin-passos__nota">
            Detalhes no{" "}
            <a href="https://github.com/pluggyai/meu-pluggy" target="_blank" rel="noreferrer">
              guia da Pluggy
            </a>
            .
          </p>
        </>
      ),
      acao: !feito[2] && (
        <button className="fin-btn fin-btn--primary fin-btn--sm" onClick={() => marcar(2)}>
          <Check size={13} /> Já fiz
        </button>
      ),
    },
    {
      n: 3,
      titulo: "Cole aqui o Client ID e o Client Secret",
      corpo: semChave ? (
        <div className="fin-banner fin-passos__alerta" style={{ "--bc": "var(--fin-warn)" }}>
          <CloudOff size={15} />
          <span>{aviso || "O servidor ainda não está pronto para guardar credenciais."}</span>
        </div>
      ) : credencialPronta ? (
        <p>Credencial conferida na Pluggy e guardada cifrada. O segredo não aparece de novo.</p>
      ) : (
        <>
          <p>
            Os dois ficam na página da aplicação que você criou. O app confere na Pluggy antes de
            salvar e guarda o segredo cifrado.
          </p>
          {credencial?.situacao === "ilegivel" && (
            <p className="fin-passos__nota">
              A credencial guardada não abre mais (a chave do servidor mudou). Cadastre de novo.
            </p>
          )}
          <FormCredencial notificar={notificar} onSalvo={onMudou} />
        </>
      ),
    },
    {
      n: 4,
      titulo: "Conecte seus bancos",
      corpo: (
        <>
          <p>
            Abre a janela da Pluggy. Procure <strong>MeuPluggy</strong> e autorize: os bancos que você
            ligou no passo 1 chegam juntos. Se algum não vier, conecte de novo e escolha o outro.
          </p>
          {credencialPronta && !disponivel && aviso && (
            <div className="fin-banner fin-passos__alerta" style={{ "--bc": "var(--fin-warn)" }}>
              <CloudOff size={15} />
              <span>{aviso}</span>
            </div>
          )}
          <p className="fin-passos__nota">
            Depois disso o app pede o histórico para trazer suas transações para Entradas e Saídas.
          </p>
        </>
      ),
      acao: (
        <button
          className="fin-btn fin-btn--primary fin-btn--sm"
          onClick={onConectar}
          disabled={!credencialPronta || !disponivel || abrindoWidget}
        >
          {abrindoWidget ? (
            <>
              <Loader2 size={13} className="fin-spin" /> Abrindo...
            </>
          ) : (
            <>
              <Link2 size={13} /> Conectar banco
            </>
          )}
        </button>
      ),
    },
  ];

  return (
    <div className="fin-card fin-passos">
      <div className="fin-cfg-card__title">
        <Plug size={15} /> Comece por aqui
      </div>
      <p className="fin-passos__intro">
        Uma vez só, uns 15 minutos. Ao fim, saldos, faturas e transações dos seus bancos aparecem
        aqui sozinhos.
      </p>

      <ol className="fin-passos__lista">
        {passos.map((p) => {
          const aberto = p.n === atual || abertos.has(p.n);
          const estado = feito[p.n] ? "feito" : p.n === atual ? "atual" : "depois";
          return (
            <li key={p.n} className={`fin-passo fin-passo--${estado}`}>
              <button
                className="fin-passo__cab"
                onClick={() => p.n !== atual && alternar(p.n)}
                aria-expanded={aberto}
                disabled={p.n === atual}
              >
                <span className="fin-passo__marca" aria-hidden="true">
                  {feito[p.n] ? <Check size={13} /> : p.n}
                </span>
                <span className="fin-passo__titulo">{p.titulo}</span>
                {p.n !== atual && <ChevronDown size={14} className="fin-passo__seta" />}
              </button>
              {aberto && (
                <div className="fin-passo__corpo">
                  {p.corpo}
                  {p.acao && <div className="fin-form__actions">{p.acao}</div>}
                </div>
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}

// Formulário da credencial, usado no guia e no cartão de trocar. O segredo
// vai para a API, que testa na Pluggy, cifra e nunca devolve.
function FormCredencial({ notificar, onSalvo, onCancelar }) {
  const [clientId, setClientId] = useState("");
  const [segredo, setSegredo] = useState("");
  const [salvando, setSalvando] = useState(false);

  const salvar = async (e) => {
    e.preventDefault();
    setSalvando(true);
    try {
      await salvarCredencial(clientId.trim(), segredo.trim());
      setSegredo("");
      setClientId("");
      notificar("Credencial da Pluggy conferida e salva.");
      await onSalvo();
    } catch (err) {
      notificar(err.message, "error");
    } finally {
      setSalvando(false);
    }
  };

  return (
    <form className="fin-form" onSubmit={salvar}>
      <div className="fin-form__row">
        <div className="fin-field">
          <label htmlFor="pl-id">Client ID</label>
          <input
            id="pl-id"
            value={clientId}
            onChange={(e) => setClientId(e.target.value.trim())}
            placeholder="00000000-0000-0000-0000-000000000000"
            spellCheck={false}
            autoComplete="off"
            required
          />
        </div>
        <div className="fin-field">
          <label htmlFor="pl-segredo">Client Secret</label>
          <input
            id="pl-segredo"
            type="password"
            value={segredo}
            onChange={(e) => setSegredo(e.target.value)}
            spellCheck={false}
            autoComplete="off"
            required
          />
        </div>
      </div>
      <div className="fin-form__actions">
        <button className="fin-btn fin-btn--primary fin-btn--sm" disabled={salvando || !clientId || !segredo}>
          {salvando ? (
            <>
              <Loader2 size={13} className="fin-spin" /> Conferindo na Pluggy...
            </>
          ) : (
            <>
              <Check size={13} /> Salvar
            </>
          )}
        </button>
        {onCancelar && (
          <button type="button" className="fin-btn fin-btn--ghost fin-btn--sm" onClick={onCancelar}>
            Cancelar
          </button>
        )}
      </div>
    </form>
  );
}

// Cada pessoa lê os próprios bancos com a própria aplicação na Pluggy: é a
// regra do Meu Pluggy gratuito, que é intransferível. Este cartão aparece
// quando já existe conexão: é onde a credencial é trocada ou removida.
function CredencialPluggy({ credencial, notificar, onMudou }) {
  const pronta = credencial.situacao === "ok";
  const [editando, setEditando] = useState(!pronta);
  const [paraRemover, setParaRemover] = useState(false);
  const [removendo, setRemovendo] = useState(false);

  const remover = async () => {
    setRemovendo(true);
    try {
      await removerCredencial();
      setParaRemover(false);
      setEditando(true);
      notificar("Credencial removida.");
      await onMudou();
    } catch (err) {
      notificar(err.message, "error");
    } finally {
      setRemovendo(false);
    }
  };

  const id = credencial.clientId || "";

  return (
    <div className="fin-card">
      <div className="fin-cfg-card__title">
        <KeyRound size={15} /> Sua aplicação na Pluggy
      </div>

      {pronta && !editando ? (
        <>
          <p className="fin-of-nota" style={{ marginTop: 0, marginBottom: 12 }}>
            Client ID {id.slice(0, 8)}…{id.slice(-4)}. O Client Secret fica cifrado no servidor e
            não aparece de novo.
          </p>
          <div className="fin-form__actions">
            <button
              className="fin-btn fin-btn--ghost fin-btn--sm"
              onClick={() => setEditando(true)}
            >
              <RefreshCw size={13} /> Trocar
            </button>
            <button
              className="fin-btn fin-btn--danger fin-btn--sm"
              onClick={() => setParaRemover(true)}
            >
              <Trash2 size={13} /> Remover
            </button>
          </div>
        </>
      ) : (
        <>
          <p className="fin-of-nota" style={{ marginTop: 0 }}>
            O plano gratuito da Pluggy é pessoal: cada pessoa lê os próprios bancos com a própria
            aplicação. Faça uma vez:
          </p>
          <ol className="fin-of-passos">
            <li>
              Crie sua conta no{" "}
              <a href="https://meu.pluggy.ai/" target="_blank" rel="noreferrer">
                Meu Pluggy
              </a>{" "}
              e conecte seus bancos (até 5 contas).
            </li>
            <li>
              Crie uma conta na{" "}
              <a href="https://dashboard.pluggy.ai/" target="_blank" rel="noreferrer">
                dashboard da Pluggy
              </a>
              , crie uma aplicação de desenvolvimento e inclua nela o conector MeuPluggy (
              <a href="https://github.com/pluggyai/meu-pluggy" target="_blank" rel="noreferrer">
                guia da Pluggy
              </a>
              ).
            </li>
            <li>Copie o Client ID e o Client Secret da aplicação e cole aqui.</li>
            <li>Depois, use Conectar banco e escolha Meu Pluggy.</li>
          </ol>
          {credencial.situacao === "ilegivel" && (
            <p className="fin-of-nota" style={{ marginTop: 0, marginBottom: 12 }}>
              A credencial guardada não abre mais (a chave do servidor mudou). Cadastre de novo.
            </p>
          )}
          <FormCredencial
            notificar={notificar}
            onSalvo={async () => {
              setEditando(false);
              await onMudou();
            }}
            onCancelar={pronta ? () => setEditando(false) : undefined}
          />
        </>
      )}

      {paraRemover && (
        <ConfirmarExclusao
          titulo="Remover a credencial da Pluggy?"
          mensagem="As conexões continuam aqui, mas o app para de ler seus bancos até você cadastrar outra credencial. O consentimento no Meu Pluggy não muda."
          rotuloConfirmar="Remover"
          ocupado={removendo}
          onConfirmar={remover}
          onCancelar={() => setParaRemover(false)}
        />
      )}
    </div>
  );
}

function Conexao({ c, ocupado, onSincronizar, onReconectar, onRemover, comEspaco, onAlternarPrivada }) {
  const d = c.dados;
  // Conta de outra pessoa do espaço: só leitura (sem sincronizar, remover
  // nem reconectar, que usam a credencial dela).
  const minha = c.minha !== false;
  const status = d?.status;
  const girando = ocupado || status === "UPDATING";

  return (
    <div className="fin-card fin-card--flush">
      <div className="fin-card__head fin-of-cab">
        <div style={{ minWidth: 0 }}>
          <div className="fin-card__title">
            {c.instituicao}
            {!minha && (
              <span className="fin-tag fin-tag--dono" style={{ marginLeft: 8 }}>
                <Users size={10} /> {c.donoNome}
              </span>
            )}
            {minha && comEspaco && c.privada && (
              <span className="fin-tag" style={{ marginLeft: 8 }} title="Fora do Juntos">
                <Lock size={10} /> privada
              </span>
            )}
          </div>
          <div className="fin-card__sub">
            {d ? (
              <>
                <span className="fin-of-status" style={{ "--sc": COR_STATUS[status] || "var(--fin-muted)" }}>
                  {d.statusTexto}
                </span>{" "}
                · dados {haQuanto(d.atualizadoEm)}
              </>
            ) : (
              "sem leitura agora"
            )}
          </div>
        </div>
        {minha && (
        <div className="fin-of-cab__acoes">
          {comEspaco && (
            <button
              className="fin-icon-btn"
              onClick={onAlternarPrivada}
              aria-label={c.privada ? `Compartilhar ${c.instituicao} com o espaço` : `Deixar ${c.instituicao} só para mim`}
              title={c.privada ? "Privada: toque para compartilhar com o espaço" : "Compartilhada: toque para deixar só sua"}
            >
              {c.privada ? <Lock size={14} /> : <Unlock size={14} />}
            </button>
          )}
          <button
            className="fin-icon-btn"
            onClick={onSincronizar}
            disabled={girando}
            aria-label={`Sincronizar ${c.instituicao}`}
            title="Sincronizar agora"
          >
            <RefreshCw size={14} className={girando ? "fin-spin" : ""} />
          </button>
          <button
            className="fin-lanc-item__excluir"
            onClick={onRemover}
            aria-label={`Desconectar ${c.instituicao}`}
            title="Desconectar"
          >
            <Trash2 size={14} />
          </button>
        </div>
        )}
      </div>

      {c.aviso && (
        <div className="fin-banner fin-of-aviso" style={{ "--bc": "var(--fin-warn)" }}>
          <CloudOff size={16} />
          <span>{c.aviso}</span>
        </div>
      )}

      {minha && status === "LOGIN_ERROR" && (
        <div className="fin-banner fin-of-aviso" style={{ "--bc": "var(--fin-danger)" }}>
          <AlertTriangle size={16} />
          <span style={{ flex: 1 }}>O consentimento expirou ou foi revogado.</span>
          <button className="fin-btn fin-btn--ghost fin-btn--sm" onClick={onReconectar}>
            <Link2 size={13} /> Reconectar
          </button>
        </div>
      )}

      {d && d.contas.length === 0 && d.cartoes.length === 0 && !d.investimentos?.length && (
        <div className="fin-empty" style={{ paddingTop: 8 }}>
          <Wallet size={22} />
          <span>Nenhuma conta nessa conexão ainda. Se acabou de conectar, sincronize.</span>
        </div>
      )}

      {d && (
        <div className="fin-list">
          {d.contas.map((conta) => (
            <div key={conta.id} className="fin-list__item">
              <div className="fin-list__ico" style={{ "--ic": "var(--fin-in)" }}>
                <Landmark size={14} />
              </div>
              <div className="fin-list__body">
                <div className="fin-list__name">{conta.nome}</div>
                <div className="fin-list__meta">
                  {conta.tipo}
                  {conta.numero ? ` · ${conta.numero}` : ""}
                </div>
              </div>
              <div
                className="fin-list__val"
                style={{ "--ic": conta.saldo < 0 ? "var(--fin-out)" : "var(--fin-text)" }}
              >
                {conta.saldo == null ? "n/d" : brl(conta.saldo)}
                <small>saldo</small>
              </div>
            </div>
          ))}

          {(d.investimentos || []).map((inv) => (
            <div key={inv.id} className="fin-list__item">
              <div className="fin-list__ico" style={{ "--ic": "var(--fin-accent)" }}>
                <PiggyBank size={14} />
              </div>
              <div className="fin-list__body">
                <div className="fin-list__name">{inv.nome}</div>
                <div className="fin-list__meta">
                  {inv.tipo}
                  {inv.vencimento ? ` · vence ${dataCurta(inv.vencimento)}/${inv.vencimento.slice(2, 4)}` : ""}
                </div>
              </div>
              <div className="fin-list__val">
                {inv.saldo == null ? "n/d" : brl(inv.saldo)}
                <small>líquido</small>
              </div>
            </div>
          ))}

          {d.cartoes.map((cartao) => (
            <Cartao key={cartao.id} cartao={cartao} />
          ))}
        </div>
      )}
    </div>
  );
}

function Cartao({ cartao }) {
  const [aba, setAba] = useState(cartao.faturasFuturas.length ? "futuras" : "passadas");
  const [aberta, setAberta] = useState(null);
  const atual = cartao.faturaAtual;

  const usado =
    cartao.limite && cartao.disponivel != null ? Math.max(0, cartao.limite - cartao.disponivel) : null;
  const pctUsado = usado != null && cartao.limite ? Math.min(100, (usado / cartao.limite) * 100) : null;

  const hoje = hojeISO();

  return (
    <div className="fin-of-cartao">
      <div className="fin-list__item">
        <div className="fin-list__ico" style={{ "--ic": "var(--fin-out)" }}>
          <CreditCard size={14} />
        </div>
        <div className="fin-list__body">
          <div className="fin-list__name">{cartao.nome}</div>
          <div className="fin-list__meta">
            {[cartao.bandeira, cartao.numero && `final ${String(cartao.numero).slice(-4)}`]
              .filter(Boolean)
              .join(" · ") || "Cartão de crédito"}
          </div>
        </div>
        <div className="fin-list__val" style={{ "--ic": "var(--fin-out)" }}>
          {atual.valor == null ? "n/d" : brl(atual.valor)}
          <small>fatura atual</small>
        </div>
      </div>

      <div className="fin-of-cartao__corpo">
        <dl className="fin-of-fatos">
          <div>
            <dt>Fecha</dt>
            <dd>{atual.fechamento ? dataCurta(atual.fechamento) : "n/d"}</dd>
          </div>
          <div>
            <dt>Vence</dt>
            <dd>{atual.vencimento ? dataCurta(atual.vencimento) : "n/d"}</dd>
          </div>
          <div>
            <dt>Mínimo</dt>
            <dd>{atual.pagamentoMinimo == null ? "n/d" : brl(atual.pagamentoMinimo)}</dd>
          </div>
          <div>
            <dt>Limite livre</dt>
            <dd>{cartao.disponivel == null ? "n/d" : brl(cartao.disponivel)}</dd>
          </div>
        </dl>

        {pctUsado != null && (
          <div
            className="fin-of-limite"
            role="meter"
            aria-valuenow={Math.round(pctUsado)}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label="Limite usado"
            title={`${brl(usado)} usados de ${brl(cartao.limite)}`}
          >
            <span style={{ width: `${pctUsado}%` }} />
          </div>
        )}

        <div className="fin-seg" style={{ marginTop: 12 }}>
          <button className={aba === "futuras" ? "active" : ""} onClick={() => setAba("futuras")}>
            Próximas ({cartao.faturasFuturas.length})
          </button>
          <button className={aba === "passadas" ? "active" : ""} onClick={() => setAba("passadas")}>
            Anteriores ({cartao.faturasPassadas.length})
          </button>
        </div>

        {aba === "futuras" ? (
          cartao.faturasFuturas.length === 0 ? (
            <p className="fin-of-nota">Nenhuma parcela de compra parcelada para os próximos meses.</p>
          ) : (
            <>
              <div className="fin-of-faturas">
                {cartao.faturasFuturas.map((f) => (
                  <div key={f.mes}>
                    <button
                      className="fin-of-fatura"
                      onClick={() => setAberta(aberta === f.mes ? null : f.mes)}
                      aria-expanded={aberta === f.mes}
                    >
                      <span className="fin-of-fatura__mes">{mesAno(f.mes)}</span>
                      <span className="fin-of-fatura__meta">
                        vence {dataCurta(f.vencimento)} · {f.parcelas.length}{" "}
                        {f.parcelas.length === 1 ? "parcela" : "parcelas"}
                      </span>
                      <span className="fin-of-fatura__val">{brl(f.valor)}</span>
                      <ChevronDown size={13} className="fin-of-fatura__seta" />
                    </button>
                    {aberta === f.mes && (
                      <ul className="fin-of-parcelas">
                        {f.parcelas.map((p, i) => (
                          <li key={i}>
                            <span>{p.descricao}</span>
                            <small>{p.parcela}</small>
                            <span className="fin-num">{brl(p.valor)}</span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                ))}
              </div>
              <p className="fin-of-nota">
                Projeção só com as parcelas já compradas. Compras novas, juros e anuidade não entram.
              </p>
            </>
          )
        ) : cartao.faturasPassadas.length === 0 ? (
          <p className="fin-of-nota">O banco ainda não entregou faturas fechadas desse cartão.</p>
        ) : (
          <div className="fin-of-faturas">
            {cartao.faturasPassadas.map((f) => (
              <div key={f.id} className="fin-of-fatura fin-of-fatura--estatica">
                <span className="fin-of-fatura__mes">{f.vencimento ? mesAno(f.vencimento.slice(0, 7)) : "n/d"}</span>
                <span className="fin-of-fatura__meta">
                  {f.vencimento
                    ? `${f.vencimento > hoje ? "vence" : "venceu"} ${dataCurta(f.vencimento)}`
                    : "sem vencimento"}
                </span>
                <span className="fin-of-fatura__val">{f.valor == null ? "n/d" : brl(f.valor)}</span>
              </div>
            ))}
          </div>
        )}
      </div>
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
