/**
 * Agent contracts — presentation-only registry.
 *
 * These entries describe intended responsibility and boundaries. They are
 * NOT operational AI capabilities: no model is called and no orchestration
 * exists yet (see docs/agents/agent-contracts.md).
 */

export type AgentId = 'orchestrator' | 'retrieval' | 'memory' | 'verification';

export type AgentKind = 'orchestrator' | 'specialist';

export type AgentAvailability = 'planned';

export interface AgentContract {
  id: AgentId;
  name: string;
  kind: AgentKind;
  summary: string;
  responsibilities: string[];
  boundaries: string[];
  inputs: string[];
  outputs: string[];
  availability: AgentAvailability;
  /** Which phase is expected implement this agent. */
  targetPhase: string;
}

export const AGENT_CATALOG: AgentContract[] = [
  {
    id: 'orchestrator',
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
    availability: 'planned',
    targetPhase: 'Phase 3',
  },
  {
    id: 'retrieval',
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
    availability: 'planned',
    targetPhase: 'Phase 2',
  },
  {
    id: 'memory',
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
    availability: 'planned',
    targetPhase: 'Phase 3',
  },
  {
    id: 'verification',
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
    availability: 'planned',
    targetPhase: 'Phase 4',
  },
];

export function getAgent(id: string): AgentContract | undefined {
  return AGENT_CATALOG.find((agent) => agent.id === id);
}
