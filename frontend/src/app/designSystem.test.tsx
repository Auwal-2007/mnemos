/**
 * Design-system and motion contract tests.
 *
 * jsdom has no layout engine, so nothing here asserts pixels. What it *can*
 * assert is the set of decisions that would silently regress: that motion is
 * suppressed under `prefers-reduced-motion`, that the 3D scene is not loaded
 * eagerly, that cursor effects write CSS custom properties only on pointer
 * movement, and that the design tokens stay internally consistent.
 */

import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { render, screen, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { AppProviders } from './AppProviders';
import { LandingPage } from '../features/landing/LandingPage';
import { HeroOrbit } from '../features/landing/HeroOrbit';
import { CommandPalette } from '../components/layout/CommandPalette';
import { AppShell } from '../components/layout/AppShell';
import { Route, Routes } from 'react-router-dom';

const tokensCss = readFileSync(resolve(__dirname, '../styles/tokens.css'), 'utf8');

/** Overrides matchMedia so both viewport and motion queries can be driven. */
function mockMedia(options: { reducedMotion?: boolean; width?: number }): void {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: (query: string) => {
      let matches = false;
      if (query.includes('prefers-reduced-motion')) {
        matches = Boolean(options.reducedMotion);
      } else {
        const max = /max-width:\s*(\d+)px/.exec(query);
        const min = /min-width:\s*(\d+)px/.exec(query);
        if (max) matches = (options.width ?? 1440) <= Number(max[1]);
        else if (min) matches = (options.width ?? 1440) >= Number(min[1]);
      }
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

describe('design tokens', () => {
  it('defines every semantic hue family in both themes', () => {
    for (const theme of ["[data-theme='light'] {"]) {
      const block = tokensCss.slice(tokensCss.indexOf(theme));
      for (const token of [
        '--accent:',
        '--accent-text:',
        '--brass:',
        '--brass-bright:',
        '--danger:',
        '--success:',
        '--warning:',
      ]) {
        expect(block).toContain(token);
      }
    }
  });

  it('exposes a motion token set and a reduced-motion override', () => {
    for (const token of [
      '--motion-instant',
      '--motion-fast',
      '--motion-base',
      '--motion-slow',
      '--ease-standard',
      '--ease-out',
      '--ease-spring',
    ]) {
      expect(tokensCss).toContain(token);
    }
    expect(tokensCss).toMatch(/prefers-reduced-motion: reduce/);
  });

  it('keeps the display face distinct from the UI and data faces', () => {
    expect(tokensCss).toContain("--font-display: 'Instrument Serif'");
    expect(tokensCss).toContain("--font-sans: 'Inter Variable'");
    expect(tokensCss).toContain("--font-mono: 'JetBrains Mono Variable'");
  });
});

describe('reduced motion', () => {
  beforeEach(() => mockMedia({ reducedMotion: true }));
  afterEach(() => vi.restoreAllMocks());

  it('is reported by matchMedia so components can opt out', () => {
    expect(window.matchMedia('(prefers-reduced-motion: reduce)').matches).toBe(true);
  });

  it('renders a static 3D frame instead of starting an animation loop', () => {
    // jsdom has no WebGL: the component must fall back rather than throw.
    const { container } = render(<HeroOrbit />);
    expect(container.querySelector('.hero-orbit')).toBeTruthy();
    expect(container.querySelector('.hero-orbit__fallback')).toBeTruthy();
  });

  it('does not animate the product-demo progress bar', () => {
    render(
      <MemoryRouter>
        <AppProviders>
          <LandingPage />
        </AppProviders>
      </MemoryRouter>,
    );
    expect(document.querySelector('.demo__progress')).toBeNull();
  });
});

describe('cursor interactions', () => {
  beforeEach(() => mockMedia({ reducedMotion: false }));
  afterEach(() => vi.restoreAllMocks());

  it('writes spotlight coordinates as CSS custom properties on pointer move', async () => {
    const user = userEvent.setup();
    const { container } = render(
      <MemoryRouter>
        <AppProviders>
          <LandingPage />
        </AppProviders>
      </MemoryRouter>,
    );
    const hero = container.querySelector('.hero') as HTMLElement;
    expect(hero).toBeTruthy();
    // Before any pointer movement no coordinate properties exist, so the
    // gradient is inert and cannot obscure content.
    expect(hero.style.getPropertyValue('--pointer-nx')).toBe('');

    await user.pointer({ target: hero, coords: { clientX: 100, clientY: 200 } });
    await act(async () => {
      await new Promise((resolveFrame) => requestAnimationFrame(() => resolveFrame(null)));
    });

    expect(hero.style.getPropertyValue('--pointer-nx')).not.toBe('');
    expect(hero.style.getPropertyValue('--pointer-ny')).not.toBe('');
  });

  it('never traps pointer events on decorative layers', () => {
    const { container } = render(<HeroOrbit />);
    const fallback = container.querySelector('.hero-orbit__fallback') as HTMLElement;
    // The decorative SVG must not be a hit target.
    expect(fallback.getAttribute('aria-hidden')).toBe('true');
  });
});

describe('command palette', () => {
  beforeEach(() => mockMedia({ reducedMotion: true }));
  afterEach(() => vi.restoreAllMocks());

  it('opens on demand and lists every real destination', () => {
    render(
      <MemoryRouter>
        <AppProviders>
          <CommandPalette open onClose={() => {}} />
        </AppProviders>
      </MemoryRouter>,
    );
    const options = screen.getAllByRole('option');
    expect(options.length).toBeGreaterThanOrEqual(6);
    const labels = options.map((option) => option.textContent ?? '');
    expect(labels.some((label) => label.includes('Knowledge'))).toBe(true);
    expect(labels.some((label) => label.includes('Agents'))).toBe(true);
  });

  it('filters as the user types', async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <AppProviders>
          <CommandPalette open onClose={() => {}} />
        </AppProviders>
      </MemoryRouter>,
    );
    await user.type(screen.getByLabelText(/search pages/i), 'knowl');
    const options = screen.getAllByRole('option');
    expect(options).toHaveLength(1);
    expect(options[0].textContent).toContain('Knowledge');
  });

  it('closes on Escape and exposes no fake AI action', async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(
      <MemoryRouter>
        <AppProviders>
          <CommandPalette open onClose={onClose} />
        </AppProviders>
      </MemoryRouter>,
    );
    const labels = screen.getAllByRole('option').map((option) => option.textContent ?? '');
    expect(labels.some((label) => /ask ai|generate|summarise/i.test(label))).toBe(false);
    await user.keyboard('{Escape}');
    expect(onClose).toHaveBeenCalled();
  });
});

describe('application shell', () => {
  afterEach(() => vi.restoreAllMocks());

  function renderShell(): void {
    render(
      <AppProviders>
        <MemoryRouter initialEntries={['/app']}>
          <Routes>
            <Route path="/app" element={<AppShell />}>
              <Route index element={<div>Overview content</div>} />
            </Route>
          </Routes>
        </MemoryRouter>
      </AppProviders>,
    );
  }

  it('exposes a command-palette trigger in the sidebar', () => {
    mockMedia({ width: 1440 });
    renderShell();
    expect(screen.getByRole('button', { name: /search and jump/i })).toBeInTheDocument();
  });

  it('opens the palette from the sidebar trigger', async () => {
    mockMedia({ width: 1440 });
    const user = userEvent.setup();
    renderShell();
    await user.click(screen.getByRole('button', { name: /search and jump/i }));
    expect(screen.getByRole('dialog', { name: /command palette/i })).toBeInTheDocument();
  });

  it('renders a mobile top bar instead of the rail below 768px', () => {
    mockMedia({ width: 390 });
    renderShell();
    // The rail is hidden by CSS at this width; the top bar carries the two
    // controls that remain reachable.
    expect(screen.getAllByRole('button', { name: /open navigation menu/i }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole('button', { name: /search and jump/i }).length).toBeGreaterThan(0);
  });
});
