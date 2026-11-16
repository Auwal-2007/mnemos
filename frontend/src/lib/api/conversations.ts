/**
 * Conversation API calls (Phase 3B).
 *
 * One module for conversations, messages and grounded answers, because they
 * share a lifecycle: a question is appended to a conversation and produces an
 * answer with evidence attached. Splitting them would mean two places knew the
 * shape of an answer.
 *
 * Every function takes an explicit `accessToken` rather than reaching for one.
 * The token is owned by the auth layer and passed down; nothing in this module
 * stores it.
 */

import { api } from './client';
import type {
  AgentAskResponse,
  AgentRole,
  AnswerDetail,
  AskResponse,
  Conversation,
  ConversationList,
  MessageList,
  VerificationCounts,
  VerificationResult,
} from './types';

export interface AskOptions {
  conversationId?: string | null;
  agentRole?: AgentRole | null;
  limit?: number;
  includeSuperseded?: boolean;
  signal?: AbortSignal;
}

/**
 * Ask a question in a workspace, creating a conversation when none is supplied.
 *
 * The backend decides whether to answer or abstain, and says which in
 * `answer.status`. This module never second-guesses that: an abstention is a
 * result, not an error.
 */
export function askQuestion(
  accessToken: string,
  workspaceId: string,
  question: string,
  options: AskOptions = {},
): Promise<AskResponse> {
  return api.post<AskResponse>(
    `/conversations/workspaces/${encodeURIComponent(workspaceId)}/ask`,
    {
      question,
      conversation_id: options.conversationId ?? null,
      agent_role: options.agentRole ?? null,
      limit: options.limit ?? 10,
      include_superseded: options.includeSuperseded ?? false,
    },
    { accessToken, signal: options.signal, timeoutMs: 120_000 },
  );
}

export function fetchConversations(
  accessToken: string,
  workspaceId: string,
  signal?: AbortSignal,
): Promise<ConversationList> {
  return api.get<ConversationList>(
    `/conversations/workspaces/${encodeURIComponent(workspaceId)}`,
    { accessToken, signal },
  );
}

export function createConversation(
  accessToken: string,
  workspaceId: string,
  title: string,
  agentRole?: AgentRole | null,
): Promise<Conversation> {
  return api.post<Conversation>(`/conversations/workspaces/${encodeURIComponent(workspaceId)}`, {
    title,
    agent_role: agentRole ?? null,
  }, { accessToken });
}

export function fetchConversation(
  accessToken: string,
  conversationId: string,
  signal?: AbortSignal,
): Promise<Conversation> {
  return api.get<Conversation>(`/conversations/${encodeURIComponent(conversationId)}`, {
    accessToken,
    signal,
  });
}

export function fetchMessages(
  accessToken: string,
  conversationId: string,
  signal?: AbortSignal,
): Promise<MessageList> {
  return api.get<MessageList>(
    `/conversations/${encodeURIComponent(conversationId)}/messages`,
    { accessToken, signal },
  );
}

export function fetchAnswer(
  accessToken: string,
  answerId: string,
  signal?: AbortSignal,
): Promise<AnswerDetail> {
  return api.get<AnswerDetail>(`/conversations/answers/${encodeURIComponent(answerId)}`, {
    accessToken,
    signal,
  });
}

// --- verification ----------------------------------------------------------

export interface VerifyOptions {
  method?: 'lexical_overlap' | 'model' | string;
}

/**
 * Verify an answer's claims against the evidence it cites.
 *
 * Kept separate from asking because it can be run later, on a stored answer,
 * with a different method.
 */
export function verifyAnswer(
  accessToken: string,
  answerId: string,
  options: VerifyOptions = {},
): Promise<VerificationResult> {
  return api.post<VerificationResult>(
    `/memory/answers/${encodeURIComponent(answerId)}/verify`,
    { method: options.method ?? 'lexical_overlap' },
    { accessToken, timeoutMs: 120_000 },
  );
}

// --- agents ----------------------------------------------------------------

export interface AgentAskOptions extends AskOptions {
  verify?: boolean;
  method?: string;
  candidateCount?: number;
  maxTokens?: number;
  temperature?: number;
}

/**
 * Ask through the agent orchestrator for a specific workspace.
 *
 * Returns the answer plus the real execution trace, so the UI can show what
 * each specialist actually did rather than a decorative animation.
 */
export function askAgent(
  accessToken: string,
  workspaceId: string,
  question: string,
  options: AgentAskOptions = {},
): Promise<AgentAskResponse> {
  return api.post<AgentAskResponse>(
    `/agents/workspaces/${encodeURIComponent(workspaceId)}/ask`,
    {
      question,
      conversation_id: options.conversationId ?? null,
      verify: options.verify ?? true,
      method: options.method ?? 'lexical_overlap',
      candidate_count: options.candidateCount ?? 30,
      limit: options.limit ?? 10,
      max_tokens: options.maxTokens ?? 1024,
      temperature: options.temperature ?? 0.2,
    },
    { accessToken, signal: options.signal, timeoutMs: 180_000 },
  );
}

export type { VerificationCounts };
