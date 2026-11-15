import type { ReactNode } from 'react';
import './ConversationMetadata.css';

export interface MetadataRow {
  label: string;
  value: ReactNode;
}

/** Compact key/value panel describing a conversation's context. */
export function ConversationMetadata({ rows }: { rows: MetadataRow[] }): JSX.Element {
  return (
    <aside className="conv-metadata" aria-label="Conversation details">
      <h3 className="conv-metadata__title">Conversation</h3>
      <dl className="conv-metadata__list">
        {rows.map((row) => (
          <div key={row.label} className="conv-metadata__row">
            <dt className="conv-metadata__label">{row.label}</dt>
            <dd className="conv-metadata__value">{row.value}</dd>
          </div>
        ))}
      </dl>
    </aside>
  );
}
