import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { AgentConversationPage } from './AgentConversationPage';
import { OrchestratorConversationPage } from './OrchestratorConversationPage';

function renderAt(path: string): void {
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/conversations/orchestrator" element={<OrchestratorConversationPage />} />
        <Route path="/conversations/agent/:agentId" element={<AgentConversationPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('conversation modes', () => {
  it('labels the orchestrator conversation as orchestrated', () => {
    renderAt('/conversations/orchestrator');
    // Mode badge in the conversation header (the metadata panel also names it).
    expect(screen.getAllByText('Orchestrated').length).toBeGreaterThan(0);
    expect(screen.queryByText('Direct specialist')).not.toBeInTheDocument();
  });

  it('labels a specialist conversation as direct and names the agent', () => {
    renderAt('/conversations/agent/retrieval');
    expect(screen.getAllByText('Direct specialist').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Retrieval Specialist').length).toBeGreaterThan(0);
  });

  it('disables the composer with an explicit reason in both modes', () => {
    renderAt('/conversations/orchestrator');
    expect(screen.getByLabelText('Message')).toBeDisabled();
    expect(screen.getByText(/no model execution/i)).toBeInTheDocument();
  });

  it('renders no fabricated assistant messages in an empty conversation', () => {
    renderAt('/conversations/agent/memory');
    expect(screen.queryAllByRole('listitem')).toHaveLength(0);
    expect(screen.getByText(/not connected to a model yet/i)).toBeInTheDocument();
  });

  it('handles an unknown agent id honestly', () => {
    renderAt('/conversations/agent/does-not-exist');
    expect(screen.getByText(/unknown agent/i)).toBeInTheDocument();
  });
});
