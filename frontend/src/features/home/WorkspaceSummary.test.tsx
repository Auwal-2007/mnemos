import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { WorkspaceSummary } from './WorkspaceSummary';

// The hook is mocked so each state can be asserted deterministically.
const mockUseWorkspaces = vi.fn();
vi.mock('../../lib/api/useWorkspaces', () => ({
  useWorkspaces: () => mockUseWorkspaces(),
}));

function renderSummary(): void {
  render(
    <MemoryRouter>
      <WorkspaceSummary />
    </MemoryRouter>,
  );
}

function state(overrides: Record<string, unknown>): Record<string, unknown> {
  return {
    data: null,
    error: null,
    isLoading: false,
    reload: vi.fn(),
    needsAuth: false,
    unconfigured: false,
    ...overrides,
  };
}

describe('WorkspaceSummary', () => {
  it('explains when Supabase is not configured', () => {
    mockUseWorkspaces.mockReturnValue(state({ unconfigured: true }));
    renderSummary();
    expect(screen.getByText(/data layer not configured/i)).toBeInTheDocument();
  });

  it('asks anonymous visitors to sign in rather than showing data', () => {
    mockUseWorkspaces.mockReturnValue(state({ needsAuth: true }));
    renderSummary();
    expect(screen.getByText(/sign in to see your workspaces/i)).toBeInTheDocument();
    expect(screen.queryByRole('list')).not.toBeInTheDocument();
  });

  it('shows a loading state while fetching', () => {
    mockUseWorkspaces.mockReturnValue(state({ isLoading: true }));
    renderSummary();
    expect(screen.getAllByText(/loading workspaces/i).length).toBeGreaterThan(0);
  });

  it('shows a retryable error state', () => {
    mockUseWorkspaces.mockReturnValue(state({ error: 'Network unavailable' }));
    renderSummary();
    expect(screen.getByRole('alert')).toHaveTextContent(/network unavailable/i);
    expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument();
  });

  it('shows an honest empty state', () => {
    mockUseWorkspaces.mockReturnValue(state({ data: [] }));
    renderSummary();
    expect(screen.getByText(/no workspaces yet/i)).toBeInTheDocument();
  });

  it('renders real workspaces when they exist', () => {
    mockUseWorkspaces.mockReturnValue(
      state({
        data: [
          {
            id: 'ws-1',
            owner_id: '11111111-1111-4111-8111-111111111111',
            name: 'Personal',
            slug: 'personal',
            description: null,
            created_at: '2026-01-01T00:00:00Z',
            updated_at: '2026-01-01T00:00:00Z',
          },
        ],
      }),
    );
    renderSummary();
    expect(screen.getByText('Personal')).toBeInTheDocument();
    expect(screen.getByText(/11111111/)).toBeInTheDocument();
  });
});
