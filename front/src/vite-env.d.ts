/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** 演示数据开关，见 .env.example 与 vite.config.ts */
  readonly VITE_DEMO_MODE?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
