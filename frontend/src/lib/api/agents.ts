/**
 * Agent and orchestration API calls (Phase 3D).
 *
 * Two distinct surfaces:
 *
 *  * `askAgent` asks through the orchestrator, which plans and delegates.
 *  * the orchestration readers expose the recorded trace of what it did.
 *
 * The trace is read back from persisted database rows, not reconstructed in the
 * browser. That distinction matters: a replayed animation would look identical
 * while telling the user nothing true about what happened.
 */

import { api } from './client';
import type { OrchestrationDetail, OrchestrationList } from './types';

export function fetchOrchestration(
  accessToken: string,
  orchestrationId: string,
  signal?: AbortSignal,
): Promise<OrchestrationDetail> {
  return api.get<OrchestrationDetail>(
    `/agents/orchestrations/${encodeURIComponent(orchestrationId)}`,
    { accessToken, signal },
  );
}

export function fetchOrchestrations(
  accessToken: string,
  workspaceId: string,
  signal?: AbortSignal,
): Promise<OrchestrationList> {
  return api.get<OrchestrationList>(
    `/agents/workspaces/${encodeURIComponent(workspaceId)}/orchestrations`,
    { accessToken, signal },
  );
}

/**
 * The four built-in roles and what each is allowed to do.
 *
 * Static because it describes the deployed architecture, not runtime state.
 * Kept beside the API calls so the UI cannot advertise a specialist the backend
 * does not have.
 */
export interface AgentDescriptor {
  role: string;
  name: string;
  purpose: string;
  capabilities: string[];
}

export const AGENT_ROLES: AgentDescriptor[] = [
  {
    role: 'orchestrator',
    name: 'MNEMOS Orchestrator',
    purpose:
      'Plans a request, delegates to specialists in order, and assembles a single grounded answer.',
    capabilities: ['plan', 'delegate', 'synthesise'],
  },
  {
    role: 'retrieval_specialist',
    name: 'Retrieval Specialist',
    purpose: 'Finds the passages that bear on a question, ranked and with provenance.',
    capabilities: ['retrieve', 'rank'],
  },
  {
    role: 'memory_specialist',
    name: 'Memory Management Specialist',
    purpose: 'Tracks revisions, supersession and conflicts so history is not lost.',
    capabilities: ['read_memory', 'trace_revisions'],
  },
  {
    role: 'verification_specialist',
    name: 'Evidence Verification Specialist',
    purpose: 'Checks each claim against the evidence it cites and reports what it cannot support.',
    capabilities: ['verify_claims', 'report_support'],
  },
];
