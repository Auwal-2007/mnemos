import { useEffect, useRef } from 'react';
import { AssistantMessage } from './AssistantMessage';
import { UserMessage } from './UserMessage';
import type { ChatMessage } from './types';
import './MessageList.css';

export interface MessageListProps {
  messages: ChatMessage[];
  showAgentAttribution?: boolean;
  emptyState?: React.ReactNode;
}

/** Scrollable transcript with polite live announcements for new messages. */
export function MessageList({
  messages,
  showAgentAttribution = true,
  emptyState,
}: MessageListProps): JSX.Element {
  const endRef = useRef<HTMLDivElement>(null);
  const latestId = messages.at(-1)?.id;

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: 'end', behavior: 'smooth' });
  }, [latestId]);

  if (messages.length === 0 && emptyState) {
    return <div className="message-list message-list--empty">{emptyState}</div>;
  }

  return (
    <div className="message-list" aria-live="polite" aria-relevant="additions">
      <ul className="message-list__items" role="list">
        {messages.map((message) =>
          message.author === 'user' ? (
            <UserMessage key={message.id} message={message} />
          ) : (
            <AssistantMessage
              key={message.id}
              message={message}
              showAgent={showAgentAttribution}
            />
          ),
        )}
      </ul>
      <div ref={endRef} />
    </div>
  );
}
