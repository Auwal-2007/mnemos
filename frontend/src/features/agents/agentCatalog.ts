/**
 * Agent contracts — the four roles the backend actually implements.
 *
 * These are no longer aspirational. `app/services/orchestration.py` plans and
 * delegates across these roles, and `/api/v1/agents/.../ask` executes them with
 * a persisted trace. The `role` field is the exact string the API expects, so a
 * mismatch is a type error rather than a silently ignored request.
 *
 * `availability` stays because a deployment can run without a model provider:
 * in that case the roles exist but every execution degrades, and the UI must be
 * able to say so instead of implying a working assistant.
 */

export type AgentId = 'orchestrator' | 'retrieval' | 'memory' | 'verification';

export type AgentKind = 'orchestrator' | 'specialist';

/**
 * `available` — the role executes.
 * `degraded` — the role exists but its model provider is not configured, so it
 *              reports failure rather than answering.
 */
export type AgentAvailability = 'available' | 'degraded';

import type { AgentRole } from '../../lib/api/types';

export interface AgentContract {
  id: AgentId;
  /** The backend role identifier, sent verbatim to the API. */
  role: AgentRole;
  name: string;
  kind: AgentKind;
  summary: string;
  responsibilities: string[];
  boundaries: string[];
  inputs: string[];
  outputs: string[];
  availability: AgentAvailability;
  /** Short capability tags rendered beside the agent. */
  capabilities: string[];
}

export const AGENT_CATALOG: AgentContract[] = [
  {
    id: 'orchestrator',
    role: 'orchestrator',
    name: 'MNEMOS Orchestrator',
    kind: 'orchestrator',
    summary:
      'The single conversational entry point. Interprets a user request, decides which specialists to consult, and composes a single evidence-aware answer.',
    responsibilities: [
      'Interpret user intent and plan a response strategy',
      'Delegate to specialist agents and merge their findings',
      'Compose one coherent answer with citations to evidence',
      'Escalate to the user when evidence is insufficient or conflicting',
    ],
    boundaries: [
      'Does not write directly to the database',
      'Does not execute arbitrary SQL or code',
      'Does not fabricate sources when none are retrieved',
    ],
    inputs: ['User message', 'Conversation history', 'Specialist agent results'],
    outputs: ['Composed answer', 'Evidence references', 'Follow-up questions'],
    availability: 'available',
    capabilities: ['plan', 'delegate', 'compose'],
  },
  {
    id: 'retrieval',
    role: 'retrieval_specialist',
    name: 'Retrieval Specialist',
    kind: 'specialist',
    summary:
      'Finds the most relevant passages in the personal knowledge base for a given query, ranked and scoped to the requesting user.',
    responsibilities: [
      'Translate a query into search terms and embeddings',
      'Search the knowledge base and rank candidate passages',
      'Return passages with source identifiers for citation',
    ],
    boundaries: [
      'Reads only within the authenticated user’s scope',
      'Never rewrites stored knowledge',
      'Returns nothing rather than inventing matches',
    ],
    inputs: ['Query text', 'User scope', 'Search filters'],
    outputs: ['Ranked passages', 'Source references', 'Relevance scores'],
    availability: 'available',
    capabilities: ['retrieve', 'rank'],
  },
  {
    id: 'memory',
    role: 'memory_specialist',
    name: 'Memory Management Specialist',
    kind: 'specialist',
    summary:
      'Maintains durable knowledge: consolidates notes, tracks revisions and supersession, and keeps prior decisions discoverable.',
    responsibilities: [
      'Propose knowledge entries from conversations and documents',
      'Track revisions and superseded statements',
      'Preserve provenance for every stored assertion',
    ],
    boundaries: [
      'Proposals require user confirmation before becoming authoritative',
      'Never deletes revision history',
      'Writes only through application services',
    ],
    inputs: ['Conversation excerpts', 'User corrections', 'Existing knowledge entries'],
    outputs: ['Proposed entries', 'Revision records', 'Supersession links'],
    availability: 'available',
    capabilities: ['read_memory', 'trace_revisions'],
  },
  {
    id: 'verification',
    role: 'verification_specialist',
    name: 'Evidence Verification Specialist',
    kind: 'specialist',
    summary:
      'Checks whether claims are supported by retrieved evidence, flags conflicts between sources, and reports confidence honestly.',
    responsibilities: [
      'Compare claims against cited passages',
      'Detect contradictions between sources and revisions',
      'Return sufficiency and confidence verdicts',
    ],
    boundaries: [
      'Never upgrades confidence without supporting evidence',
      'Reports insufficiency rather than guessing',
      'Does not modify the knowledge base',
    ],
    inputs: ['Claims', 'Retrieved passages', 'Revision history'],
    outputs: ['Support verdicts', 'Conflict reports', 'Confidence signals'],
    availability: 'available',
    capabilities: ['verify_claims', 'report_support'],
  },
];

export function getAgent(id: string): AgentContract | undefined {
  return AGENT_CATALOG.find((agent) => agent.id === id);
}
