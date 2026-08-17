// Cliente da API local (Flask + MySQL/Laragon).
//
// Um único lugar que sabe falar HTTP. Nenhuma tela monta URL ou header
// na mão, o que mantém o token de sessão fora dos componentes.

const BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8756";

// O token fica em sessionStorage, não em localStorage: fechar a janela
// derruba a sessão e o código do autenticador é pedido de novo. O
// servidor também expira a sessão sozinho. Isto é só a metade do
// cliente.
const CHAVE = "fin_token";

export const lerToken = () => sessionStorage.getItem(CHAVE) || "";
export const guardarToken = (t) => sessionStorage.setItem(CHAVE, t);
export const limparToken = () => sessionStorage.removeItem(CHAVE);

/** Erro com o status HTTP junto, para a tela decidir o que dizer. */
export class ApiError extends Error {
  constructor(mensagem, status) {
    super(mensagem);
    this.name = "ApiError";
    this.status = status;
  }
}

async function pedir(caminho, { metodo = "GET", corpo } = {}) {
  const token = lerToken();

  let resp;
  try {
    resp = await fetch(`${BASE}${caminho}`, {
      method: metodo,
      headers: {
        ...(corpo ? { "Content-Type": "application/json" } : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: corpo ? JSON.stringify(corpo) : undefined,
    });
  } catch {
    // fetch só rejeita quando nem chegou a falar com o servidor.
    throw new ApiError("Não consegui falar com o servidor local. Ele está rodando?", 0);
  }

  if (resp.status === 204) return null;

  const dados = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new ApiError(dados.erro || "Falha na requisição.", resp.status);
  return dados;
}

export const api = {
  get: (c) => pedir(c),
  post: (c, corpo) => pedir(c, { metodo: "POST", corpo }),
  put: (c, corpo) => pedir(c, { metodo: "PUT", corpo }),
  del: (c) => pedir(c, { metodo: "DELETE" }),
};
