import type { ReactNode } from 'react';
import './EmptyState.css';

export interface EmptyStateProps {
  title: string;
  description: string;
  icon?: ReactNode;
  action?: ReactNode;
  /** `hero` gives the empty state room to breathe on a full-width page. */
  size?: 'default' | 'hero';
  /** Optional honest footnote, e.g. which phase will fill this area. */
  footnote?: string;
}

/**
 * Honest empty state.
 *
 * An empty corpus is a normal state, not an error, so it gets the same design
 * attention as populated content: a drawn mark, a plain explanation of what
 * will live here, and the one action that would start filling it. It is never
 * substituted with fabricated sample data.
 */
export function EmptyState({
  title,
  description,
  icon,
  action,
  size = 'default',
  footnote,
}: EmptyStateProps): JSX.Element {
  return (
    <div className={`empty-state empty-state--${size}`}>
      <div className="empty-state__mark" aria-hidden="true">
        <svg viewBox="0 0 64 64" className="empty-state__orbit" fill="none">
          <circle cx="32" cy="32" r="26" stroke="currentColor" strokeOpacity="0.14" />
          <circle cx="32" cy="32" r="17" stroke="currentColor" strokeOpacity="0.1" />
          <circle cx="32" cy="6" r="1.8" fill="currentColor" fillOpacity="0.5" />
          <circle cx="50" cy="45" r="1.4" fill="currentColor" fillOpacity="0.35" />
          <circle cx="13" cy="41" r="1.2" fill="currentColor" fillOpacity="0.3" />
        </svg>
        {icon && <div className="empty-state__icon">{icon}</div>}
      </div>
      <h3 className="empty-state__title">{title}</h3>
      <p className="empty-state__description">{description}</p>
      {action && <div className="empty-state__action">{action}</div>}
      {footnote && <p className="empty-state__footnote">{footnote}</p>}
    </div>
  );
}
