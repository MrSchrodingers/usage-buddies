import { defineConfig } from "vite";

// Porta fixa 1421 (o app velho usa 1420) para poderem coexistir.
// Multi-página: index.html (painel) + pill.html (pílula colapsada).
export default defineConfig({
  clearScreen: false,
  server: {
    port: 1421,
    strictPort: true,
    watch: { ignored: ["**/src-tauri/**"] },
  },
  build: {
    rollupOptions: {
      input: {
        main: "index.html",
        pill: "pill.html",
      },
    },
  },
});
