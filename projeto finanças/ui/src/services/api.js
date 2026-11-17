// Cliente da API local (Flask + MySQL/Laragon).
//
// Um único lugar que sabe falar HTTP. Nenhuma tela monta URL ou header
// na mão, o que mantém o token de sessão fora dos componentes.

// `?.` porque fora do Vite (os testes rodam os serviços direto no Node) o
// import.meta.env não existe.
//
// Na Vercel a API mora no mesmo endereço do app (/api/...), então o build
// de lá liga VITE_API_MESMA_ORIGEM e as chamadas ficam relativas.
const MESMA_ORIGEM = import.meta.env?.VITE_API_MESMA_ORIGEM === "1";
const BASE = MESMA_ORIGEM ? "" : import.meta.env?.VITE_API_BASE || "http://127.0.0.1:8756";

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
    throw new ApiError(
      MESMA_ORIGEM
        ? "Não consegui falar com o servidor. Confira a internet."
        : "Não consegui falar com o servidor local. Ele está rodando?",
      0,
    );
  }

  if (resp.status === 204) return null;

  const dados = await resp.json().catch(() => ({}));
  // 428: a versão dos termos mudou com o app aberto. Qualquer tela que
  // bater nisso vai para o aceite, em vez de cada uma tratar o caso.
  if (resp.status === 428 && window.location.pathname !== "/aceite") {
    window.location.assign("/aceite");
  }
  if (!resp.ok) throw new ApiError(dados.erro || "Falha na requisição.", resp.status);
  return dados;
}

export const api = {
  get: (c) => pedir(c),
  post: (c, corpo) => pedir(c, { metodo: "POST", corpo }),
  put: (c, corpo) => pedir(c, { metodo: "PUT", corpo }),
  patch: (c, corpo) => pedir(c, { metodo: "PATCH", corpo }),
  del: (c, corpo) => pedir(c, { metodo: "DELETE", corpo }),
};
