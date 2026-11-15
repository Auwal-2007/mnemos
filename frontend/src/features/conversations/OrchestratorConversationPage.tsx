import { ConversationMetadata, ConversationView } from '../../components/conversation';
import { ExecutionTimeline, type ExecutionStep } from '../../components/conversation/ExecutionTimeline';
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
 * The delegated path, stated as it is intended to run.
 *
 * Every step is `pending`: there are no execution events because there is no
 * orchestrator. The timeline therefore renders in "Planned — not run" mode,
 * which is a visible statement rather than a subtle styling difference.
 */
const plannedSteps: ExecutionStep[] = [
  {
    id: 'receive',
    actor: 'MNEMOS Orchestrator',
    role: 'Receives the request and decides which specialists are needed.',
    state: 'pending',
  },
  {
    id: 'retrieve',
    actor: 'Retrieval Specialist',
    role: 'Searches your corpus and returns ranked passages with source identifiers.',
    state: 'pending',
  },
  {
    id: 'memory',
    actor: 'Memory Management Specialist',
    role: 'Supplies what is currently known, including superseded and disputed claims.',
    state: 'pending',
  },
  {
    id: 'compose',
    actor: 'MNEMOS Orchestrator',
    role: 'Reconciles findings into one answer, citing each supported claim.',
    state: 'pending',
  },
  {
    id: 'verify',
    actor: 'Evidence Verification Specialist',
    role: 'Checks every claim against its cited passage and reports insufficiency.',
    state: 'pending',
  },
];

export function OrchestratorConversationPage(): JSX.Element {
  return (
    <ConversationView
      identity={identity}
      messages={messages}
      showAgentAttribution={false}
      banner={<ExecutionTimeline steps={plannedSteps} live={false} />}
      emptyState={
        <EmptyState
          icon={<Icon name="conversations" size={20} />}
          title="Orchestrated conversation"
          description="This is where a single request would be routed across the specialists and answered with evidence. Model execution is not implemented in this phase, so nothing can be sent yet."
          footnote="The composer is disabled rather than silently discarding messages."
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
