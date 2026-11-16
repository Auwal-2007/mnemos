import { useCallback, useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { ConversationMetadata, ConversationView } from '../../components/conversation';
import { AnswerView } from '../../components/conversation/AnswerView';
import { EvidencePanel } from '../../components/conversation/EvidencePanel';
import { Badge } from '../../components/ui/Badge';
import { EmptyState } from '../../components/ui/EmptyState';
import { Icon } from '../../components/ui/Icon';
import type { ChatMessage, ConversationIdentity } from '../../components/conversation';
import { NotFoundPage } from '../system/NotFoundPage';
import { getAgent } from '../agents/agentCatalog';
import { useAuth } from '../../lib/auth';
import { fetchProvenance } from '../../lib/api/knowledge';
import { useConversationMessages } from '../../lib/api/useConversations';
import { useWorkspaces } from '../../lib/api/useWorkspaces';
import type { Answer, Citation, Message, Provenance } from '../../lib/api/types';
import '../conversations/OrchestratorConversationPage.css';

/**
 * Mode B: a direct line to one specialist.
 *
 * The interface advertises only what the backend actually exposes. All four
 * roles are reachable through the agent endpoint, but they are not
 * interchangeable: switching the specialist changes which reasoning the
 * orchestrator applies, and the page says which role is answering rather than
 * implying four independent services.
 */
export function AgentConversationPage(): JSX.Element {
  const { agentId } = useParams<{ agentId: string }>();
  const agent = agentId ? getAgent(agentId) : undefined;

  const { accessToken } = useAuth();
  const workspaces = useWorkspaces();
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);
  const thread = useConversationMessages(workspaceId, null);
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
      const response = await thread.ask(text, {
        // The backend role string, not the route id: 'retrieval' is a URL slug,
        // 'retrieval_specialist' is what the API accepts.
        agentRole: agent?.role ?? null,
      });
      if (response) setAnswer(response.answer);
    },
    [agentId, thread],
  );

  const transcript = useMemo<ChatMessage[]>(() => toChatMessages(thread.messages), [thread.messages]);

  if (!agent) {
    return (
      <NotFoundPage
        title="Unknown agent"
        message="That agent does not exist in the MNEMOS directory."
      />
    );
  }

  const identity: ConversationIdentity = {
    kind: 'direct',
    agentId: agent.id,
    title: agent.name,
    subtitle: agent.summary,
  };

  const canSend = Boolean(workspaceId && accessToken);

  return (
    <>
      <ConversationView
        identity={identity}
        messages={transcript}
        showAgentAttribution={false}
        sending={thread.isAsking}
        emptyState={
          <EmptyState
            icon={<Icon name="agents" size={20} />}
            title={`Direct conversation with ${agent.name}`}
            description={`${agent.summary} Answers are drawn only from your indexed knowledge and cite the passages they rely on.`}
          />
        }
        afterTranscript={
          <div className="orch">
            {thread.isAsking && (
              <p className="orch__pending" role="status">
                <Icon name="spinner" size={14} /> Consulting {agent.name}…
              </p>
            )}
            {answer && !thread.isAsking && (
              <div className="orch__answer" aria-live="polite">
                <div className="orch__answer-head">
                  <Badge tone="accent" variant="outline">
                    {agent.name}
                  </Badge>
                  <span className="orch__answer-source">
                    {answer.evidence_cited} citation{answer.evidence_cited === 1 ? '' : 's'}
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
          </div>
        }
        composerNotice={
          canSend
            ? `Speaking to ${agent.name}. Answers are grounded in your indexed knowledge.`
            : 'Sign in and create a workspace to start a conversation.'
        }
        onSend={canSend ? (text) => void handleSend(text) : undefined}
        sidebar={
          <ConversationMetadata
            rows={[
              { label: 'Mode', value: 'Direct specialist' },
              { label: 'Agent', value: agent.name },
              { label: 'Evidence', value: answer ? `${answer.evidence_cited} cited` : 'None yet' },
              ...(agent.capabilities ?? []).map((capability, index) => ({
                label: index === 0 ? 'Capabilities' : '',
                value: capability,
              })),
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
    content: message.content,
    createdAt: message.created_at,
    status: 'complete',
  }));
}
