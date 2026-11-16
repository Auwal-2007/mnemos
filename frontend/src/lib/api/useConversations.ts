/**
 * Conversation state hooks.
 *
 * These mirror the shape of `useSources`: a small explicit state object with
 * loading, error and an honest "needs auth / needs workspace" flag. No sample
 * data is ever inserted — an empty conversation renders as empty.
 *
 * The ask hook deliberately keeps the last answer's evidence. The UI needs it to
 * render the EvidencePanel, and re-fetching it would risk showing evidence from
 * a different answer than the text on screen.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { useAuth } from '../auth';
import { ApiError, toErrorMessage } from './client';
import {
  askQuestion,
  createConversation,
  fetchConversations,
  fetchMessages,
  type AskOptions,
} from './conversations';
import type { Answer, AskResponse, Conversation, Message } from './types';

export interface ConversationsState {
  conversations: Conversation[];
  error: string | null;
  isLoading: boolean;
  reload: () => void;
}

export function useConversations(workspaceId: string | null): ConversationsState {
  const { accessToken } = useAuth();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(Boolean(workspaceId && accessToken));
  const [reloadToken, setReloadToken] = useState(0);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    if (!workspaceId || !accessToken) {
      setConversations([]);
      setIsLoading(false);
      setError(null);
      return;
    }
    const controller = new AbortController();
    setIsLoading(true);
    setError(null);

    fetchConversations(accessToken, workspaceId, controller.signal)
      .then((list) => {
        if (mounted.current && !controller.signal.aborted) setConversations(list.items);
      })
      .catch((cause: unknown) => {
        if (controller.signal.aborted) return;
        if (mounted.current) setError(toErrorMessage(cause));
      })
      .finally(() => {
        if (mounted.current && !controller.signal.aborted) setIsLoading(false);
      });

    return () => controller.abort();
  }, [workspaceId, accessToken, reloadToken]);

  const reload = useCallback(() => setReloadToken((token) => token + 1), []);
  return { conversations, error, isLoading, reload };
}

export interface MessagesState {
  messages: Message[];
  error: string | null;
  isLoading: boolean;
  /** The answer produced by the most recent ask, with its evidence. */
  lastAnswer: Answer | null;
  /** True while a question is in flight. */
  isAsking: boolean;
  /** Set when the last ask failed. Cleared on retry. */
  askError: string | null;
  /** Set when a failed ask is worth retrying (network, timeout, 5xx). */
  canRetry: boolean;
  /**
   * Ask a question.
   *
   * Resolves with the full backend response, not just the answer, because the
   * caller needs `conversation_id` to continue the thread the server created.
   */
  ask: (question: string, options?: AskOptions) => Promise<AskResponse | null>;
  retry: () => Promise<AskResponse | null>;
}

export function useConversationMessages(
  workspaceId: string | null,
  conversationId: string | null,
): MessagesState {
  const { accessToken } = useAuth();
  const [messages, setMessages] = useState<Message[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(Boolean(conversationId && accessToken));
  const [lastAnswer, setLastAnswer] = useState<Answer | null>(null);
  const [isAsking, setIsAsking] = useState(false);
  const [askError, setAskError] = useState<string | null>(null);
  const [canRetry, setCanRetry] = useState(false);
  const lastQuestion = useRef<{ question: string; options: AskOptions; conversationId: string | null } | null>(
    null,
  );
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  // Load history whenever the selected conversation changes.
  useEffect(() => {
    if (!conversationId || !accessToken) {
      setMessages([]);
      setIsLoading(false);
      setError(null);
      return;
    }
    const controller = new AbortController();
    setIsLoading(true);
    setError(null);

    fetchMessages(accessToken, conversationId, controller.signal)
      .then((list) => {
        if (mounted.current && !controller.signal.aborted) setMessages(list.items);
      })
      .catch((cause: unknown) => {
        if (controller.signal.aborted) return;
        if (mounted.current) setError(toErrorMessage(cause));
      })
      .finally(() => {
        if (mounted.current && !controller.signal.aborted) setIsLoading(false);
      });

    return () => controller.abort();
  }, [conversationId, accessToken]);

  const runAsk = useCallback(
    async (
      question: string,
      options: AskOptions,
      targetConversationId: string | null,
    ): Promise<AskResponse | null> => {
      if (!accessToken || !workspaceId) return null;
      setIsAsking(true);
      setAskError(null);
      setCanRetry(false);

      // Show the user's message immediately. It is replaced by the server's row
      // once the response arrives, so a refresh never double-counts it.
      const optimistic: Message = {
        id: `pending-${Date.now()}`,
        conversation_id: targetConversationId ?? '',
        role: 'user',
        content: question,
        sequence_number: Number.MAX_SAFE_INTEGER,
        execution_id: null,
        created_at: new Date().toISOString(),
      };
      setMessages((current) => [...current, optimistic]);

      try {
        const response = await askQuestion(accessToken, workspaceId, question, {
          ...options,
          conversationId: targetConversationId,
        });
        if (!mounted.current) return null;
        setMessages((current) => [
          ...current.filter((message) => message.id !== optimistic.id),
          response.question,
          response.message,
        ]);
        setLastAnswer(response.answer);
        return response;
      } catch (cause) {
        if (!mounted.current) return null;
        // Remove the optimistic message: leaving it would imply it was sent.
        setMessages((current) => current.filter((message) => message.id !== optimistic.id));
        setAskError(toErrorMessage(cause));
        setCanRetry(cause instanceof ApiError ? cause.isRetryable : true);
        return null;
      } finally {
        if (mounted.current) setIsAsking(false);
      }
    },
    [accessToken, workspaceId],
  );

  const ask = useCallback(
    async (question: string, options: AskOptions = {}): Promise<AskResponse | null> => {
      const target = options.conversationId ?? conversationId;
      lastQuestion.current = { question, options, conversationId: target ?? null };
      return runAsk(question, options, target ?? null);
    },
    [conversationId, runAsk],
  );

  const retry = useCallback(async (): Promise<AskResponse | null> => {
    const previous = lastQuestion.current;
    if (!previous) return null;
    return runAsk(previous.question, previous.options, previous.conversationId);
  }, [runAsk]);

  return { messages, error, isLoading, lastAnswer, isAsking, askError, canRetry, ask, retry };
}

/** Create a conversation. Separate from the list hook so the caller controls navigation. */
export function useCreateConversation(): {
  create: (workspaceId: string, title: string) => Promise<Conversation | null>;
  isCreating: boolean;
  error: string | null;
} {
  const { accessToken } = useAuth();
  const [isCreating, setIsCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const create = useCallback(
    async (workspaceId: string, title: string): Promise<Conversation | null> => {
      if (!accessToken) return null;
      setIsCreating(true);
      setError(null);
      try {
        return await createConversation(accessToken, workspaceId, title);
      } catch (cause) {
        setError(toErrorMessage(cause));
        return null;
      } finally {
        setIsCreating(false);
      }
    },
    [accessToken],
  );

  return { create, isCreating, error };
}
