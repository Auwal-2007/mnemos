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
import { HomePage } from '../features/home/HomePage';
import { KnowledgePage } from '../features/knowledge/KnowledgePage';
import { SettingsPage } from '../features/settings/SettingsPage';
import { ConversationsPage } from '../features/conversations/ConversationsPage';
import { SignInPage } from '../features/auth/SignInPage';

const AXE_OPTIONS: axe.RunOptions = {
  rules: {
    'color-contrast': { enabled: false },
    // Region rules require a full document; components are rendered in isolation.
    region: { enabled: false },
  },
};

async function audit(ui: React.ReactElement): Promise<axe.AxeResults> {
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

  it('home page has no detectable violations', async () => {
    const results = await audit(<HomePage />);
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
});
