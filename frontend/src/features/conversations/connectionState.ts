/**
 * Why the composer is (or is not) usable.
 *
 * The previous behaviour was a single message — "Sign in and create a workspace
 * to start a conversation" — shown whenever no workspace had loaded. That
 * conflated at least four different situations, and the most common one was the
 * worst: a signed-in user whose token the server had rejected was told to sign
 * in again, which could never help. Users reasonably concluded the session was
 * broken rather than the API call.
 *
 * So the reason is computed explicitly, and the most specific cause wins. Each
 * branch tells the user something they can act on.
 */

import type { AuthStatus } from '../../lib/auth';

export type ConnectionProblem =
  | 'unconfigured'
  | 'signed_out'
  | 'loading'
  | 'error'
  | 'no_workspace'
  | null;

export interface ConnectionState {
  canSend: boolean;
  problem: ConnectionProblem;
  /** A sentence safe to show the user. Null when there is no problem. */
  message: string | null;
  /** True when re-authenticating is the fix. */
  needsSignIn: boolean;
}

export interface ConnectionInput {
  authStatus: AuthStatus;
  hasToken: boolean;
  workspacesLoading: boolean;
  workspacesError: string | null;
  workspaceCount: number;
  hasWorkspace: boolean;
}

export function describeConnection(input: ConnectionInput): ConnectionState {
  if (input.authStatus === 'unconfigured') {
    return {
      canSend: false,
      problem: 'unconfigured',
      message:
        'Authentication is not configured for this deployment, so no account can be used. An administrator must set the Supabase project URL and anon key.',
      needsSignIn: false,
    };
  }

  if (!input.hasToken) {
    return {
      canSend: false,
      problem: 'signed_out',
      message: 'Sign in to ask questions about your knowledge.',
      needsSignIn: true,
    };
  }

  // Reported before loading so a failed request is never mistaken for slowness.
  if (input.workspacesError) {
    return {
      canSend: false,
      problem: 'error',
      message: `Your workspace could not be loaded: ${input.workspacesError}`,
      needsSignIn: false,
    };
  }

  if (input.workspacesLoading) {
    return {
      canSend: false,
      problem: 'loading',
      message: 'Loading your workspace…',
      needsSignIn: false,
    };
  }

  if (input.workspaceCount === 0) {
    return {
      canSend: false,
      problem: 'no_workspace',
      message: 'Your account has no workspace yet. Create one to start asking questions.',
      needsSignIn: false,
    };
  }

  if (!input.hasWorkspace) {
    return {
      canSend: false,
      problem: 'loading',
      message: 'Preparing your workspace…',
      needsSignIn: false,
    };
  }

  return {
    canSend: true,
    problem: null,
    message: 'Answers come only from your indexed knowledge, and every claim cites its source.',
    needsSignIn: false,
  };
}
