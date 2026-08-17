// Sessão e 2FA.
//
// INVARIANTE: o segredo TOTP nunca existe no frontend. O servidor gera,
// guarda em `usuarios.totp_secret` e valida; daqui só saem 6 dígitos e
// só volta "ok" ou "não ok". A única coisa que o cliente vê uma vez é o
// `otpauth://` do cadastro, para virar QR code, e nem ele é guardado.
//
// Se um dia aparecer `otplib`/`speakeasy` no package.json do front, é
// sinal de que o segredo vazou para cá.

import { api, guardarToken, limparToken, lerToken } from "./api";

/**
 * Autentica com senha. A sessão nasce PARCIAL: o token devolvido só
 * abre as rotas de 2FA. Quem promove a sessão é `verificar2FA`.
 *
 * @returns {"2fa"|"setup2fa"} etapa seguinte do fluxo
 */
export async function entrar(email, senha) {
  const { token, etapa } = await api.post("/api/auth/login", { email, senha });
  guardarToken(token);
  return etapa;
}

/** Pede um segredo novo ao servidor e recebe só o otpauth:// do QR. */
export async function iniciarSetup2FA() {
  const { otpauthUri } = await api.post("/api/auth/2fa/setup");
  return otpauthUri;
}

/** Valida o código NO SERVIDOR. Em caso de sucesso, a sessão vira completa. */
export async function verificar2FA(codigo) {
  await api.post("/api/auth/2fa/verify", { codigo: String(codigo).replace(/\D/g, "") });
  return true;
}

/** Desativa o 2FA. Exige código válido para não virar bypass. */
export async function desativar2FA(codigo) {
  await api.post("/api/auth/2fa/disable", { codigo: String(codigo).replace(/\D/g, "") });
  return true;
}

export async function sair() {
  // Apaga a sessão do servidor; se a chamada falhar, o token local some
  // do mesmo jeito: sair nunca pode ficar pela metade.
  try {
    await api.post("/api/auth/logout");
  } catch {
    /* ignorado de propósito */
  }
  limparToken();
}

export const temToken = () => Boolean(lerToken());

/**
 * A sessão do servidor é a fonte da verdade. Um token guardado pode já
 * ter expirado, e só o servidor sabe se ele passou pelo 2FA. Por isso
 * quem decide se está autenticado é esta chamada, não o sessionStorage.
 */
export async function sessaoValida() {
  if (!lerToken()) return false;
  try {
    await api.get("/api/perfil");
    return true;
  } catch {
    return false;
  }
}
