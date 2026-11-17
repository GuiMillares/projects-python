// Passkeys: entrar com Face ID, digital ou o desbloqueio do aparelho.
//
// O navegador conversa com o leitor biométrico; a biblioteca
// @simplewebauthn/browser só converte os formatos (base64url ⇄ bytes) que
// a API WebAuthn exige. Quem decide se a entrada vale é o servidor, que
// confere a assinatura (api/passkeys.py).
//
// A marca "este aparelho tem passkey" no localStorage é só conveniência:
// serve para abrir o Face ID sozinho ao abrir o app. Se ela sumir, nada
// quebra; se mentir, o servidor recusa e a tela cai na senha.

import {
  browserSupportsWebAuthn,
  platformAuthenticatorIsAvailable,
  startAuthentication,
  startRegistration,
} from "@simplewebauthn/browser";
import { api, guardarToken } from "./api";

const MARCA = "fin_passkey_aqui";

const ler = (k) => {
  try {
    return localStorage.getItem(k);
  } catch {
    return null;
  }
};
const gravar = (k, v) => {
  try {
    if (v == null) localStorage.removeItem(k);
    else localStorage.setItem(k, v);
  } catch {
    // Sem armazenamento: só perde a conveniência.
  }
};

export const suportaPasskey = () => browserSupportsWebAuthn();

/** Há Face ID, digital ou Windows Hello neste aparelho? */
export async function temLeitorNoAparelho() {
  if (!browserSupportsWebAuthn()) return false;
  try {
    return await platformAuthenticatorIsAvailable();
  } catch {
    return false;
  }
}

export const aparelhoTemPasskey = () => ler(MARCA) === "1";
export const marcarAparelho = (tem) => gravar(MARCA, tem ? "1" : null);

/** Nome que aparece na lista de Configurações. A pessoa pode trocar. */
export function apelidoDoAparelho() {
  const ua = navigator.userAgent;
  if (/iphone/i.test(ua)) return "iPhone";
  if (/ipad/i.test(ua) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1)) return "iPad";
  if (/android/i.test(ua)) return "Android";
  if (/windows/i.test(ua)) return "Computador Windows";
  if (/mac os/i.test(ua)) return "Mac";
  return "Este aparelho";
}

/** Erro do navegador → frase para a tela. null = a pessoa cancelou. */
export function textoDoErro(e) {
  const nome = e?.name || e?.cause?.name;
  if (nome === "NotAllowedError" || nome === "AbortError") return null;
  if (nome === "InvalidStateError") return "Este aparelho já está cadastrado.";
  if (nome === "SecurityError") return "O navegador recusou: o endereço não confere.";
  return e?.message || "Não deu certo. Tente de novo.";
}

export async function entrarComPasskey() {
  const { desafioId, opcoes } = await api.post("/api/auth/passkey/opcoes");
  const resposta = await startAuthentication({ optionsJSON: opcoes });
  const { token } = await api.post("/api/auth/passkey/entrar", { desafioId, resposta });
  guardarToken(token);
  marcarAparelho(true);
}

export async function cadastrarPasskey(apelido = apelidoDoAparelho()) {
  const { desafioId, opcoes } = await api.post("/api/passkeys/opcoes");
  const resposta = await startRegistration({ optionsJSON: opcoes });
  const nova = await api.post("/api/passkeys", { desafioId, resposta, apelido });
  marcarAparelho(true);
  return nova;
}

export const listarPasskeys = async () => (await api.get("/api/passkeys")).passkeys;
export const removerPasskey = (id) => api.del(`/api/passkeys/${id}`);
