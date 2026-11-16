import { useCallback, useEffect, useMemo, useState } from 'react';
import { ConversationMetadata, ConversationView } from '../../components/conversation';
import { AnswerView } from '../../components/conversation/AnswerView';
import { EvidencePanel } from '../../components/conversation/EvidencePanel';
import { Badge } from '../../components/ui/Badge';
import { EmptyState } from '../../components/ui/EmptyState';
import { Icon } from '../../components/ui/Icon';
import { useAuth } from '../../lib/auth';
import { fetchProvenance } from '../../lib/api/knowledge';
import { useConversationMessages, useConversations } from '../../lib/api/useConversations';
import { useWorkspaces } from '../../lib/api/useWorkspaces';
import type {
  Answer,
  Citation,
  Conversation,
  Message,
  Provenance,
} from '../../lib/api/types';
import type { ChatMessage, ConversationIdentity } from '../../components/conversation';
import './OrchestratorConversationPage.css';

const identity: ConversationIdentity = {
  kind: 'orchestrated',
  agentId: 'orchestrator',
  title: 'MNEMOS Orchestrator',
  subtitle: 'One request, composed answer — specialists consulted on your behalf.',
};

/**
 * The orchestrated conversation, connected to the real endpoints.
 *
 * pick workspace → pick or start conversation → ask → the backend retrieves,
 * composes and verifies; this page renders only what came back.
 *
 * Two behaviours are deliberate:
 *
 *  * An abstention is rendered as an answer, not as an error. Refusing without
 *    evidence is the designed behaviour, so presenting it as a failure would
 *    teach users to distrust the system for doing the right thing.
 *  * Every citation is a button that loads that chunk's provenance record.
 *    Inspectorability is the product's entire claim; a citation you cannot open
 *    is decoration.
 */
export function OrchestratorConversationPage(): JSX.Element {
  const { accessToken } = useAuth();
  const workspaces = useWorkspaces();
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const { conversations, isLoading: loadingConversations } = useConversations(workspaceId);
  const thread = useConversationMessages(workspaceId, conversationId);
  const [answer, setAnswer] = useState<Answer | null>(null);

  const [evidenceOpen, setEvidenceOpen] = useState(false);
  const [provenance, setProvenance] = useState<Provenance | null>(null);
  const [evidenceLoading, setEvidenceLoading] = useState(false);
  const [evidenceError, setEvidenceError] = useState<string | null>(null);
  const [activeChunkId, setActiveChunkId] = useState<string | null>(null);

  useEffect(() => {
    if (!workspaceId && workspaces.data && workspaces.data.length > 0) {
      setWorkspaceId(workspaces.data[0].id);
    }
  }, [workspaceId, workspaces.data]);

  useEffect(() => {
    if (!conversationId && conversations.length > 0) setConversationId(conversations[0].id);
  }, [conversationId, conversations]);

  const loadProvenance = useCallback(
    (chunkId: string) => {
      if (!accessToken) return;
      setActiveChunkId(chunkId);
      setEvidenceLoading(true);
      setEvidenceError(null);
      setProvenance(null);
      fetchProvenance(accessToken, chunkId)
        .then(setProvenance)
        .catch((cause: unknown) => {
          setEvidenceError(
            cause instanceof Error ? cause.message : 'Unable to load this passage.',
          );
        })
        .finally(() => setEvidenceLoading(false));
    },
    [accessToken],
  );

  const inspectEvidence = useCallback(
    (citation: Citation) => {
      setEvidenceOpen(true);
      loadProvenance(citation.chunk_id);
    },
    [loadProvenance],
  );

  const handleSend = useCallback(
    async (text: string) => {
      const response = await thread.ask(text, { conversationId });
      if (!response) return;
      setAnswer(response.answer);
      // The server creates a conversation on the first question; adopt its id so
      // the next question continues the same thread instead of starting a new one.
      if (!conversationId) setConversationId(response.conversation_id);
    },
    [conversationId, thread],
  );

  const transcript = useMemo<ChatMessage[]>(() => toChatMessages(thread.messages), [thread.messages]);

  const activeConversation: Conversation | null =
    conversations.find((item) => item.id === conversationId) ?? null;
  const canSend = Boolean(workspaceId && accessToken);

  return (
    <>
      <ConversationView
        identity={identity}
        messages={transcript}
        showAgentAttribution
        sending={thread.isAsking}
        emptyState={
          workspaceId ? (
            <EmptyState
              icon={<Icon name="conversations" size={20} />}
              title="Ask about your knowledge"
              description="Your question is answered only from indexed sources, with each claim tied to the passage that supports it. If the evidence is not there, MNEMOS says so instead of guessing."
            />
          ) : (
            <EmptyState
              icon={<Icon name="workspace" size={20} />}
              title={workspaces.isLoading ? 'Loading workspaces…' : 'No workspace yet'}
              description="Create a workspace and add knowledge before asking questions."
              footnote="Go to Workspaces from the sidebar to create one."
            />
          )
        }
        afterTranscript={
          <div className="orch">
            {thread.isAsking && (
              <p className="orch__pending" role="status">
                <Icon name="spinner" size={14} /> Retrieving evidence and composing an answer…
              </p>
            )}

            {answer && !thread.isAsking && (
              <div className="orch__answer" aria-live="polite">
                <div className="orch__answer-head">
                  <Badge tone="accent" variant="outline">
                    Answer
                  </Badge>
                  <span className="orch__answer-source">
                    {answer.evidence_cited > 0
                      ? `${answer.claims.length} claim${answer.claims.length === 1 ? '' : 's'} · ${answer.evidence_cited} citation${answer.evidence_cited === 1 ? '' : 's'}`
                      : 'No citations'}
                  </span>
                </div>
                <AnswerView answer={answer} onInspectEvidence={inspectEvidence} />
              </div>
            )}

            {thread.askError && (
              <div className="orch__error" role="alert">
                <p>{thread.askError}</p>
                {thread.canRetry && (
                  <button type="button" className="orch__retry" onClick={() => void thread.retry()}>
                    Try again
                  </button>
                )}
              </div>
            )}

            {thread.error && (
              <div className="orch__error" role="alert">
                <p>Could not load the conversation history: {thread.error}</p>
              </div>
            )}
          </div>
        }
        composerNotice={
          canSend
            ? 'Answers come only from your indexed knowledge. Evidence is cited for every claim.'
            : 'Sign in and create a workspace to start a conversation.'
        }
        onSend={canSend ? (text) => void handleSend(text) : undefined}
        sidebar={
          <ConversationMetadata
            rows={[
              { label: 'Mode', value: 'Orchestrated' },
              { label: 'Lead agent', value: 'MNEMOS Orchestrator' },
              { label: 'Specialists', value: 'Retrieval · Memory · Verification' },
              {
                label: 'Evidence',
                value:
                  answer === null
                    ? 'None yet'
                    : `${answer.evidence_considered} considered · ${answer.evidence_cited} cited`,
              },
              {
                label: 'Conversation',
                value:
                  activeConversation?.title ?? (loadingConversations ? 'Loading…' : 'Not started'),
              },
              { label: 'Persistence', value: conversationId ? 'Saved' : 'Starts on first question' },
            ]}
          />
        }
      />

      <EvidencePanel
        provenance={provenance}
        open={evidenceOpen}
        onClose={() => setEvidenceOpen(false)}
        loading={evidenceLoading}
        error={evidenceError}
        onRetry={activeChunkId ? () => loadProvenance(activeChunkId) : undefined}
      />
    </>
  );
}

function toChatMessages(messages: Message[]): ChatMessage[] {
  return messages.map((message) => ({
    id: message.id,
    author:
      message.role === 'user' ? 'user' : message.role === 'assistant' ? 'assistant' : 'system',
    agentId: 'orchestrator',
    content: message.content,
    createdAt: message.created_at,
    status: 'complete',
  }));
}
