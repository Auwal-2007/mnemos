import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, api, request } from './client';

function jsonResponse(body: unknown, init: ResponseInit = {}): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json', 'X-Request-ID': 'req-1' },
    ...init,
  });
}

describe('api client', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('returns parsed JSON for successful requests', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ status: 'ok' }));

    const result = await api.get<{ status: string }>('/health');

    expect(result).toEqual({ status: 'ok' });
    expect(fetch).toHaveBeenCalledOnce();
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(String(url)).toContain('/health');
    expect(init?.method).toBe('GET');
  });

  it('sends JSON bodies and content type on POST', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ ok: true }));

    await api.post('/things', { name: 'note' });

    const [, init] = vi.mocked(fetch).mock.calls[0];
    expect(init?.body).toBe(JSON.stringify({ name: 'note' }));
    expect((init?.headers as Record<string, string>)['Content-Type']).toBe('application/json');
  });

  it('attaches a bearer token when provided', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ ok: true }));

    await request('/secure', { accessToken: 'token-123' });

    const [, init] = vi.mocked(fetch).mock.calls[0];
    expect((init?.headers as Record<string, string>).Authorization).toBe('Bearer token-123');
  });

  it('maps the backend error envelope to an ApiError', async () => {
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse(
        { error: { code: 'not_found', message: 'Missing.', request_id: 'rid-9' } },
        { status: 404 },
      ),
    );

    await expect(api.get('/missing')).rejects.toMatchObject({
      name: 'ApiError',
      code: 'not_found',
      status: 404,
      message: 'Missing.',
      requestId: 'rid-9',
    });
  });

  it('classifies validation errors from the backend', async () => {
    vi.mocked(fetch).mockResolvedValue(
      jsonResponse({ error: { code: 'validation_error', message: 'Bad input' } }, { status: 422 }),
    );

    await expect(api.post('/x', {})).rejects.toMatchObject({ code: 'validation_error' });
  });

  it('maps network failures to a retryable ApiError', async () => {
    vi.mocked(fetch).mockRejectedValue(new TypeError('Failed to fetch'));

    const error = await api.get('/health').catch((cause: unknown) => cause);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).code).toBe('network_error');
    expect((error as ApiError).isRetryable).toBe(true);
  });

  it('treats 204 responses as empty bodies', async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(null, { status: 204 }));
    await expect(api.delete('/thing')).resolves.toBeUndefined();
  });

  it('rejects with a server_error for 5xx responses', async () => {
    vi.mocked(fetch).mockResolvedValue(new Response('boom', { status: 500 }));
    await expect(api.get('/health')).rejects.toMatchObject({
      code: 'server_error',
      status: 500,
    });
  });
});
