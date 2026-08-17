// Configurações de usuário único: não há convite, papel nem lista de admins
// como no painel do Synchro. Só o meu perfil, minha segurança e os tetos de
// gasto que alimentam os alertas do dashboard.
//
// O tema não mora aqui: troca pelo botão da topbar.

import {
  Camera,
  Check,
  Eye,
  EyeOff,
  KeyRound,
  Loader2,
  ShieldCheck,
  Target,
  Trash2,
  TriangleAlert,
  User,
} from "lucide-react";
import QRCode from "qrcode";
import { useEffect, useRef, useState } from "react";
import { usePerfil } from "../context/PerfilProvider";
import { desativar2FA, iniciarSetup2FA, verificar2FA } from "../services/authService";
import {
  brl,
  carregarOrcamentos,
  categorias as extrairCategorias,
  chaveMes,
  gastosPorCategoria,
  listarTransacoes,
  salvarOrcamentos,
} from "../services/financasService";
import { criarMapaDeCores } from "../services/cores";
import { ImagemInvalida, prepararFotoPerfil } from "../services/imagem";
import {
  iniciais,
  removerFoto,
  salvarFoto,
  salvarNome,
  trocarSenha,
} from "../services/perfilService";

export default function Configuracoes() {
  // O perfil vem do contexto: a topbar consome o mesmo objeto, então trocar
  // a foto aqui repinta o avatar de lá sem recarregar a página.
  const { perfil, atualizar } = usePerfil();

  const [carregando, setCarregando] = useState(true);
  const [toast, setToast] = useState(null);

  // Perfil
  const [nome, setNome] = useState("");
  const [salvandoNome, setSalvandoNome] = useState(false);

  // Foto
  const arquivoRef = useRef(null);
  const [salvandoFoto, setSalvandoFoto] = useState(false);

  // Senha
  const [senhaAtual, setSenhaAtual] = useState("");
  const [senhaNova, setSenhaNova] = useState("");
  const [senhaConfirma, setSenhaConfirma] = useState("");
  const [mostrarSenha, setMostrarSenha] = useState(false);
  const [salvandoSenha, setSalvandoSenha] = useState(false);

  // 2FA
  const [qrDataUrl, setQrDataUrl] = useState("");
  const [modo2fa, setModo2fa] = useState("idle"); // idle | setup | desativar
  const [codigo, setCodigo] = useState("");
  const [salvando2fa, setSalvando2fa] = useState(false);

  // Orçamentos
  const [orcamentos, setOrcamentos] = useState({});
  const [gastoDoMes, setGastoDoMes] = useState({});
  const [listaCategorias, setListaCategorias] = useState([]);
  const [salvandoOrc, setSalvandoOrc] = useState(false);

  const avisar = (msg, tipo = "success") => {
    setToast({ msg, tipo });
    setTimeout(() => setToast(null), 3500);
  };

  // O campo de nome é editável, então parte do valor do contexto mas passa a
  // viver localmente: sincronizar a cada tecla apagaria o que está sendo
  // digitado assim que outra tela atualizasse o perfil.
  useEffect(() => {
    if (perfil) setNome(perfil.nome || "");
  }, [perfil?.nome]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    (async () => {
      try {
        const [transacoes, orc] = await Promise.all([
          listarTransacoes(),
          carregarOrcamentos(),
        ]);
        setListaCategorias(extrairCategorias(transacoes));
        setOrcamentos(orc || {});
        setGastoDoMes(
          Object.fromEntries(
            gastosPorCategoria(transacoes, chaveMes(new Date())).map((c) => [c.label, c.valor]),
          ),
        );
      } catch (e) {
        console.error(e);
        avisar("Não consegui carregar suas configurações.", "error");
      } finally {
        setCarregando(false);
      }
    })();
  }, []);

  // ── Perfil ────────────────────────────────────────────────────────────────
  const handleNome = async (e) => {
    e.preventDefault();
    setSalvandoNome(true);
    try {
      await salvarNome(nome);
      atualizar({ nome: nome.trim() });
      avisar("Nome atualizado.");
    } catch (err) {
      avisar(err.message, "error");
    } finally {
      setSalvandoNome(false);
    }
  };

  // ── Foto ──────────────────────────────────────────────────────────────────
  const handleFoto = async (e) => {
    const arquivo = e.target.files?.[0];
    // Limpa o input antes de qualquer coisa: sem isso, escolher o mesmo
    // arquivo de novo depois de um erro não dispara o onChange.
    e.target.value = "";
    if (!arquivo) return;

    setSalvandoFoto(true);
    try {
      const foto = await prepararFotoPerfil(arquivo);
      await salvarFoto(foto);
      atualizar({ foto });
      avisar("Foto atualizada.");
    } catch (err) {
      avisar(
        err instanceof ImagemInvalida ? err.message : err.message || "Erro ao enviar a foto.",
        "error",
      );
    } finally {
      setSalvandoFoto(false);
    }
  };

  const handleRemoverFoto = async () => {
    setSalvandoFoto(true);
    try {
      await removerFoto();
      atualizar({ foto: null });
      avisar("Foto removida.");
    } catch (err) {
      avisar(err.message, "error");
    } finally {
      setSalvandoFoto(false);
    }
  };

  // ── Senha ─────────────────────────────────────────────────────────────────
  const handleSenha = async (e) => {
    e.preventDefault();
    if (senhaNova !== senhaConfirma) {
      avisar("As senhas novas não coincidem.", "error");
      return;
    }
    if (senhaNova.length < 8) {
      avisar("A senha nova precisa de pelo menos 8 caracteres.", "error");
      return;
    }
    setSalvandoSenha(true);
    try {
      // O servidor confere a senha atual antes de trocar e, ao trocar,
      // derruba as outras sessões abertas.
      await trocarSenha(senhaAtual, senhaNova);
      setSenhaAtual("");
      setSenhaNova("");
      setSenhaConfirma("");
      avisar("Senha alterada. As outras sessões foram encerradas.");
    } catch (err) {
      avisar(err.message, "error");
    } finally {
      setSalvandoSenha(false);
    }
  };

  // ── 2FA ───────────────────────────────────────────────────────────────────
  // Tudo passa pela API local: o segredo TOTP não é gerado nem validado
  // aqui, e quem grava `totp_confirmado` é o servidor.
  const abrirSetup = async () => {
    setCodigo("");
    try {
      const uri = await iniciarSetup2FA();
      setQrDataUrl(await QRCode.toDataURL(uri, { margin: 0, width: 320 }));
      setModo2fa("setup");
    } catch (err) {
      avisar(err.message, "error");
    }
  };

  const confirmarSetup = async (e) => {
    e.preventDefault();
    setSalvando2fa(true);
    try {
      await verificar2FA(codigo);
      atualizar({ twoFactorEnrolled: true });
      setModo2fa("idle");
      setQrDataUrl("");
      setCodigo("");
      avisar("Verificação em duas etapas ativada.");
    } catch (err) {
      avisar(err.message, "error");
    } finally {
      setSalvando2fa(false);
    }
  };

  const confirmarDesativacao = async (e) => {
    e.preventDefault();
    setSalvando2fa(true);
    try {
      // Exigir um código válido para desativar: sem isso, quem pegasse a
      // sessão aberta desligaria a segunda etapa em dois cliques.
      await desativar2FA(codigo);
      atualizar({ twoFactorEnrolled: false });
      setModo2fa("idle");
      setCodigo("");
      avisar("Verificação em duas etapas desativada.");
    } catch (err) {
      avisar(err.message, "error");
    } finally {
      setSalvando2fa(false);
    }
  };

  // ── Orçamentos ────────────────────────────────────────────────────────────
  const handleOrcamentos = async (e) => {
    e.preventDefault();
    setSalvandoOrc(true);
    try {
      setOrcamentos(await salvarOrcamentos(orcamentos));
      avisar("Orçamentos salvos.");
    } catch (err) {
      avisar(err.message, "error");
    } finally {
      setSalvandoOrc(false);
    }
  };

  if (carregando) {
    return (
      <div className="fin-loading">
        <Loader2 size={17} className="fin-spin" />
        <span>Carregando configurações...</span>
      </div>
    );
  }

  const dosDoisFa = perfil?.twoFactorEnrolled;
  const corDaCategoria = criarMapaDeCores(listaCategorias);

  return (
    <>
      <div className="fin-page-head">
        <div>
          <h1 className="fin-page-title">Configurações</h1>
          <p className="fin-page-sub">Perfil, segurança e orçamentos</p>
        </div>
      </div>

      {/* Duas colunas explícitas em vez de deixar o grid preencher linha a
          linha. Perfil é bem mais alto que Senha, e no fluxo automático a
          coluna da direita abria um vão até o card seguinte. Com Senha e
          2FA empilhados (os dois são segurança), as colunas se equilibram. */}
      <div className="fin-cfg-grid">
        {/* ── Coluna 1: identidade ── */}
        <div className="fin-cfg-col">
          <section className="fin-card">
            <div className="fin-cfg-card__title">
            <User size={15} /> Perfil
          </div>

          <div className="fin-foto-row" style={{ marginBottom: 16 }}>
            <div className="fin-foto">
              {perfil?.foto ? (
                <img src={perfil.foto} alt="Sua foto de perfil" />
              ) : (
                iniciais(perfil)
              )}
              {salvandoFoto && (
                <div className="fin-foto__carregando">
                  <Loader2 size={20} className="fin-spin" />
                </div>
              )}
            </div>

            <div className="fin-foto-acoes">
              <div className="fin-form__actions">
                <button
                  type="button"
                  className="fin-btn fin-btn--outline fin-btn--sm"
                  onClick={() => arquivoRef.current?.click()}
                  disabled={salvandoFoto}
                >
                  <Camera size={13} /> {perfil?.foto ? "Trocar foto" : "Enviar foto"}
                </button>

                {perfil?.foto && (
                  <button
                    type="button"
                    className="fin-btn fin-btn--danger fin-btn--sm"
                    onClick={handleRemoverFoto}
                    disabled={salvandoFoto}
                  >
                    <Trash2 size={13} /> Remover
                  </button>
                )}
              </div>

              <span className="fin-field__hint">
                JPEG, PNG ou WebP. Recortada no centro e reduzida aqui mesmo antes
                de subir. Sem foto, ficam as iniciais.
              </span>

              <input
                ref={arquivoRef}
                type="file"
                accept="image/jpeg,image/png,image/webp"
                onChange={handleFoto}
                style={{ display: "none" }}
              />
            </div>
          </div>

          <form className="fin-form" onSubmit={handleNome}>
            <div className="fin-field">
              <label htmlFor="nome">Nome</label>
              <input
                id="nome"
                value={nome}
                onChange={(e) => setNome(e.target.value)}
                placeholder="Como você quer ser chamado"
              />
            </div>

            <div className="fin-field">
              <label htmlFor="mail">E-mail</label>
              <input id="mail" value={perfil?.email || ""} disabled />
              <span className="fin-field__hint">
                É com ele que você entra. Para trocar, use o criar_usuario.py.
              </span>
            </div>

            <div className="fin-form__actions">
              <button className="fin-btn fin-btn--primary fin-btn--sm" disabled={salvandoNome}>
                {salvandoNome ? (
                  <>
                    <Loader2 size={13} className="fin-spin" /> Salvando...
                  </>
                ) : (
                  <>
                    <Check size={13} /> Salvar
                  </>
                )}
              </button>
            </div>
            </form>
          </section>
        </div>

        {/* Não há card de aparência: o tema se troca pelo botão da topbar,
            que está sempre à mão. Duplicar o controle aqui só criaria dois
            lugares para fazer a mesma coisa. */}

        {/* ── Coluna 2: segurança ── */}
        <div className="fin-cfg-col">
          <section className="fin-card">
            <div className="fin-cfg-card__title">
              <KeyRound size={15} /> Senha
              </div>

            <form className="fin-form" onSubmit={handleSenha}>
              <div className="fin-field">
                <label htmlFor="s-atual">Senha atual</label>
                <div className="fin-pwd">
                  <input
                    id="s-atual"
                    type={mostrarSenha ? "text" : "password"}
                    autoComplete="current-password"
                    value={senhaAtual}
                    onChange={(e) => setSenhaAtual(e.target.value)}
                    required
                  />
                  <button
                    type="button"
                    className="fin-pwd__toggle"
                    onClick={() => setMostrarSenha((v) => !v)}
                    aria-label={mostrarSenha ? "Ocultar senhas" : "Mostrar senhas"}
                  >
                    {mostrarSenha ? <EyeOff size={15} /> : <Eye size={15} />}
                  </button>
                </div>
              </div>

              <div className="fin-form__row">
                <div className="fin-field">
                  <label htmlFor="s-nova">Nova senha</label>
                  <input
                    id="s-nova"
                    type={mostrarSenha ? "text" : "password"}
                    autoComplete="new-password"
                    value={senhaNova}
                    onChange={(e) => setSenhaNova(e.target.value)}
                    minLength={8}
                    required
                  />
                </div>
                <div className="fin-field">
                  <label htmlFor="s-conf">Repetir</label>
                  <input
                    id="s-conf"
                    type={mostrarSenha ? "text" : "password"}
                    autoComplete="new-password"
                    value={senhaConfirma}
                    onChange={(e) => setSenhaConfirma(e.target.value)}
                    minLength={8}
                    required
                  />
                </div>
              </div>

              <div className="fin-form__actions">
                <button className="fin-btn fin-btn--primary fin-btn--sm" disabled={salvandoSenha}>
                  {salvandoSenha ? (
                    <>
                      <Loader2 size={13} className="fin-spin" /> Alterando...
                    </>
                  ) : (
                    <>
                      <KeyRound size={13} /> Alterar senha
                    </>
                  )}
                </button>
              </div>
              </form>
          </section>

          {/* ── 2FA ── */}
          <section className="fin-card">
            <div className="fin-cfg-card__title">
              <ShieldCheck size={15} /> Verificação em duas etapas
              </div>

            {modo2fa === "idle" && (
              <div className="fin-form">
                <span
                  className="fin-status-pill"
                  style={{ "--pc": dosDoisFa ? "var(--fin-in)" : "var(--fin-warn)", alignSelf: "flex-start" }}
                >
                  {dosDoisFa ? <ShieldCheck size={12} /> : <TriangleAlert size={12} />}
                  {dosDoisFa ? "Ativa" : "Desativada"}
                </span>

                <p className="fin-field__hint">
                  {dosDoisFa
                    ? "Um código do autenticador é pedido toda vez que você abre o painel. Trocou de celular? Reconfigure: o código antigo para de valer na hora."
                    : "Sem ela, quem souber sua senha entra no painel. Vale o minuto que leva para configurar."}
                </p>

                <div className="fin-form__actions">
                  <button
                    type="button"
                    className={`fin-btn fin-btn--sm ${dosDoisFa ? "fin-btn--outline" : "fin-btn--primary"}`}
                    onClick={abrirSetup}
                  >
                    <ShieldCheck size={13} /> {dosDoisFa ? "Reconfigurar" : "Ativar agora"}
                  </button>

                  {dosDoisFa && (
                    <button
                      type="button"
                      className="fin-btn fin-btn--danger fin-btn--sm"
                      onClick={() => {
                        setCodigo("");
                        setModo2fa("desativar");
                      }}
                    >
                      Desativar
                    </button>
                  )}
                </div>
              </div>
            )}

            {modo2fa === "setup" && (
              <form className="fin-form" onSubmit={confirmarSetup}>
                <p className="fin-field__hint">
                  Leia o QR code no seu autenticador e digite o código gerado para confirmar.
                </p>
                {qrDataUrl && <img src={qrDataUrl} alt="QR code do autenticador" className="fin-qr" />}
                <CampoCodigo valor={codigo} onChange={setCodigo} />
                <AcoesCodigo
                  salvando={salvando2fa}
                  codigo={codigo}
                  rotulo="Confirmar"
                  onCancelar={() => {
                    setModo2fa("idle");
                    setQrDataUrl("");
                    setCodigo("");
                  }}
                />
              </form>
            )}

            {modo2fa === "desativar" && (
              <form className="fin-form" onSubmit={confirmarDesativacao}>
                <div className="fin-alert fin-alert--error">
                  <TriangleAlert size={14} />
                  <span>
                    Depois disso, sua senha passa a ser a única barreira. Digite um código
                    válido para confirmar.
                  </span>
                </div>
                <CampoCodigo valor={codigo} onChange={setCodigo} />
                <AcoesCodigo
                  salvando={salvando2fa}
                  codigo={codigo}
                  rotulo="Desativar"
                  perigo
                  onCancelar={() => {
                    setModo2fa("idle");
                    setCodigo("");
                  }}
                />
                </form>
              )}
          </section>
        </div>

        {/* ── Orçamentos: linha inteira, é uma tabela ── */}
        <section className="fin-card fin-cfg-largo">
          <div className="fin-cfg-card__title">
            <Target size={15} /> Orçamento por categoria
          </div>

          <p className="fin-field__hint" style={{ marginBottom: 12 }}>
            Teto mensal de cada categoria. É daqui que saem os avisos de
            &ldquo;gasto acima do previsto&rdquo; no painel. Deixe em branco ou zero para
            não acompanhar a categoria.
          </p>

          {listaCategorias.length === 0 ? (
            <div className="fin-empty">
              <Target size={26} />
              <span>Nenhuma categoria de saída registrada ainda.</span>
            </div>
          ) : (
            <form onSubmit={handleOrcamentos}>
              {/* Mesmo mapa do dashboard: a bolinha aqui tem a cor da fatia lá. */}
              {listaCategorias.map((cat) => {
                const teto = Number(orcamentos[cat]) || 0;
                const gasto = gastoDoMes[cat] || 0;
                return (
                  <div key={cat} className="fin-budget-row" style={{ "--dc": corDaCategoria(cat) }}>
                    <span className="fin-budget-row__dot" />
                    <span className="fin-budget-row__name">
                      {cat}
                      <span className="fin-field__hint" style={{ marginLeft: 8 }}>
                        {gasto > 0 ? `${brl(gasto)} este mês` : "sem gasto no mês"}
                      </span>
                    </span>
                    {teto > 0 && gasto > teto && (
                      <span className="fin-status-pill" style={{ "--pc": "var(--fin-danger)" }}>
                        estourou
                      </span>
                    )}
                    <input
                      type="number"
                      min="0"
                      step="10"
                      inputMode="decimal"
                      placeholder="sem teto"
                      aria-label={`Teto mensal de ${cat}`}
                      value={orcamentos[cat] ?? ""}
                      onChange={(e) =>
                        setOrcamentos((o) => ({ ...o, [cat]: e.target.value }))
                      }
                    />
                  </div>
                );
              })}

              <div className="fin-form__actions" style={{ marginTop: 14 }}>
                <button className="fin-btn fin-btn--primary fin-btn--sm" disabled={salvandoOrc}>
                  <Check size={13} /> Salvar orçamentos
                </button>
              </div>
            </form>
          )}
        </section>
      </div>

      {toast && (
        <div className={`fin-toast fin-toast--${toast.tipo}`} role="status">
          {toast.tipo === "success" ? <Check size={14} /> : <TriangleAlert size={14} />}
          {toast.msg}
        </div>
      )}
    </>
  );
}

function CampoCodigo({ valor, onChange }) {
  return (
    <div className="fin-field">
      <label htmlFor="cfg-codigo">Código de 6 dígitos</label>
      <input
        id="cfg-codigo"
        type="text"
        inputMode="numeric"
        autoComplete="one-time-code"
        maxLength={6}
        className="fin-otp-input"
        placeholder="000000"
        value={valor}
        onChange={(e) => onChange(e.target.value.replace(/\D/g, "").slice(0, 6))}
        required
        autoFocus
      />
    </div>
  );
}

function AcoesCodigo({ salvando, codigo, rotulo, onCancelar, perigo = false }) {
  return (
    <div className="fin-form__actions">
      <button
        className={`fin-btn fin-btn--sm ${perigo ? "fin-btn--danger" : "fin-btn--primary"}`}
        disabled={salvando || codigo.length < 6}
      >
        {salvando ? (
          <>
            <Loader2 size={13} className="fin-spin" /> Aguarde...
          </>
        ) : (
          <>
            <Check size={13} /> {rotulo}
          </>
        )}
      </button>
      <button type="button" className="fin-btn fin-btn--ghost fin-btn--sm" onClick={onCancelar}>
        Cancelar
      </button>
    </div>
  );
}
