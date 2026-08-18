import { api } from "./api";

/**
 * Metas com subtarefas, mais o estado do personagem.
 *
 * `personagem` (xp, nível, progresso) vem calculado do servidor e não é
 * gravado em lugar nenhum: deriva do que está concluído. Por isso as rotas
 * que mudam conclusão devolvem o personagem novo junto, e a tela não
 * precisa recarregar tudo para animar o ganho de XP.
 */
export const listarMetas = () => api.get("/api/metas");

export const criarMeta = (meta) => api.post("/api/metas", meta);

export const apagarMeta = (id) => api.del(`/api/metas/${id}`);

export const atualizarMeta = (id, campos) => api.patch(`/api/metas/${id}`, campos);

export const gerarSubtarefas = (metaId) =>
  api.post(`/api/metas/${metaId}/subtarefas/gerar`);

export const criarSubtarefa = (metaId, titulo) =>
  api.post(`/api/metas/${metaId}/subtarefas`, { titulo });

export const alternarSubtarefa = (id, concluida) =>
  api.patch(`/api/subtarefas/${id}`, { concluida });

export const apagarSubtarefa = (id) => api.del(`/api/subtarefas/${id}`);

/** Quantas subtarefas foram feitas, para a barra de progresso da meta. */
export function progressoDaMeta(meta) {
  const total = meta.subtarefas.length;
  const feitas = meta.subtarefas.filter((s) => s.concluida).length;
  return {
    total,
    feitas,
    percentual: total ? Math.round((feitas / total) * 100) : meta.concluida ? 100 : 0,
    // XP que ainda dá para ganhar nesta meta, contando o bônus do fim.
    xpRestante:
      meta.subtarefas.filter((s) => !s.concluida).reduce((soma, s) => soma + s.xp, 0) +
      (meta.concluida ? 0 : meta.bonusXp),
  };
}
