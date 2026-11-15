import { AgentIndicator } from './AgentIndicator';
import { EvidencePlaceholder } from './EvidencePlaceholder';
import type { ChatMessage } from './types';
import './Message.css';

export interface AssistantMessageProps {
  message: ChatMessage;
  /** Shows the orchestrator/specialist attribution for composed answers. */
  showAgent?: boolean;
}

/** A message authored by an agent. Never rendered for unimplemented AI. */
export function AssistantMessage({ message, showAgent = true }: AssistantMessageProps): JSX.Element {
  return (
    <li className="message message--assistant">
      {showAgent && message.agentId && (
        <div className="message__author">
          <AgentIndicator agentId={message.agentId} size="sm" />
        </div>
      )}
      <div className="message__body">
        <p className="message__content">{message.content}</p>
        {message.evidence && message.evidence.length > 0 && (
          <EvidencePlaceholder evidence={message.evidence} />
        )}
      </div>
      <time className="message__meta" dateTime={message.createdAt}>
        {new Date(message.createdAt).toLocaleTimeString([], {
          hour: '2-digit',
          minute: '2-digit',
        })}
      </time>
    </li>
  );
}
