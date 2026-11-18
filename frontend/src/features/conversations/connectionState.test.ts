import { describe, expect, it } from 'vitest';
import { describeConnection, type ConnectionInput } from './connectionState';

function input(overrides: Partial<ConnectionInput> = {}): ConnectionInput {
  return {
    authStatus: 'authenticated',
    hasToken: true,
    workspacesLoading: false,
    workspacesError: null,
    workspaceCount: 1,
    hasWorkspace: true,
    ...overrides,
  };
}

describe('describeConnection', () => {
  it('allows sending when signed in with a workspace', () => {
    const state = describeConnection(input());
    expect(state.canSend).toBe(true);
    expect(state.problem).toBeNull();
  });

  it('reports an unconfigured deployment without blaming the user', () => {
    const state = describeConnection(input({ authStatus: 'unconfigured', hasToken: false }));
    expect(state.canSend).toBe(false);
    expect(state.problem).toBe('unconfigured');
    expect(state.needsSignIn).toBe(false);
    expect(state.message).toMatch(/not configured/i);
  });

  it('asks for a sign-in only when there is genuinely no session', () => {
    const state = describeConnection(input({ hasToken: false, authStatus: 'anonymous' }));
    expect(state.problem).toBe('signed_out');
    expect(state.needsSignIn).toBe(true);
  });

  it('surfaces a rejected token as an error rather than as signed out', () => {
    // This is the regression that mattered: a signed-in user whose token the
    // API rejected was told to sign in again, which could never help.
    const state = describeConnection(
      input({
        workspacesError: 'Your session is invalid or has expired. Please sign in again.',
        workspaceCount: 0,
        hasWorkspace: false,
      }),
    );
    expect(state.problem).toBe('error');
    expect(state.needsSignIn).toBe(false);
    expect(state.message).toContain('could not be loaded');
    expect(state.message).toContain('invalid or has expired');
  });

  it('reports a server misconfiguration distinctly from a bad credential', () => {
    const state = describeConnection(
      input({
        workspacesError:
          'Token verification is not configured on this server. Set SUPABASE_URL and SUPABASE_ANON_KEY.',
      }),
    );
    expect(state.problem).toBe('error');
    expect(state.needsSignIn).toBe(false);
    expect(state.message).toContain('SUPABASE_URL');
  });

  it('prefers the error over the loading state', () => {
    // A failed request must not be shown as "still loading" forever.
    const state = describeConnection(
      input({ workspacesLoading: true, workspacesError: 'network error' }),
    );
    expect(state.problem).toBe('error');
  });

  it('explains that a workspace is needed when the account has none', () => {
    const state = describeConnection(
      input({ workspaceCount: 0, hasWorkspace: false, workspacesLoading: false }),
    );
    expect(state.problem).toBe('no_workspace');
    expect(state.needsSignIn).toBe(false);
    expect(state.message).toMatch(/create one/i);
  });

  it('shows loading while workspaces are in flight', () => {
    const state = describeConnection(
      input({ workspacesLoading: true, workspaceCount: 0, hasWorkspace: false }),
    );
    expect(state.problem).toBe('loading');
  });
});
