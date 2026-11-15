import { Spinner } from './Spinner';
import './LoadingState.css';

export interface LoadingStateProps {
  label?: string;
  /**
   * `rows` renders skeleton lines shaped like the content that is coming,
   * which communicates *what* is loading rather than just that something is.
   */
  variant?: 'inline' | 'rows' | 'panel';
  rows?: number;
}

/**
 * Loading placeholder.
 *
 * There are no progress percentages here on purpose: the interface only ever
 * prints a number it received from the backend. A spinner plus a real status
 * word is honest; a fake 40% is not.
 */
export function LoadingState({
  label = 'Loading…',
  variant = 'inline',
  rows = 3,
}: LoadingStateProps): JSX.Element {
  if (variant === 'inline') {
    return (
      <div className="loading-state" role="status" aria-live="polite">
        <Spinner label={label} />
        <span className="loading-state__label">{label}</span>
      </div>
    );
  }

  return (
    <div className={`loading-state loading-state--${variant}`} role="status" aria-live="polite">
      <span className="visually-hidden">{label}</span>
      {Array.from({ length: rows }, (_, index) => (
        <span
          key={index}
          className="loading-state__row"
          style={{ width: `${100 - (index % 3) * 14}%` }}
          aria-hidden="true"
        />
      ))}
    </div>
  );
}
