import { Badge } from '../../components/ui/Badge';
import { Icon } from '../../components/ui/Icon';
import { formatBytes } from '../../lib/api/knowledge';
import type { KnowledgeSource } from '../../lib/api/types';
import { presentStatus } from './status';
import './SourceList.css';

export interface SourceListProps {
  sources: KnowledgeSource[];
  selectedId: string | null;
  onSelect: (sourceId: string) => void;
}

function formatDate(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return 'Unknown date';
  return date.toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

function typeLabel(source: KnowledgeSource): string {
  if (source.kind === 'note') return 'Note';
  if (source.mime_type === 'application/pdf') return 'PDF';
  if (source.mime_type === 'text/markdown') return 'Markdown';
  return 'Text';
}

/** A source row. Every value shown comes from the server response. */
export function SourceList({ sources, selectedId, onSelect }: SourceListProps): JSX.Element {
  return (
    <ul className="source-list" aria-label="Sources">
      {sources.map((source) => {
        const status = presentStatus(source.processing_status);
        const isSelected = source.id === selectedId;
        return (
          <li key={source.id}>
            <button
              type="button"
              className={`source-row ${isSelected ? 'source-row--selected' : ''}`}
              onClick={() => onSelect(source.id)}
              aria-current={isSelected ? 'true' : undefined}
            >
              <span className="source-row__icon" aria-hidden="true">
                <Icon name={source.kind === 'note' ? 'note' : 'document'} size={16} />
              </span>
              <span className="source-row__main">
                <span className="source-row__title">{source.title}</span>
                <span className="source-row__meta">
                  {typeLabel(source)} · {formatBytes(source.size_bytes)} ·{' '}
                  {formatDate(source.submitted_at)}
                </span>
                {source.processing_status === 'failed' && source.processing_error_detail && (
                  <span className="source-row__error">{source.processing_error_detail}</span>
                )}
              </span>
              <Badge tone={status.tone} title={status.description}>
                {status.label}
              </Badge>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
