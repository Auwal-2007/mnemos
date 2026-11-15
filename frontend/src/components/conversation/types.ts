import type { AgentId } from '../../features/agents/agentCatalog';

/** Mode A: the user talks to the orchestrator, which may consult specialists. */
export type ConversationMode = 'orchestrated';
/** Mode B: the user talks directly to one specialist. */
export type DirectConversationMode = 'direct';

export type ConversationKind = ConversationMode | DirectConversationMode;

export type MessageAuthor = 'user' | 'assistant' | 'system';

export interface EvidenceRef {
  id: string;
  sourceTitle: string;
  locator?: string;
}

export interface ChatMessage {
  id: string;
  author: MessageAuthor;
  /** For assistant messages: which agent produced it (orchestrator by default). */
  agentId?: AgentId;
  content: string;
  createdAt: string;
  evidence?: EvidenceRef[];
  /** Marks a message that could not be produced (no fabricated answers). */
  status?: 'complete' | 'error' | 'pending';
}

export interface ConversationIdentity {
  kind: ConversationKind;
  /** Present for direct conversations. */
  agentId?: AgentId;
  title: string;
  subtitle: string;
}
