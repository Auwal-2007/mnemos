import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  createWorkspace,
  fetchPreferences,
  fetchProfile,
  fetchWorkspaceMembers,
  fetchWorkspaces,
  updatePreferences,
} from './workspaces';

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('workspace API calls', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('sends the bearer token on every request', async () => {
    vi.mocked(fetch).mockImplementation(async () => json([]));
    await fetchWorkspaces('token-abc');
    await fetchProfile('token-abc');
    await fetchPreferences('token-abc');

    for (const call of vi.mocked(fetch).mock.calls) {
      const headers = call[1]?.headers as Record<string, string>;
      expect(headers.Authorization).toBe('Bearer token-abc');
    }
  });

  it('requests the documented endpoints', async () => {
    vi.mocked(fetch).mockImplementation(async () => json([]));
    await fetchWorkspaces('t');
    await fetchProfile('t');
    await fetchPreferences('t');
    await fetchWorkspaceMembers('t', 'ws-1');

    const urls = vi.mocked(fetch).mock.calls.map((call) => String(call[0]));
    expect(urls.some((url) => url.endsWith('/workspaces'))).toBe(true);
    expect(urls.some((url) => url.endsWith('/me'))).toBe(true);
    expect(urls.some((url) => url.endsWith('/me/preferences'))).toBe(true);
    expect(urls.some((url) => url.endsWith('/workspaces/ws-1/members'))).toBe(true);
  });

  it('posts a workspace payload', async () => {
    vi.mocked(fetch).mockResolvedValue(json({ id: 'ws-2' }, 201));
    await createWorkspace('t', { name: 'Work', slug: 'work' });
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(String(url)).toContain('/workspaces');
    expect(init?.method).toBe('POST');
    expect(init?.body).toBe(JSON.stringify({ name: 'Work', slug: 'work' }));
  });

  it('surfaces backend authorization failures', async () => {
    vi.mocked(fetch).mockResolvedValue(
      json({ error: { code: 'forbidden', message: 'You do not have access.' } }, 403),
    );
    await expect(fetchWorkspaces('t')).rejects.toMatchObject({ code: 'forbidden', status: 403 });
  });

  it('sends the theme when updating preferences', async () => {
    vi.mocked(fetch).mockResolvedValue(json({ theme: 'dark' }));
    await updatePreferences('t', 'dark');
    const [, init] = vi.mocked(fetch).mock.calls[0];
    expect(init?.body).toBe(JSON.stringify({ theme: 'dark' }));
  });
});
