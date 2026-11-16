/**
 * Retrieval API calls (Phase 3A).
 *
 * Retrieval answers a narrower question than asking: "what evidence exists?",
 * with no generation and no answer text. That makes it the honest way to show a
 * user why an answer was or was not possible.
 */

import { api } from './client';
import type { SearchResponse } from './types';

export interface SearchOptions {
  limit?: number;
  candidateCount?: number;
  includeSuperseded?: boolean;
  signal?: AbortSignal;
}

/**
 * Search a workspace's indexed knowledge.
 *
 * `includeSuperseded` is exposed because it changes the question being asked:
 * "what is currently true?" versus "what did we once say?". The UI must label
 * which one it is showing.
 */
export function searchKnowledge(
  accessToken: string,
  workspaceId: string,
  query: string,
  options: SearchOptions = {},
): Promise<SearchResponse> {
  return api.post<SearchResponse>(
    `/knowledge/workspaces/${encodeURIComponent(workspaceId)}/search`,
    {
      query,
      limit: options.limit ?? 10,
      candidate_count: options.candidateCount ?? 30,
      include_superseded: options.includeSuperseded ?? false,
    },
    { accessToken, signal: options.signal, timeoutMs: 60_000 },
  );
}
