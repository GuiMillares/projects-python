import { api } from "./api";

export const carregarPerfil = () => api.get("/api/perfil");

export const salvarNome = (nome) => api.put("/api/perfil", { nome: nome.trim() });

export const trocarSenha = (senhaAtual, senhaNova) =>
  api.put("/api/perfil/senha", { senhaAtual, senhaNova });

/** Recebe a data URL já recortada e reduzida (ver services/imagem.js). */
export const salvarFoto = (foto) => api.put("/api/perfil/foto", { foto });

export const removerFoto = () => api.del("/api/perfil/foto");

// ── LGPD ────────────────────────────────────────────────────

/** Termos de uso e política de privacidade, com a versão que vale agora. */
export const lerDocumentos = () => api.get("/api/documentos");

export const aceitarDocumentos = (versao) => api.post("/api/aceite", { versao });

/** Apaga a conta e tudo dela. `codigo` só é exigido com o 2FA ativo. */
export const apagarConta = (senha, codigo) => api.del("/api/conta", { senha, codigo });

/**
 * Baixa tudo o que o app guarda sobre a pessoa num arquivo JSON. O arquivo
 * é montado aqui a partir da resposta: a API não precisa saber de download.
 */
export async function exportarDados() {
  const dados = await api.get("/api/conta/exportar");
  const blob = new Blob([JSON.stringify(dados, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `meus-dados-financas-${dados.exportadoEm.slice(0, 10)}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

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
