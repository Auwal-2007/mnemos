import { ConversationMetadata, ConversationView } from '../../components/conversation';
import { EmptyState } from '../../components/ui/EmptyState';
import { Icon } from '../../components/ui/Icon';
import type { ChatMessage, ConversationIdentity } from '../../components/conversation';

const identity: ConversationIdentity = {
  kind: 'orchestrated',
  agentId: 'orchestrator',
  title: 'MNEMOS Orchestrator',
  subtitle: 'One request, composed answer — specialists consulted on your behalf.',
};

const messages: ChatMessage[] = [];

/**
 * Mode A interface. The transcript is empty because generation is not
 * implemented; the composer is disabled with an explicit explanation.
 */
export function OrchestratorConversationPage(): JSX.Element {
  return (
    <ConversationView
      identity={identity}
      messages={messages}
      showAgentAttribution={false}
      emptyState={
        <EmptyState
          icon={<Icon name="conversations" size={20} />}
          title="Orchestrated conversation"
          description="This is where a single request would be routed across the specialists and answered with evidence. Model execution is not implemented in this phase, so nothing can be sent yet."
        />
      }
      composerNotice="Sending is disabled: no model execution or orchestration exists yet."
      sidebar={
        <ConversationMetadata
          rows={[
            { label: 'Mode', value: 'Orchestrated' },
            { label: 'Lead agent', value: 'MNEMOS Orchestrator' },
            { label: 'Specialists', value: 'Retrieval · Memory · Verification' },
            { label: 'Evidence', value: 'None — retrieval not implemented' },
            { label: 'Persistence', value: 'Not implemented' },
          ]}
        />
      }
    />
  );
}
