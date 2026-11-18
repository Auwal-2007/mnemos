import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { AuthProvider } from '../../lib/auth';
import { AgentConversationPage } from './AgentConversationPage';
import { OrchestratorConversationPage } from './OrchestratorConversationPage';

/**
 * These tests describe the *connected* conversation pages.
 *
 * The previous version of this file asserted that the composer was permanently
 * disabled because "no model execution exists yet". That is no longer true, and
 * asserting it would have locked in a false statement about the product. What is
 * asserted now is the behaviour a signed-out visitor actually gets: the composer
 * is disabled with a sign-in explanation, and nothing is fabricated to fill the
 * empty transcript.
 *
 * Supabase is unconfigured in the test environment, so AuthProvider reports
 * `unconfigured` and there is no access token — which is exactly the signed-out
 * case worth testing.
 */
function renderAt(path: string): void {
  render(
    <AuthProvider>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/conversations/orchestrator" element={<OrchestratorConversationPage />} />
          <Route path="/conversations/agent/:agentId" element={<AgentConversationPage />} />
        </Routes>
      </MemoryRouter>
    </AuthProvider>,
  );
}

describe('conversation modes', () => {
  it('labels the orchestrator conversation as orchestrated', () => {
    renderAt('/conversations/orchestrator');
    expect(screen.getAllByText('Orchestrated').length).toBeGreaterThan(0);
    expect(screen.queryByText('Direct specialist')).not.toBeInTheDocument();
  });

  it('labels a specialist conversation as direct and names the agent', () => {
    renderAt('/conversations/agent/retrieval');
    expect(screen.getAllByText('Direct specialist').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Retrieval Specialist').length).toBeGreaterThan(0);
  });

  it('disables the composer and states the real reason', () => {
    renderAt('/conversations/orchestrator');
    const composer = screen.getByLabelText('Message');
    expect(composer).toBeDisabled();

    // Supabase is unconfigured in tests, so the true reason is a deployment
    // problem, not a missing session. Previously every case collapsed into
    // "sign in and create a workspace", which sent users to re-authenticate
    // against a session that was working.
    expect(screen.getByText(/authentication is not configured/i)).toBeInTheDocument();
    expect(screen.queryByText(/sign in and create a workspace/i)).not.toBeInTheDocument();
  });

  it('never claims that model execution is missing', () => {
    // Regression guard: this copy was true before Phase 3B/3D and is now false.
    renderAt('/conversations/orchestrator');
    expect(screen.queryByText(/no model execution/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/not connected to a model yet/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/not implemented in this phase/i)).not.toBeInTheDocument();
  });

  it('renders no fabricated assistant messages in an empty conversation', () => {
    renderAt('/conversations/agent/memory');
    expect(screen.queryAllByRole('listitem')).toHaveLength(0);
  });

  it('handles an unknown agent id honestly', () => {
    renderAt('/conversations/agent/does-not-exist');
    expect(screen.getByText(/unknown agent/i)).toBeInTheDocument();
  });

  it('shows the orchestrator as available rather than planned', () => {
    renderAt('/conversations/orchestrator');
    expect(screen.queryByText(/planned capability/i)).not.toBeInTheDocument();
  });
});
