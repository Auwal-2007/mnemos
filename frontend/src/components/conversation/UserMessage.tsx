import type { ChatMessage } from './types';
import './Message.css';

/** A message authored by the user. */
export function UserMessage({ message }: { message: ChatMessage }): JSX.Element {
  return (
    <li className="message message--user">
      <div className="message__body">
        <p className="message__content">{message.content}</p>
      </div>
      <span className="message__meta">You</span>
    </li>
  );
}
