import { api } from "./api";

export const carregarPerfil = () => api.get("/api/perfil");

export const salvarNome = (nome) => api.put("/api/perfil", { nome: nome.trim() });

export const trocarSenha = (senhaAtual, senhaNova) =>
  api.put("/api/perfil/senha", { senhaAtual, senhaNova });

/** Recebe a data URL já recortada e reduzida (ver services/imagem.js). */
export const salvarFoto = (foto) => api.put("/api/perfil/foto", { foto });

export const removerFoto = () => api.del("/api/perfil/foto");

export const iniciais = (perfil) => {
  const nome = perfil?.nome?.trim();
  if (nome) {
    return nome
      .split(/\s+/)
      .slice(0, 2)
      .map((p) => p[0].toUpperCase())
      .join("");
  }
  return (perfil?.email?.[0] || "?").toUpperCase();
};
