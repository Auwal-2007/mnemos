import './Spinner.css';

export interface SpinnerProps {
  size?: 'sm' | 'md';
  label?: string;
}

/** Indeterminate progress indicator with an accessible label. */
export function Spinner({ size = 'md', label = 'Loading' }: SpinnerProps): JSX.Element {
  return (
    <span className={`spinner spinner--${size}`} role="status">
      <span className="visually-hidden">{label}</span>
    </span>
  );
}
