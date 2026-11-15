import type { HTMLAttributes, ReactNode } from 'react';
import './Card.css';

export interface CardProps extends HTMLAttributes<HTMLDivElement> {
  as?: 'div' | 'section' | 'article';
  padding?: 'sm' | 'md' | 'lg';
  interactive?: boolean;
  children: ReactNode;
}

/** Elevated content container with a single border and no decoration. */
export function Card({
  as: Tag = 'div',
  padding = 'md',
  interactive = false,
  className = '',
  children,
  ...rest
}: CardProps): JSX.Element {
  return (
    <Tag
      className={`card card--pad-${padding} ${interactive ? 'card--interactive' : ''} ${className}`.trim()}
      {...rest}
    >
      {children}
    </Tag>
  );
}
