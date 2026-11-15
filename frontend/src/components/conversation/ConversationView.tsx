import type { ReactNode } from 'react';
import { ConversationHeader } from './ConversationHeader';
import { MessageComposer } from './MessageComposer';
import { MessageList } from './MessageList';
import type { ChatMessage, ConversationIdentity } from './types';
import './ConversationView.css';

export interface ConversationViewProps {
  identity: ConversationIdentity;
  messages: ChatMessage[];
  sidebar?: ReactNode;
  emptyState: ReactNode;
  composerNotice: string;
  headerActions?: ReactNode;
  showAgentAttribution?: boolean;
  onSend?: (message: string) => void;
}

/**
 * Shared body for both conversation modes (orchestrated and direct).
 * Message rendering, layout, composer and metadata are identical; only
 * identity and attribution differ.
 */
export function ConversationView({
  identity,
  messages,
  sidebar,
  emptyState,
  composerNotice,
  headerActions,
  showAgentAttribution = true,
  onSend,
}: ConversationViewProps): JSX.Element {
  return (
    <div className={`conv-view ${sidebar ? 'conv-view--with-aside' : ''}`}>
      <div className="conv-view__main">
        <ConversationHeader identity={identity} actions={headerActions} />
        <MessageList
          messages={messages}
          showAgentAttribution={showAgentAttribution}
          emptyState={emptyState}
        />
        <MessageComposer
          onSend={onSend}
          disabled={!onSend}
          disabledReason="Agent responses are not implemented yet"
          notice={composerNotice}
        />
      </div>
      {sidebar && <div className="conv-view__aside">{sidebar}</div>}
    </div>
  );
}
