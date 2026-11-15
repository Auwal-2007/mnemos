import { getAgent } from '../../features/agents/agentCatalog';
import type { AgentId } from '../../features/agents/agentCatalog';
import './AgentIndicator.css';

export interface AgentIndicatorProps {
  agentId: AgentId;
  size?: 'sm' | 'md';
}

/** Compact identity marker for the agent behind a conversation or message. */
export function AgentIndicator({ agentId, size = 'md' }: AgentIndicatorProps): JSX.Element {
  const agent = getAgent(agentId);
  const label = agent?.name ?? agentId;
  const initials = agentId === 'orchestrator' ? 'OR' : agentId.slice(0, 2).toUpperCase();

  return (
    <span className={`agent-indicator agent-indicator--${size}`} title={label}>
      <span className="agent-indicator__badge" aria-hidden="true">
        {initials}
      </span>
      {size === 'md' && <span className="agent-indicator__name">{label}</span>}
    </span>
  );
}
