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
  /** Optional: an absent notice means there is nothing to explain. */
  composerNotice?: string;
  headerActions?: ReactNode;
  showAgentAttribution?: boolean;
  onSend?: (message: string) => void;
  /** Rendered above the message list — used for the execution trace. */
  banner?: ReactNode;
  /**
   * Rendered between the transcript and the composer.
   *
   * The grounded answer lives here rather than in `banner`: it belongs after
   * the question it answers, and it is not metadata about the conversation.
   */
  afterTranscript?: ReactNode;
  /** True while a question is in flight; disables the composer but keeps text. */
  sending?: boolean;
}

/**
 * Shared body for both conversation modes (orchestrated and direct).
 *
 * Layout is a three-part column: identity header, transcript, composer, with
 * an optional aside. The transcript is the only element that scrolls, so the
 * composer never drifts out of reach on a long conversation.
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
  banner,
  afterTranscript,
  sending = false,
}: ConversationViewProps): JSX.Element {
  return (
    <div className={`conv-view ${sidebar ? 'conv-view--with-aside' : ''}`}>
      <div className="conv-view__main">
        <ConversationHeader identity={identity} actions={headerActions} />
        {banner && <div className="conv-view__banner">{banner}</div>}
        <MessageList
          messages={messages}
          showAgentAttribution={showAgentAttribution}
          emptyState={emptyState}
        />
        {afterTranscript}
        <MessageComposer
          sending={sending}
          onSend={onSend}
          disabled={!onSend}
          disabledReason="Agent responses are not implemented yet"
          notice={composerNotice}
        />
      </div>
      {sidebar && (
        <aside className="conv-view__aside" aria-label="Conversation context">
          {sidebar}
        </aside>
      )}
    </div>
  );
}
