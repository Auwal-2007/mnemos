import { Spinner } from './Spinner';
import './LoadingState.css';

/** Full-region loading placeholder used while data is in flight. */
export function LoadingState({ label = 'Loading…' }: { label?: string }): JSX.Element {
  return (
    <div className="loading-state" role="status" aria-live="polite">
      <Spinner label={label} />
      <span className="loading-state__label">{label}</span>
    </div>
  );
}
