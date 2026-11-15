/**
 * Supabase browser client.
 *
 * Only the PUBLIC anon key is used in the browser. The service-role key
 * must never be imported into frontend code.
 */

import { createClient, type SupabaseClient } from '@supabase/supabase-js';
import { config, isSupabaseConfigured } from '../config';

let client: SupabaseClient | null = null;

/**
 * Return the shared Supabase client, or null when the environment has not
 * been configured. Callers must handle the null case explicitly rather
 * than pretending auth is available.
 */
export function getSupabaseClient(): SupabaseClient | null {
  if (!isSupabaseConfigured) return null;
  if (!client) {
    client = createClient(config.supabaseUrl, config.supabaseAnonKey, {
      auth: {
        persistSession: true,
        autoRefreshToken: true,
        detectSessionInUrl: true,
        flowType: 'pkce',
      },
    });
  }
  return client;
}
