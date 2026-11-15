import { useParams } from 'react-router-dom';
import { ConversationMetadata, ConversationView } from '../../components/conversation';
import type { ChatMessage, ConversationIdentity } from '../../components/conversation';
import { EmptyState } from '../../components/ui/EmptyState';
import { Icon } from '../../components/ui/Icon';
import { NotFoundPage } from '../system/NotFoundPage';
import { getAgent } from '../agents/agentCatalog';

const messages: ChatMessage[] = [];

/**
 * Mode B interface: a direct line to one specialist. Identity, attribution
 * and boundaries come from the agent contract, not from fabricated data.
 */
export function AgentConversationPage(): JSX.Element {
  const { agentId } = useParams<{ agentId: string }>();
  const agent = agentId ? getAgent(agentId) : undefined;

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

  return (
    <ConversationView
      identity={identity}
      messages={messages}
      showAgentAttribution={false}
      emptyState={
        <EmptyState
          icon={<Icon name="agents" size={20} />}
          title={`Direct conversation with ${agent.name}`}
          description={`${agent.summary} This role is not operational yet, so no response can be generated.`}
        />
      }
      composerNotice={`Sending is disabled: the ${agent.name} is not connected to a model yet.`}
      sidebar={
        <ConversationMetadata
          rows={[
            { label: 'Mode', value: 'Direct specialist' },
            { label: 'Agent', value: agent.name },
            { label: 'Status', value: 'Planned capability' },
            { label: 'Target phase', value: agent.targetPhase },
            { label: 'Evidence', value: 'None — retrieval not implemented' },
          ]}
        />
      }
    />
  );
}
