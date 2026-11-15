import type { ReactNode } from 'react';
import { Button } from './Button';
import './ErrorState.css';

export interface ErrorStateProps {
  title?: string;
  message: string;
  requestId?: string;
  onRetry?: () => void;
  action?: ReactNode;
}

/** Consistent, non-alarmist error surface with optional retry. */
export function ErrorState({
  title = 'Something went wrong',
  message,
  requestId,
  onRetry,
  action,
}: ErrorStateProps): JSX.Element {
  return (
    <div className="error-state" role="alert">
      <h3 className="error-state__title">{title}</h3>
      <p className="error-state__message">{message}</p>
      {requestId && <p className="error-state__meta">Reference: {requestId}</p>}
      {(onRetry || action) && (
        <div className="error-state__actions">
          {onRetry && (
            <Button variant="secondary" size="sm" onClick={onRetry}>
              Try again
            </Button>
          )}
          {action}
        </div>
      )}
    </div>
  );
}
