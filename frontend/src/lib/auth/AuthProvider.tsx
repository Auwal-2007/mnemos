/**
 * Authentication state for the application.
 *
 * Two honest modes:
 *  - `configured`: Supabase is configured; real sessions are tracked.
 *  - `unconfigured`: no Supabase credentials; the UI states clearly that
 *    authentication is unavailable rather than faking a signed-in user.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import type { Session, User } from '@supabase/supabase-js';
import { isSupabaseConfigured } from '../config';
import { toErrorMessage } from '../api/client';
import { getSupabaseClient } from './supabaseClient';

export type AuthStatus = 'loading' | 'authenticated' | 'anonymous' | 'unconfigured';

export interface AuthContextValue {
  status: AuthStatus;
  session: Session | null;
  user: User | null;
  accessToken: string | null;
  error: string | null;
  isConfigured: boolean;
  signInWithPassword: (email: string, password: string) => Promise<void>;
  signUpWithPassword: (email: string, password: string) => Promise<{ needsConfirmation: boolean }>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }): JSX.Element {
  const supabase = getSupabaseClient();
  const [status, setStatus] = useState<AuthStatus>(
    isSupabaseConfigured ? 'loading' : 'unconfigured',
  );
  const [session, setSession] = useState<Session | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!supabase) return undefined;
    let active = true;

    supabase.auth
      .getSession()
      .then(({ data, error: sessionError }) => {
        if (!active) return;
        if (sessionError) {
          setError(sessionError.message);
          setStatus('anonymous');
          return;
        }
        setSession(data.session);
        setStatus(data.session ? 'authenticated' : 'anonymous');
      })
      .catch((cause: unknown) => {
        if (!active) return;
        setError(toErrorMessage(cause));
        setStatus('anonymous');
      });

    const { data: subscription } = supabase.auth.onAuthStateChange((_event, nextSession) => {
      setSession(nextSession);
      setStatus(nextSession ? 'authenticated' : 'anonymous');
    });

    return () => {
      active = false;
      subscription.subscription.unsubscribe();
    };
  }, [supabase]);

  const signInWithPassword = useCallback(
    async (email: string, password: string) => {
      if (!supabase) throw new Error('Authentication is not configured for this deployment.');
      setError(null);
      const { error: signInError } = await supabase.auth.signInWithPassword({ email, password });
      if (signInError) {
        setError(signInError.message);
        throw new Error(signInError.message);
      }
    },
    [supabase],
  );

  const signUpWithPassword = useCallback(
    async (email: string, password: string) => {
      if (!supabase) throw new Error('Authentication is not configured for this deployment.');
      setError(null);
      const { data, error: signUpError } = await supabase.auth.signUp({ email, password });
      if (signUpError) {
        setError(signUpError.message);
        throw new Error(signUpError.message);
      }
      return { needsConfirmation: !data.session };
    },
    [supabase],
  );

  const signOut = useCallback(async () => {
    if (!supabase) return;
    const { error: signOutError } = await supabase.auth.signOut();
    if (signOutError) {
      setError(signOutError.message);
      throw new Error(signOutError.message);
    }
    setSession(null);
    setStatus('anonymous');
  }, [supabase]);

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      session,
      user: session?.user ?? null,
      accessToken: session?.access_token ?? null,
      error,
      isConfigured: isSupabaseConfigured,
      signInWithPassword,
      signUpWithPassword,
      signOut,
    }),
    [status, session, error, signInWithPassword, signUpWithPassword, signOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used within AuthProvider');
  return context;
}
