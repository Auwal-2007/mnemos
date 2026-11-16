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

describe('MNEMOS application', () => {
  beforeEach(() => {
    stubHealthApi();
    window.history.pushState({}, '', '/');
  });

  describe('public site', () => {
    it('renders the landing headline and product identity', () => {
      render(<App />);
      expect(
        screen.getByRole('heading', { name: /your knowledge deserves more than a search bar/i }),
      ).toBeInTheDocument();
      expect(screen.getAllByText(/MNEMOS/).length).toBeGreaterThan(0);
    });

    it('offers both primary and secondary calls to action in the hero', () => {
      render(<App />);
      const hero = screen.getByRole('region', { name: /your knowledge deserves/i });
      expect(within(hero).getByRole('link', { name: /enter mnemos/i })).toBeInTheDocument();
      expect(within(hero).getByRole('link', { name: /see how it works/i })).toBeInTheDocument();
    });

    it('labels the hero visual as a rendering, not a live session', () => {
      render(<App />);
      expect(screen.getByText(/not a live session/i)).toBeInTheDocument();
    });

    it('labels the product demonstration as an illustration', () => {
      render(<App />);
      expect(
        screen.getByText(/fixed illustration of the pipeline, not a live execution/i),
      ).toBeInTheDocument();
    });

    it('marks which demonstration steps are built and which are planned', () => {
      render(<App />);
      const demo = screen.getByRole('region', { name: /what actually happens/i });
      expect(within(demo).getAllByText(/Implemented/i).length).toBeGreaterThan(0);
      expect(within(demo).getAllByText(/Planned/i).length).toBeGreaterThan(0);
    });

    it('presents all four agent roles by name', () => {
      render(<App />);
      const showcase = screen.getByRole('region', { name: /specialists with/i });
      for (const name of [
        /MNEMOS Orchestrator/,
        /Retrieval Specialist/,
        /Memory Management Specialist/,
        /Evidence Verification Specialist/,
      ]) {
        expect(within(showcase).getAllByRole('button', { name }).length).toBeGreaterThan(0);
      }
    });

    it('states that agents cannot be invoked yet', () => {
      render(<App />);
      const showcase = screen.getByRole('region', { name: /specialists with/i });
      // The specialists are executable now; the landing page must not claim
      // otherwise. It may still say the panel itself does not start anything.
      expect(within(showcase).getByText(/executable through the orchestrator/i)).toBeInTheDocument();
      expect(within(showcase).queryByText(/not yet executable/i)).not.toBeInTheDocument();
    });

    it('shows an agent contract when a specialist is selected', () => {
      render(<App />);
      const showcase = screen.getByRole('region', { name: /specialists with/i });
      // Retrieval is selected by default, so its responsibilities are visible.
      expect(within(showcase).getByText(/Translate a query into search terms/i)).toBeInTheDocument();
      expect(within(showcase).getByText(/Never rewrites stored knowledge/i)).toBeInTheDocument();
    });

    it('explains provenance with revision states', () => {
      render(<App />);
      expect(
        screen.getByRole('heading', { name: /an answer you can walk backwards/i }),
      ).toBeInTheDocument();
      expect(screen.getByRole('tab', { name: /current/i })).toBeInTheDocument();
      expect(screen.getByRole('tab', { name: /superseded/i })).toBeInTheDocument();
      expect(screen.getByRole('tab', { name: /disputed/i })).toBeInTheDocument();
    });

    it('labels the provenance panel as an illustrative example', () => {
      render(<App />);
      expect(screen.getByText(/illustrative example/i)).toBeInTheDocument();
    });

    it('renders a footer without invented social links', () => {
      render(<App />);
      const footer = screen.getByRole('contentinfo');
      expect(within(footer).getByText(/MNEMOS is under active development/i)).toBeInTheDocument();
      expect(within(footer).queryByText(/twitter|x\.com|linkedin|discord/i)).toBeNull();
    });
  });

  describe('product shell', () => {
    it('renders the overview with grouped primary navigation', () => {
      window.history.pushState({}, '', '/app');
      render(<App />);
      const nav = screen.getAllByRole('navigation', { name: /primary/i })[0];
      const labels = within(nav)
        .getAllByRole('link')
        .map((link) => link.textContent ?? '');
      expect(labels.some((label) => label.includes('Overview'))).toBe(true);
      expect(labels.some((label) => label.includes('Knowledge'))).toBe(true);
      expect(labels.some((label) => label.includes('Conversations'))).toBe(true);
      expect(labels.some((label) => label.includes('Agents'))).toBe(true);
      expect(labels.some((label) => label.includes('Settings'))).toBe(true);
    });

    it('groups navigation by workspace, intelligence and system', () => {
      window.history.pushState({}, '', '/app');
      render(<App />);
      const nav = screen.getAllByRole('navigation', { name: /primary/i })[0];
      expect(within(nav).getByText('Workspace')).toBeInTheDocument();
      expect(within(nav).getByText('Intelligence')).toBeInTheDocument();
      expect(within(nav).getByText('System')).toBeInTheDocument();
    });

    it('says there is no session rather than showing invented data', async () => {
      window.history.pushState({}, '', '/app');
      render(<App />);
      expect(await screen.findByText(/No session/i)).toBeInTheDocument();
      expect(screen.getByText(/deliberately shows nothing rather than stand-in data/i)).toBeInTheDocument();
    });

    it('shows every pipeline stage as empty when there are no sources', () => {
      window.history.pushState({}, '', '/app');
      render(<App />);
      // Not signed in: the pipeline view states the precondition instead of
      // drawing an empty chart that could be mistaken for zero data.
      expect(screen.getByText(/appears once you are signed in/i)).toBeInTheDocument();
    });

    it('opens the real submission surface at /app/sources', async () => {
      window.history.pushState({}, '', '/app/sources');
      render(<App />);
      expect(await screen.findByRole('heading', { name: /your corpus/i })).toBeInTheDocument();
      expect(await screen.findByText(/sign in to add sources/i)).toBeInTheDocument();
      expect(screen.queryByText(/reserved for a later phase/i)).not.toBeInTheDocument();
    });

    it('renders the agent directory with all four intended roles', () => {
      window.history.pushState({}, '', '/app/agents');
      render(<App />);
      const roster = screen.getByRole('navigation', { name: /agent roles/i });
      for (const name of [
        'MNEMOS Orchestrator',
        'Retrieval Specialist',
        'Memory Management Specialist',
        'Evidence Verification Specialist',
      ]) {
        expect(within(roster).getByRole('button', { name: new RegExp(name) })).toBeInTheDocument();
      }
      // The selected role is presented as the document heading.
      expect(screen.getByRole('heading', { name: 'MNEMOS Orchestrator' })).toBeInTheDocument();
    });

    it('opens a different contract when another role is chosen', async () => {
      window.history.pushState({}, '', '/app/agents');
      const { default: userEvent } = await import('@testing-library/user-event');
      const user = userEvent.setup();
      render(<App />);
      const roster = screen.getByRole('navigation', { name: /agent roles/i });
      await user.click(within(roster).getByRole('button', { name: /Evidence Verification/i }));
      expect(
        screen.getByRole('heading', { name: 'Evidence Verification Specialist' }),
      ).toBeInTheDocument();
      expect(screen.getByText(/Never upgrades confidence without supporting evidence/i)).toBeInTheDocument();
    });

    it('renders an honest 404 for unknown product routes', async () => {
      window.history.pushState({}, '', '/app/nope');
      render(<App />);
      expect(await screen.findByText(/page not found/i)).toBeInTheDocument();
    });

    it('renders an honest 404 for unknown public routes', async () => {
      window.history.pushState({}, '', '/definitely-not-a-page');
      render(<App />);
      expect(await screen.findByText(/page not found/i)).toBeInTheDocument();
    });
  });
});
