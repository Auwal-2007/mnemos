import type { ReactNode } from 'react';
import type { ConversationIdentity } from './types';
import { AgentIndicator } from './AgentIndicator';
import { Badge } from '../ui/Badge';
import './ConversationHeader.css';

export interface ConversationHeaderProps {
  identity: ConversationIdentity;
  actions?: ReactNode;
}

/**
 * Header shared by both conversation modes. The mode badge makes the
 * distinction explicit rather than implied by styling.
 */
export function ConversationHeader({ identity, actions }: ConversationHeaderProps): JSX.Element {
  const orchestrated = identity.kind === 'orchestrated';

  return (
    <header className="conversation-header">
      <div className="conversation-header__identity">
        {identity.agentId && <AgentIndicator agentId={identity.agentId} />}
        <div className="conversation-header__text">
          <h2 className="conversation-header__title">{identity.title}</h2>
          <p className="conversation-header__subtitle">{identity.subtitle}</p>
        </div>
      </div>
      <div className="conversation-header__meta">
        <Badge tone={orchestrated ? 'accent' : 'neutral'}>
          {orchestrated ? 'Orchestrated' : 'Direct specialist'}
        </Badge>
        {actions}
      </div>
    </header>
  );
}
