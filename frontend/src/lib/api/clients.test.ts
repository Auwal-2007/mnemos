import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from './client';
import { askQuestion, fetchMessages, verifyAnswer } from './conversations';
import { searchKnowledge } from './retrieval';
import {
  applyCorrection,
  detectConflicts,
  proposeCorrection,
  resolveConflict,
  reviewCorrection,
} from './memory';
import { fetchOrchestration } from './agents';

/**
 * Contract tests for the Phase 3 API clients.
 *
 * These assert the request the client sends — path, method, body shape — because
 * a field renamed on the server otherwise surfaces as a silently ignored option
 * rather than an error. They do not assert response handling in depth; that is
 * covered by the component tests, which render real responses.
 */

interface Call {
  url: string;
  method: string;
  body: unknown;
  headers: Record<string, string>;
}

const calls: Call[] = [];

function jsonResponse(payload: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: new Headers({ 'Content-Type': 'application/json' }),
    text: () => Promise.resolve(JSON.stringify(payload)),
  } as unknown as Response;
}

beforeEach(() => {
  calls.length = 0;
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string, init: RequestInit) => {
      calls.push({
        url,
        method: init.method ?? 'GET',
        body: init.body ? JSON.parse(String(init.body)) : undefined,
        headers: (init.headers ?? {}) as Record<string, string>,
      });
      return Promise.resolve(jsonResponse({ ok: true }));
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('conversation client', () => {
  it('asks with the documented payload and no conversation id on a new thread', async () => {
    await askQuestion('token', 'ws-1', 'What is the fee?');
    expect(calls).toHaveLength(1);
    expect(calls[0].url).toContain('/conversations/workspaces/ws-1/ask');
    expect(calls[0].method).toBe('POST');
    expect(calls[0].body).toEqual({
      question: 'What is the fee?',
      conversation_id: null,
      agent_role: null,
      limit: 10,
      include_superseded: false,
    });
  });

  it('continues a thread and opts into history when asked', async () => {
    await askQuestion('token', 'ws-1', 'And before that?', {
      conversationId: 'conv-9',
      includeSuperseded: true,
      limit: 5,
    });
    expect(calls[0].body).toMatchObject({
      conversation_id: 'conv-9',
      include_superseded: true,
      limit: 5,
    });
  });

  it('sends the bearer token rather than relying on cookies', async () => {
    await fetchMessages('secret-token', 'conv-1');
    expect(calls[0].headers.Authorization).toBe('Bearer secret-token');
  });

  it('defaults verification to the deterministic lexical method', async () => {
    await verifyAnswer('token', 'ans-1');
    expect(calls[0].url).toContain('/memory/answers/ans-1/verify');
    expect(calls[0].body).toEqual({ method: 'lexical_overlap' });
  });

  it('encodes identifiers so a stray slash cannot escape the path', async () => {
    await fetchMessages('token', 'a/b');
    expect(calls[0].url).toContain('/conversations/a%2Fb/messages');
  });
});

describe('retrieval client', () => {
  it('searches with the documented payload', async () => {
    await searchKnowledge('token', 'ws-1', 'passport validity');
    expect(calls[0].url).toContain('/knowledge/workspaces/ws-1/search');
    expect(calls[0].body).toEqual({
      query: 'passport validity',
      limit: 10,
      candidate_count: 30,
      include_superseded: false,
    });
  });
});

describe('memory client', () => {
  it('proposes a correction with its provenance target', async () => {
    await proposeCorrection('token', 'ws-1', {
      provenanceId: 'prov-4',
      correctedText: 'The fee is 120 USD.',
      rationale: 'The notice was updated.',
    });
    expect(calls[0].url).toContain('/memory/workspaces/ws-1/corrections');
    expect(calls[0].body).toEqual({
      provenance_id: 'prov-4',
      corrected_text: 'The fee is 120 USD.',
      rationale: 'The notice was updated.',
    });
  });

  it('sends a null rationale rather than omitting the key', async () => {
    await proposeCorrection('token', 'ws-1', { provenanceId: 'p', correctedText: 'x' });
    expect(calls[0].body).toMatchObject({ rationale: null });
  });

  it('reviews, applies and resolves through distinct endpoints', async () => {
    await reviewCorrection('token', 'corr-1', true, 'Checked against the notice');
    await applyCorrection('token', 'corr-1');
    await resolveConflict('token', 'conf-1', false, 'Bulletin supersedes');

    expect(calls[0].url).toContain('/memory/corrections/corr-1/review');
    expect(calls[0].body).toEqual({ approve: true, note: 'Checked against the notice' });
    expect(calls[1].url).toContain('/memory/corrections/corr-1/apply');
    expect(calls[2].url).toContain('/memory/conflicts/conf-1/resolve');
    expect(calls[2].body).toEqual({ dismiss: false, note: 'Bulletin supersedes' });
  });

  it('detection is a POST because it writes conflict rows', async () => {
    await detectConflicts('token', 'ws-1');
    expect(calls[0].method).toBe('POST');
    expect(calls[0].url).toContain('/memory/workspaces/ws-1/conflicts/detect');
  });
});

describe('agent client', () => {
  it('reads a recorded orchestration rather than replaying it locally', async () => {
    await fetchOrchestration('token', 'orch-7');
    expect(calls[0].url).toContain('/agents/orchestrations/orch-7');
    expect(calls[0].method).toBe('GET');
  });
});

describe('error normalisation', () => {
  it('maps a server error envelope to a typed ApiError', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          jsonResponse(
            { error: { code: 'forbidden', message: 'You do not have access.', request_id: 'req-1' } },
            403,
          ),
        ),
      ),
    );
    await expect(fetchMessages('token', 'conv-1')).rejects.toBeInstanceOf(ApiError);
    await expect(fetchMessages('token', 'conv-1')).rejects.toMatchObject({
      code: 'forbidden',
      status: 403,
      requestId: 'req-1',
      isRetryable: false,
    });
  });

  it('treats a 5xx as retryable and a 4xx as not', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(jsonResponse({}, 503))));
    const serverError = await fetchMessages('token', 'c').catch((error: ApiError) => error);
    expect((serverError as ApiError).isRetryable).toBe(true);
  });
});
