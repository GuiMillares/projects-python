// Espaço compartilhado (casal, família) e convites. Regras no servidor:
// api/espacos.py. Aqui só o transporte e a guarda do convite em trânsito.

import { api } from "./api";

// Quem abre o link e escolhe "já tenho conta" passa pelo login antes de
// responder. O código do convite espera aqui, só nesta aba, e o app
// retoma ao entrar (PerguntaVinculo).
const PENDENTE = "fin_convite";

export const guardarConviteEmTransito = (token) => {
  try {
    sessionStorage.setItem(PENDENTE, token);
  } catch {
    // Sem armazenamento: a pessoa abre o link de novo depois de entrar.
  }
};

export const tirarConviteEmTransito = () => {
  try {
    const t = sessionStorage.getItem(PENDENTE);
    sessionStorage.removeItem(PENDENTE);
    return t;
  } catch {
    return null;
  }
};

export const verConvite = (token) => api.get(`/api/convites/${encodeURIComponent(token)}`);
export const cadastrarPorConvite = (token, dados) =>
  api.post(`/api/convites/${encodeURIComponent(token)}/cadastro`, dados);
export const pegarConvite = (token) => api.post(`/api/convites/${encodeURIComponent(token)}/pegar`);

export const lerEspaco = () => api.get("/api/espaco");
export const gerarConvite = () => api.post("/api/espaco/convite");
export const cancelarConvite = () => api.del("/api/espaco/convite");
export const aceitarConvite = (conviteId) => api.post("/api/espaco/aceitar", { conviteId });
export const recusarConvite = (conviteId) => api.post("/api/espaco/recusar", { conviteId });
export const sairDoEspaco = () => api.post("/api/espaco/sair");
export const removerMembro = (id) => api.del(`/api/espaco/membros/${id}`);

export const linkDoConvite = (token) => `${window.location.origin}/convite/${token}`;
