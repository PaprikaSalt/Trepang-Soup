/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_SERVER_URL?: string;
  readonly VITE_TRANSPORT_MODE?: "server" | "mock";
  readonly VITE_PUBLIC_BASE?: string;
  readonly VITE_ENABLE_ADMIN?: "true" | "false";
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

declare module "*.vue" {
  import type { DefineComponent } from "vue";
  const component: DefineComponent<{}, {}, any>;
  export default component;
}
