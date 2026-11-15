import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { MessageComposer } from './MessageComposer';

describe('MessageComposer', () => {
  it('is disabled with an explanation when messaging is unavailable', () => {
    render(<MessageComposer disabled disabledReason="Agent responses are not implemented yet" />);

    const textarea = screen.getByLabelText('Message');
    expect(textarea).toBeDisabled();
    expect(textarea).toHaveAttribute('placeholder', 'Agent responses are not implemented yet');
    expect(screen.getByRole('button', { name: /send/i })).toBeDisabled();
  });

  it('submits the typed message and clears the field', async () => {
    const user = userEvent.setup();
    const onSend = vi.fn();
    render(<MessageComposer onSend={onSend} />);

    const textarea = screen.getByLabelText('Message');
    await user.type(textarea, 'Summarise my notes');
    await user.click(screen.getByRole('button', { name: /send/i }));

    expect(onSend).toHaveBeenCalledWith('Summarise my notes');
    expect(textarea).toHaveValue('');
  });

  it('sends on Enter and inserts a newline on Shift+Enter', async () => {
    const user = userEvent.setup();
    const onSend = vi.fn();
    render(<MessageComposer onSend={onSend} />);

    const textarea = screen.getByLabelText('Message');
    await user.type(textarea, 'first{Shift>}{Enter}{/Shift}second');
    expect(onSend).not.toHaveBeenCalled();
    expect(textarea).toHaveValue('first\nsecond');

    await user.type(textarea, '{Enter}');
    expect(onSend).toHaveBeenCalledWith('first\nsecond');
  });

  it('does not submit whitespace-only messages', async () => {
    const user = userEvent.setup();
    const onSend = vi.fn();
    render(<MessageComposer onSend={onSend} />);

    await user.type(screen.getByLabelText('Message'), '   {Enter}');
    expect(onSend).not.toHaveBeenCalled();
  });

  it('shows the notice text when provided', () => {
    render(
      <MessageComposer disabled notice="Sending is disabled: no model execution exists yet." />,
    );
    expect(screen.getByText(/no model execution exists yet/i)).toBeInTheDocument();
  });
});
