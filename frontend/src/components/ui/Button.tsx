import type { ButtonHTMLAttributes, ReactNode } from 'react';
import './Button.css';

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'quiet';
type Size = 'sm' | 'md' | 'lg';

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  fullWidth?: boolean;
  loading?: boolean;
  icon?: ReactNode;
  /** Icon rendered after the label, for onward navigation. */
  trailingIcon?: ReactNode;
}

/**
 * Primary interactive control. Always renders a real <button> so keyboard and
 * screen-reader behaviour stays native.
 *
 * The primary variant is deliberately *paper white on charcoal* rather than a
 * saturated accent fill: it is the highest-contrast, most confident action in
 * the interface, and reserving saturated teal for state (not actions) keeps
 * "this is live" meaningful.
 */
export function Button({
  variant = 'secondary',
  size = 'md',
  fullWidth = false,
  loading = false,
  icon,
  trailingIcon,
  children,
  className = '',
  disabled,
  type = 'button',
  ...rest
}: ButtonProps): JSX.Element {
  const classes = [
    'btn',
    `btn--${variant}`,
    `btn--${size}`,
    fullWidth ? 'btn--full' : '',
    loading ? 'btn--loading' : '',
    className,
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <button
      type={type}
      className={classes}
      disabled={disabled ?? loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      {loading && <span className="btn__spinner" aria-hidden="true" />}
      {icon && !loading && (
        <span className="btn__icon" aria-hidden="true">
          {icon}
        </span>
      )}
      <span className="btn__label">{children}</span>
      {trailingIcon && (
        <span className="btn__icon btn__icon--trailing" aria-hidden="true">
          {trailingIcon}
        </span>
      )}
    </button>
  );
}
