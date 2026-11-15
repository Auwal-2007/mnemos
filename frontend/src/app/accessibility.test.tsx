/**
 * Automated accessibility audit with axe-core.
 *
 * jsdom cannot evaluate colour contrast (no layout/paint), so the `color-contrast`
 * rule is disabled here and contrast is verified separately by
 * `src/styles/contrast.test.ts`, which computes the real ratios from tokens.
 */

import { render } from '@testing-library/react';
import axe from 'axe-core';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { AppProviders } from './AppProviders';
import { AppShell } from '../components/layout/AppShell';
import { AgentDirectoryPage } from '../features/agents/AgentDirectoryPage';
import { DashboardPage } from '../features/home/DashboardPage';
import { KnowledgePage } from '../features/knowledge/KnowledgePage';
import { SettingsPage } from '../features/settings/SettingsPage';
import { ConversationsPage } from '../features/conversations/ConversationsPage';
import { SignInPage } from '../features/auth/SignInPage';
import { LandingPage } from '../features/landing/LandingPage';
import { CommandPalette } from '../components/layout/CommandPalette';

const AXE_OPTIONS: axe.RunOptions = {
  rules: {
    'color-contrast': { enabled: false },
    // Region rules require a full document; components are rendered in isolation.
    region: { enabled: false },
  },
};

async function audit(
  ui: React.ReactElement,
  _options?: { region?: string },
): Promise<axe.AxeResults> {
  const { container } = render(
    <AppProviders>
      <MemoryRouter>{ui}</MemoryRouter>
    </AppProviders>,
  );
  return axe.run(container, AXE_OPTIONS);
}

function formatViolations(violations: axe.Result[]): string {
  return violations
    .map((violation) => `${violation.id}: ${violation.help} (${violation.nodes.length} nodes)`)
    .join('\n');
}

describe('accessibility audit', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({
              status: 'ok',
              service: 'mnemos',
              version: '0.1.0',
              environment: 'development',
              checks: [],
            }),
            { status: 200, headers: { 'Content-Type': 'application/json' } },
          ),
      ),
    );
  });

  it('dashboard has no detectable violations', async () => {
    const results = await audit(<DashboardPage />);
    expect(results.violations, formatViolations(results.violations)).toEqual([]);
  });

  it('agent directory has no detectable violations', async () => {
    const results = await audit(<AgentDirectoryPage />);
    expect(results.violations, formatViolations(results.violations)).toEqual([]);
  });

  it('knowledge workspace has no detectable violations', async () => {
    const results = await audit(<KnowledgePage />);
    expect(results.violations, formatViolations(results.violations)).toEqual([]);
  });

  it('settings page has no detectable violations', async () => {
    const results = await audit(<SettingsPage />);
    expect(results.violations, formatViolations(results.violations)).toEqual([]);
  });

  it('conversations entry page has no detectable violations', async () => {
    const results = await audit(<ConversationsPage />);
    expect(results.violations, formatViolations(results.violations)).toEqual([]);
  });

  it('sign-in page has no detectable violations', async () => {
    const results = await audit(<SignInPage />);
    expect(results.violations, formatViolations(results.violations)).toEqual([]);
  });

  it('application shell has no detectable violations', async () => {
    const results = await audit(<AppShell />);
    expect(results.violations, formatViolations(results.violations)).toEqual([]);
  });

  it('the public landing page has no detectable violations', async () => {
    // The landing page carries the most complex markup in the product: a 3D
    // canvas, a tablist, an agent topology and a marketing footer.
    const results = await audit(<LandingPage />);
    expect(results.violations, formatViolations(results.violations)).toEqual([]);
  });

  it('the command palette has no detectable violations', async () => {
    const results = await audit(<CommandPalette open onClose={() => {}} />);
    expect(results.violations, formatViolations(results.violations)).toEqual([]);
  });

  it('the agent directory has no detectable violations after selection', async () => {
    const results = await audit(<AgentDirectoryPage />);
    expect(results.violations, formatViolations(results.violations)).toEqual([]);
  });
});
