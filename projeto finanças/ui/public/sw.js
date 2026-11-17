// Service worker do app instalado (PWA).
//
// Só guarda a casca: o index.html e os arquivos de /assets, que o Vite
// gera com hash no nome. Dado financeiro NUNCA passa por aqui: a API
// (/api), a Pluggy e qualquer outro domínio vão direto para a rede, sem
// cópia no aparelho.
//
// Navegação é rede primeiro, para um deploy novo valer na hora; o cache
// só serve para abrir a casca quando o celular está sem sinal.

const CACHE = "fin-casca-v1";

self.addEventListener("install", () => self.skipWaiting());

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches
      .keys()
      .then((nomes) => Promise.all(nomes.filter((n) => n !== CACHE).map((n) => caches.delete(n))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;

  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith("/api/")) return;

  if (req.mode === "navigate") {
    e.respondWith(
      fetch(req)
        .then((resp) => {
          const copia = resp.clone();
          caches.open(CACHE).then((c) => c.put("/index.html", copia));
          return resp;
        })
        .catch(() => caches.match("/index.html")),
    );
    return;
  }

  if (url.pathname.startsWith("/assets/") || url.pathname.startsWith("/icons/")) {
    e.respondWith(
      caches.match(req).then(
        (salvo) =>
          salvo ||
          fetch(req).then((resp) => {
            if (resp.ok) {
              const copia = resp.clone();
              caches.open(CACHE).then((c) => c.put(req, copia));
            }
            return resp;
          }),
      ),
    );
  }
});
