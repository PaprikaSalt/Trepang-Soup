import { defineConfig, loadEnv } from "vite";
import vue from "@vitejs/plugin-vue";

// Vite evaluates this file in Node; Tauri injects the development host there.
// @ts-expect-error process is available while Vite evaluates this file.
const { cwd, env: processEnv } = process;
const tauriDevHost = processEnv.TAURI_DEV_HOST;

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, cwd(), "");

  return {
    // Desktop builds stay at /; the blog Web build is mounted below /apps/trepang-soup/.
    base: env.VITE_PUBLIC_BASE || "/",
    plugins: [vue()],
    clearScreen: false,
    build: {
      // Target browsers support modulepreload, so the embedded app needs no DOM polyfill.
      modulePreload: { polyfill: false },
    },
    server: {
      port: 1420,
      strictPort: true,
      host: tauriDevHost || false,
      hmr: tauriDevHost
        ? {
            protocol: "ws",
            host: tauriDevHost,
            port: 1421,
          }
        : undefined,
      watch: {
        // Rust output is unrelated to Vite HMR and can be very large.
        ignored: ["**/src-tauri/**"],
      },
    },
  };
});
