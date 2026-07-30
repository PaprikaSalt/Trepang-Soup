const DEFAULT_SERVER_URL = import.meta.env.PROD
  ? "http://ljy32.cn:8787"
  : "http://127.0.0.1:8787";

// The backend address is public configuration. VITE_SERVER_URL remains available
// for local integration tests and future reverse-proxy migrations.
export const SERVER_URL = (import.meta.env.VITE_SERVER_URL || DEFAULT_SERVER_URL).replace(
  /\/+$/,
  "",
);
