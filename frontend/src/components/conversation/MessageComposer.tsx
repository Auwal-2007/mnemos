import { useRef, useState, type FormEvent, type KeyboardEvent } from 'react';
import { Button } from '../ui/Button';
import { Icon } from '../ui/Icon';
import './MessageComposer.css';

export interface MessageComposerProps {
  onSend?: (message: string) => void;
  disabled?: boolean;
  disabledReason?: string;
  placeholder?: string;
  /** Shows a visible note when sending is not available yet. */
  notice?: string;
}

const MAX_LENGTH = 8000;

/**
 * Composer for both conversation modes. When sending is not implemented,
 * the control is honestly disabled with an explanation — no silent no-ops.
 */
export function MessageComposer({
  onSend,
  disabled = false,
  disabledReason,
  placeholder = 'Write a message…',
  notice,
}: MessageComposerProps): JSX.Element {
  const [value, setValue] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const isDisabled = disabled || !onSend;
  const canSend = value.trim().length > 0 && !isDisabled;

  const resize = (): void => {
    const node = textareaRef.current;
    if (!node) return;
    node.style.height = 'auto';
    node.style.height = `${Math.min(node.scrollHeight, 200)}px`;
  };

  const submit = (): void => {
    if (!canSend || !onSend) return;
    onSend(value.trim());
    setValue('');
    if (textareaRef.current) textareaRef.current.style.height = 'auto';
  };

  const handleSubmit = (event: FormEvent): void => {
    event.preventDefault();
    submit();
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>): void => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  };

  return (
    <form className="composer" onSubmit={handleSubmit}>
      <div className={`composer__field ${isDisabled ? 'composer__field--disabled' : ''}`}>
        <label className="sr-only" htmlFor="composer-input">
          Message
        </label>
        <textarea
          id="composer-input"
          ref={textareaRef}
          className="composer__input"
          value={value}
          rows={1}
          placeholder={isDisabled ? (disabledReason ?? 'Messaging is not available') : placeholder}
          onChange={(event) => {
            setValue(event.target.value.slice(0, MAX_LENGTH));
            resize();
          }}
          onKeyDown={handleKeyDown}
          disabled={isDisabled}
          aria-describedby={notice ? 'composer-notice' : undefined}
        />
        <div className="composer__actions">
          <span className="composer__hint" aria-hidden="true">
            Enter to send · Shift+Enter for new line
          </span>
          <Button
            type="submit"
            variant="primary"
            size="sm"
            disabled={!canSend}
            icon={<Icon name="send" size={14} />}
          >
            Send
          </Button>
        </div>
      </div>
      {notice && (
        <p className="composer__notice" id="composer-notice">
          {notice}
        </p>
      )}
    </form>
  );
}
