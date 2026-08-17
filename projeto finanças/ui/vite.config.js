import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Porta fixa e host travado: o Tauri aponta o webview para este dev server
// (tauri.conf.json → build.devUrl). Sem porta fixa o webview abre em branco.
export default defineConfig({
  plugins: [react()],
  clearScreen: false,
  server: {
    port: 1420,
    strictPort: true,
  },
  build: {
    // O webview do Tauri (WebView2 / WKWebView) é sempre moderno — não há
    // motivo para transpilar para navegadores antigos.
    target: "es2021",
    sourcemap: false,
  },
});
