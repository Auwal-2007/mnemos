import type { ReactNode } from 'react';
import './Badge.css';

type Tone = 'neutral' | 'accent' | 'success' | 'warning' | 'danger';

export interface BadgeProps {
  tone?: Tone;
  children: ReactNode;
  title?: string;
}

/** Small status label. Used to mark planned vs. available capabilities honestly. */
export function Badge({ tone = 'neutral', children, title }: BadgeProps): JSX.Element {
  return (
    <span className={`badge badge--${tone}`} title={title}>
      {children}
    </span>
  );
}
