import type { HTMLAttributes, ReactNode } from 'react';
import './Card.css';

export type CardSurface = 'plain' | 'raised' | 'inset' | 'glass';

export interface CardProps extends HTMLAttributes<HTMLElement> {
  as?: 'div' | 'section' | 'article' | 'li';
  padding?: 'none' | 'sm' | 'md' | 'lg';
  interactive?: boolean;
  /** Surface treatment. `glass` is reserved for overlays that sit above content. */
  surface?: CardSurface;
  /** Adds the cursor-tracking highlight. Requires `interactive`. */
  glow?: boolean;
  children: ReactNode;
}

/**
 * Content container.
 *
 * Depth is expressed by surface value and a hairline rather than drop shadows,
 * because on a near-black canvas shadows are invisible and borders are what
 * the eye actually reads.
 */
export function Card({
  as: Tag = 'div',
  padding = 'md',
  interactive = false,
  surface = 'plain',
  glow = false,
  className = '',
  children,
  ...rest
}: CardProps): JSX.Element {
  const classes = [
    'card',
    `card--pad-${padding}`,
    `card--surface-${surface}`,
    interactive ? 'card--interactive' : '',
    glow ? 'card--glow' : '',
    className,
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <Tag className={classes} {...(rest as HTMLAttributes<HTMLElement>)}>
      {children}
    </Tag>
  );
}
