import { render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { App } from './App';

function stubHealthApi(): void {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/health')) {
        return new Response(
          JSON.stringify({
            status: 'ok',
            service: 'mnemos',
            version: '0.1.0',
            environment: 'development',
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        );
      }
      if (url.includes('/ready')) {
        return new Response(
          JSON.stringify({
            status: 'ready',
            checks: [
              { name: 'supabase', configured: false, required: false },
              { name: 'supabase_auth', configured: false, required: false },
              { name: 'openrouter', configured: false, required: false },
            ],
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        );
      }
      return new Response('not found', { status: 404 });
    }),
  );
}

describe('MNEMOS application shell', () => {
  beforeEach(() => {
    stubHealthApi();
    window.history.pushState({}, '', '/');
  });

  it('renders the home page with product identity', async () => {
    render(<App />);

    expect(
      screen.getByRole('heading', {
        name: /personal knowledge system that shows its work/i,
      }),
    ).toBeInTheDocument();
    expect(await screen.findByText(/v0\.1\.0/)).toBeInTheDocument();
  });

  it('shows all six primary navigation destinations', () => {
    render(<App />);
    const nav = screen.getAllByRole('navigation', { name: /primary/i })[0];
    const labels = within(nav)
      .getAllByRole('link')
      .map((link) => link.textContent ?? '');
    expect(labels.some((label) => label.includes('Home'))).toBe(true);
    expect(labels.some((label) => label.includes('Knowledge Workspace'))).toBe(true);
    expect(labels.some((label) => label.includes('Conversations'))).toBe(true);
    expect(labels.some((label) => label.includes('Agents'))).toBe(true);
    expect(labels.some((label) => label.includes('Sources & Evidence'))).toBe(true);
    expect(labels.some((label) => label.includes('Settings'))).toBe(true);
  });

  it('opens the real submission surface at /sources', async () => {
    window.history.pushState({}, '', '/sources');
    render(<App />);
    // The sources route now hosts the working ingestion surface, so it must
    // show real submission controls rather than a "planned" placeholder.
    expect(await screen.findByRole('heading', { name: /your corpus/i })).toBeInTheDocument();
    // Without a session there is no workspace, so the page must say so rather
    // than showing an upload control that could not work.
    expect(await screen.findByText(/sign in to add sources/i)).toBeInTheDocument();
    expect(screen.queryByText(/reserved for a later phase/i)).not.toBeInTheDocument();
  });

  it('renders the agent directory with all four intended roles', () => {
    window.history.pushState({}, '', '/agents');
    render(<App />);
    expect(screen.getByRole('heading', { name: 'MNEMOS Orchestrator' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Retrieval Specialist' })).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: 'Memory Management Specialist' }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: 'Evidence Verification Specialist' }),
    ).toBeInTheDocument();
  });

  it('renders an honest 404 for unknown routes', async () => {
    window.history.pushState({}, '', '/nope');
    render(<App />);
    expect(await screen.findByText(/page not found/i)).toBeInTheDocument();
  });
});
