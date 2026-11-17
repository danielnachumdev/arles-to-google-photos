/** Package default (CD stamps this). Image bake prefers ``VITE_APP_VERSION``. */
export const PACKAGE_VERSION = '1.4.0'

/** Released product version (keep in sync with backend ``src.version``). */
export const APP_VERSION =
  (import.meta.env.VITE_APP_VERSION as string | undefined)?.trim() || PACKAGE_VERSION
