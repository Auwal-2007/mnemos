import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AuthProvider } from '../../lib/auth';
import { CreateWorkspacePanel } from './CreateWorkspacePanel';

/**
 * The panel is exercised signed-out, because Supabase is unconfigured in the
 * test environment. That is still worth asserting: the submit path must not
 * pretend to create anything without a session.
 */
describe('CreateWorkspacePanel', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(new Response('{}', { status: 200 }))));
  });

  it('renders a name field and a submit control', () => {
    render(
      <AuthProvider>
        <CreateWorkspacePanel onCreated={() => undefined} />
      </AuthProvider>,
    );
    expect(screen.getByLabelText('Name')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /create workspace/i })).toBeInTheDocument();
  });

  it('disables submission until a name is entered', () => {
    render(
      <AuthProvider>
        <CreateWorkspacePanel onCreated={() => undefined} />
      </AuthProvider>,
    );
    const submit = screen.getByRole('button', { name: /create workspace/i });
    expect(submit).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Research' } });
    expect(submit).toBeEnabled();
  });

  it('does not call the API without a session', async () => {
    const onCreated = vi.fn();
    render(
      <AuthProvider>
        <CreateWorkspacePanel onCreated={onCreated} />
      </AuthProvider>,
    );
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Research' } });
    fireEvent.click(screen.getByRole('button', { name: /create workspace/i }));

    await waitFor(() => {
      expect(onCreated).not.toHaveBeenCalled();
    });
    // No fabricated success: no request is made when there is no token.
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });
});
