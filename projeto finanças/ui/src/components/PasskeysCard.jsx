// Configurações → Entrar com Face ID ou digital.
//
// Lista os aparelhos com passkey, liga este aparelho e remove os que não
// valem mais (celular perdido, trocado). Remover aqui derruba a passkey no
// servidor: mesmo que o aparelho ainda a guarde, ela não abre mais nada.

import { Fingerprint, Loader2, Plus, Smartphone, Trash2 } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { dataCurta } from "../services/financasService";
import {
  aparelhoTemPasskey,
  cadastrarPasskey,
  listarPasskeys,
  marcarAparelho,
  removerPasskey,
  suportaPasskey,
  textoDoErro,
} from "../services/passkeyService";
import ConfirmarExclusao from "./ConfirmarExclusao";

const quando = (iso) => (iso ? `${dataCurta(iso.slice(0, 10))}/${iso.slice(2, 4)}` : "");

export default function PasskeysCard({ avisar }) {
  const [lista, setLista] = useState(null);
  const [adicionando, setAdicionando] = useState(false);
  const [paraRemover, setParaRemover] = useState(null);
  const [removendo, setRemovendo] = useState(false);
  const [desteAparelho, setDesteAparelho] = useState(aparelhoTemPasskey);
  const suporta = suportaPasskey();

  // Quem chama recria o avisar a cada render: guardado numa ref, ele não
  // vira dependência do carregar (senão a lista recarregaria sem parar).
  const avisarRef = useRef(avisar);
  avisarRef.current = avisar;

  const carregar = useCallback(async () => {
    try {
      setLista(await listarPasskeys());
    } catch (e) {
      setLista([]);
      avisarRef.current(e.message, "error");
    }
  }, []);

  useEffect(() => {
    carregar();
  }, [carregar]);

  const adicionar = async () => {
    setAdicionando(true);
    try {
      await cadastrarPasskey();
      setDesteAparelho(true);
      avisar("Pronto. Neste aparelho, é só o Face ID ou a digital.");
      await carregar();
    } catch (e) {
      if (e?.name === "InvalidStateError") {
        marcarAparelho(true);
        setDesteAparelho(true);
        avisar("Este aparelho já estava cadastrado.");
        return;
      }
      const texto = e?.status ? e.message : textoDoErro(e);
      if (texto) avisar(texto, "error");
    } finally {
      setAdicionando(false);
    }
  };

  const remover = async () => {
    setRemovendo(true);
    try {
      await removerPasskey(paraRemover.id);
      // Não dá para saber se a removida era a deste aparelho. Esquecer a
      // marca só custa um toque no botão na próxima entrada.
      marcarAparelho(false);
      setDesteAparelho(false);
      setParaRemover(null);
      avisar("Aparelho removido.");
      await carregar();
    } catch (e) {
      avisar(e.message, "error");
    } finally {
      setRemovendo(false);
    }
  };

  return (
    <section className="fin-card">
      <div className="fin-cfg-card__title">
        <Fingerprint size={15} /> Entrar com Face ID ou digital
      </div>

      <p className="fin-field__hint" style={{ marginBottom: 12 }}>
        Cada aparelho cadastrado entra só com a biometria ou o desbloqueio dele, sem senha nem
        código. A biometria nunca sai do aparelho: o Lastro guarda só uma chave pública. Senha e
        código continuam valendo como reserva.
      </p>

      {lista === null ? (
        <div className="fin-loading" style={{ padding: "8px 0" }}>
          <Loader2 size={15} className="fin-spin" />
        </div>
      ) : lista.length === 0 ? (
        <p className="fin-field__hint" style={{ marginBottom: 12 }}>
          Nenhum aparelho cadastrado ainda.
        </p>
      ) : (
        <ul className="fin-passkeys">
          {lista.map((p) => (
            <li key={p.id} className="fin-passkeys__item">
              <Smartphone size={15} className="fin-passkeys__ico" />
              <div className="fin-passkeys__corpo">
                <span className="fin-passkeys__nome">{p.apelido}</span>
                <span className="fin-field__hint">
                  desde {quando(p.criadoEm)}
                  {p.usadoEm ? ` · última entrada ${quando(p.usadoEm)}` : " · ainda não usado"}
                </span>
              </div>
              <button
                className="fin-lanc-item__excluir"
                onClick={() => setParaRemover(p)}
                aria-label={`Remover ${p.apelido}`}
                title="Remover"
              >
                <Trash2 size={14} />
              </button>
            </li>
          ))}
        </ul>
      )}

      {suporta ? (
        !desteAparelho && (
          <div className="fin-form__actions">
            <button
              className="fin-btn fin-btn--primary fin-btn--sm"
              onClick={adicionar}
              disabled={adicionando}
            >
              {adicionando ? <Loader2 size={13} className="fin-spin" /> : <Plus size={13} />}
              Cadastrar este aparelho
            </button>
          </div>
        )
      ) : (
        <p className="fin-field__hint">Este navegador não aceita passkeys.</p>
      )}

      {paraRemover && (
        <ConfirmarExclusao
          titulo={`Remover ${paraRemover.apelido}?`}
          mensagem="Esse aparelho deixa de entrar com a biometria na hora. Para usar de novo, entre com senha e código nele e cadastre outra vez."
          rotuloConfirmar="Remover"
          ocupado={removendo}
          onConfirmar={remover}
          onCancelar={() => setParaRemover(null)}
        />
      )}
    </section>
  );
}
