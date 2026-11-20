/// <reference types="vite/client" />

/** True only in `npm run build:replay` (static, backend-free replay build). */
declare const __STATIC_REPLAY__: boolean;

interface ImportMetaEnv {
  /** Local backend HTTP origin, e.g. http://127.0.0.1:8000. Never put secrets in VITE_* vars. */
  readonly VITE_BACKEND_HTTP_ORIGIN?: string;
}
