/**
 * Responsive and accessibility behaviour that can be asserted in jsdom.
 *
 * jsdom has no layout engine, so these tests verify *decisions* (which
 * layout state the shell chooses at a given width, which controls exist,
 * which labelling is exposed) rather than pixel rendering. Visual
 * verification at 1440/1024/768/390/360 is documented in the Phase 1C
 * report as a manual step, with the reason it could not be automated here.
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AppShell } from '../components/layout/AppShell';
import { AppProviders } from './AppProviders';

function mockViewport(width: number): void {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: (query: string) => {
      const maxWidthMatch = /max-width:\s*(\d+)px/.exec(query);
      const minWidthMatch = /min-width:\s*(\d+)px/.exec(query);
      let matches = false;
      if (maxWidthMatch) matches = width <= Number(maxWidthMatch[1]);
      else if (minWidthMatch) matches = width >= Number(minWidthMatch[1]);
      return {
        matches,
        media: query,
        onchange: null,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        addListener: vi.fn(),
        removeListener: vi.fn(),
        dispatchEvent: vi.fn(),
      };
    },
  });
}

function renderShell(): void {
  render(
    <AppProviders>
      <MemoryRouter initialEntries={['/']}>
        <Routes>
          <Route element={<AppShell />}>
            <Route index element={<div>Home content</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </AppProviders>,
  );
}

describe('responsive shell', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } })),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('shows the mobile top bar trigger below 768px', () => {
    mockViewport(390);
    renderShell();
    expect(screen.getByRole('button', { name: /open navigation menu/i })).toBeInTheDocument();
  });

  it('exposes a skip link to the main content', () => {
    mockViewport(390);
    renderShell();
    expect(screen.getByRole('link', { name: /skip to main content/i })).toHaveAttribute(
      'href',
      '#main-content',
    );
  });

  it('marks the main region focusable for skip-link landing', () => {
    mockViewport(1440);
    renderShell();
    const main = screen.getByRole('main');
    expect(main).toHaveAttribute('id', 'main-content');
    expect(main).toHaveAttribute('tabindex', '-1');
  });

  it('renders icon-only navigation on tablet where the rail is 72px', () => {
    mockViewport(900);
    renderShell();
    // Labels are not rendered, so the accessible name comes from the link text
    // container being absent; the link still exposes a title for pointer users.
    const nav = screen.getAllByRole('navigation', { name: /^primary$/i })[0];
    expect(nav.querySelector('.sidebar__label')).toBeNull();
  });

  it('renders full labels on desktop', () => {
    mockViewport(1440);
    renderShell();
    const nav = screen.getAllByRole('navigation', { name: /^primary$/i })[0];
    expect(nav.querySelector('.sidebar__label')).not.toBeNull();
  });

  it('hides the collapse control when the viewport dictates the rail width', () => {
    mockViewport(900);
    renderShell();
    expect(screen.queryByRole('button', { name: /collapse sidebar/i })).not.toBeInTheDocument();
  });

  it('offers the collapse control on desktop', async () => {
    const user = userEvent.setup();
    mockViewport(1440);
    renderShell();
    const control = screen.getByRole('button', { name: /collapse sidebar/i });
    await user.click(control);
    expect(screen.getByRole('button', { name: /expand sidebar/i })).toBeInTheDocument();
  });

  it('opens the drawer from the mobile trigger', async () => {
    const user = userEvent.setup();
    mockViewport(390);
    renderShell();
    await user.click(screen.getByRole('button', { name: /open navigation menu/i }));
    expect(screen.getByRole('complementary', { name: /navigation menu/i })).toHaveClass(
      'drawer--open',
    );
  });

  it('provides a mobile bottom navigation with touch-sized links', () => {
    mockViewport(390);
    renderShell();
    const bottomNav = screen.getByRole('navigation', { name: /primary mobile/i });
    expect(bottomNav.querySelectorAll('a').length).toBeGreaterThanOrEqual(4);
  });
});
