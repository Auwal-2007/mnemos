/**
 * Runtime configuration for the frontend.
 *
 * Only values that are safe for browsers live in VITE_* variables.
 * The service-role key must NEVER be referenced in frontend code.
 */

interface AppConfig {
  apiBaseUrl: string;
  supabaseUrl: string;
  supabaseAnonKey: string;
  appEnv: string;
  requestTimeoutMs: number;
}

function readEnv(key: string, fallback = ''): string {
  const value = import.meta.env[key] as string | undefined;
  return (value ?? fallback).trim();
}

export const config: AppConfig = {
  // Prefer an explicit absolute URL; otherwise use a relative path so the
  // Vite dev proxy (and any reverse proxy in production) can forward it.
  apiBaseUrl: readEnv('VITE_API_BASE_URL', '/api/v1').replace(/\/$/, ''),
  supabaseUrl: readEnv('VITE_SUPABASE_URL'),
  supabaseAnonKey: readEnv('VITE_SUPABASE_ANON_KEY'),
  appEnv: readEnv('VITE_APP_ENV', import.meta.env.MODE),
  requestTimeoutMs: Number(readEnv('VITE_API_TIMEOUT_MS', '15000')) || 15000,
};

export const isSupabaseConfigured = Boolean(config.supabaseUrl && config.supabaseAnonKey);

/** Resolve an API path against the configured base URL. */
export function apiUrl(path: string): string {
  const normalized = path.startsWith('/') ? path : `/${path}`;
  return `${config.apiBaseUrl}${normalized}`;
}
