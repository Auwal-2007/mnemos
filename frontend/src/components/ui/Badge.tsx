import type { ReactNode } from 'react';
import './Badge.css';

type Tone = 'neutral' | 'accent' | 'brass' | 'success' | 'warning' | 'danger';
type Variant = 'soft' | 'outline' | 'dot';

export interface BadgeProps {
  tone?: Tone;
  /**
   * `soft` is a filled tint, `outline` a hairline, `dot` a leading status dot
   * with no fill — the quietest way to mark live state.
   */
  variant?: Variant;
  children: ReactNode;
  title?: string;
}

/**
 * Small status label. Used to mark planned vs. available capabilities
 * honestly, and to carry the provenance/supersession vocabulary.
 */
export function Badge({
  tone = 'neutral',
  variant = 'soft',
  children,
  title,
}: BadgeProps): JSX.Element {
  return (
    <span className={`badge badge--${tone} badge--${variant}`} title={title}>
      {variant === 'dot' && <span className="badge__dot" aria-hidden="true" />}
      {children}
    </span>
  );
}
