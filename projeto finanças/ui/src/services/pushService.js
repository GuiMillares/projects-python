// Notificações push no aparelho. O servidor decide o que mandar
// (api/notificacoes.py); aqui só a inscrição deste navegador.

import { api } from "./api";
import { ehIOS, jaInstalado } from "./instalar";

/** O que impede este aparelho de receber, ou null se pode. */
export function impedimento() {
  if (!("serviceWorker" in navigator) || !("PushManager" in window) || !("Notification" in window)) {
    // No iPhone, push só existe no app instalado na tela inicial.
    return ehIOS() && !jaInstalado() ? "iosSemInstalar" : "semSuporte";
  }
  if (Notification.permission === "denied") return "negado";
  return null;
}

const paraBytes = (b64) => {
  const base = (b64 + "=".repeat((4 - (b64.length % 4)) % 4)).replace(/-/g, "+").replace(/_/g, "/");
  return Uint8Array.from(atob(base), (c) => c.charCodeAt(0));
};

async function inscricaoAtual() {
  if (!("serviceWorker" in navigator)) return null;
  const reg = await navigator.serviceWorker.getRegistration();
  return reg ? reg.pushManager.getSubscription() : null;
}

export async function lerEstado() {
  const atual = await inscricaoAtual().catch(() => null);
  const q = atual ? `?endpoint=${encodeURIComponent(atual.endpoint)}` : "";
  return api.get(`/api/push${q}`);
}

/** Pede a permissão, inscreve este aparelho e manda para o servidor. */
export async function ativar(chavePublica, aparelho) {
  const permissao = await Notification.requestPermission();
  if (permissao !== "granted") {
    throw new Error("Sem permissão, o aparelho não mostra as notificações.");
  }
  const reg = await navigator.serviceWorker.ready;
  let insc = await reg.pushManager.getSubscription();
  if (!insc) {
    insc = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: paraBytes(chavePublica),
    });
  }
  return api.post("/api/push/inscricao", { inscricao: insc.toJSON(), aparelho });
}

export async function desativar() {
  const insc = await inscricaoAtual();
  if (!insc) return;
  await api.del("/api/push/inscricao", { endpoint: insc.endpoint });
  await insc.unsubscribe();
}

export const salvarPreferencias = (prefs) => api.put("/api/push/preferencias", prefs);
export const enviarTeste = () => api.post("/api/push/teste");
