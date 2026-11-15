import { useEffect } from 'react';
import { Badge } from '../ui/Badge';
import { Icon } from '../ui/Icon';
import type { Provenance } from '../../lib/api/types';
import './EvidencePanel.css';

interface EvidencePanelProps {
  provenance: Provenance | null;
  open: boolean;
  onClose: () => void;
  /** Set while the provenance request is in flight. */
  loading?: boolean;
  error?: string | null;
  onRetry?: () => void;
}

/**
 * Evidence inspection drawer.
 *
 * This is where the product's central claim becomes checkable: a passage is
 * shown with the exact position it occupies in a specific document version,
 * its information status, and any supersession link. Every field is read from
 * `/chunks/{id}/provenance` — nothing is inferred.
 *
 * Implemented as a non-modal dialog on desktop (so the conversation stays
 * readable beside it) and a bottom sheet on narrow screens.
 */
export function EvidencePanel({
  provenance,
  open,
  onClose,
  loading = false,
  error = null,
  onRetry,
}: EvidencePanelProps): JSX.Element | null {
  // Escape closes; body scroll locks while the sheet is open on mobile.
  useEffect(() => {
    if (!open) return undefined;
    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <>
      <div className="evidence__scrim" onClick={onClose} role="presentation" />
      <aside
        className="evidence"
        role="dialog"
        aria-modal="false"
        aria-labelledby="evidence-heading"
      >
        <header className="evidence__head">
          <div className="evidence__title-block">
            <p className="evidence__eyebrow" data-mono>
              Provenance
            </p>
            <h2 className="evidence__title" id="evidence-heading">
              {provenance?.source_title ?? 'Evidence'}
            </h2>
          </div>
          <button type="button" className="evidence__close" onClick={onClose} aria-label="Close evidence">
            <Icon name="close" size={16} />
          </button>
        </header>

        {loading && (
          <div className="evidence__body">
            <div className="evidence__skeleton" />
            <div className="evidence__skeleton evidence__skeleton--short" />
            <div className="evidence__skeleton" />
          </div>
        )}

        {error && (
          <div className="evidence__body">
            <p className="evidence__error">{error}</p>
            {onRetry && (
              <button type="button" className="evidence__retry" onClick={onRetry}>
                Try again
              </button>
            )}
          </div>
        )}

        {provenance && (
          <div className="evidence__body">
            <div className="evidence__status-row">
              <Badge tone={statusTone(provenance.information_status)} variant="soft">
                {provenance.information_status.replace('_', ' ')}
              </Badge>
              <span className="evidence__chunk" data-mono>
                chunk {provenance.chunk_index + 1}
              </span>
            </div>

            <dl className="evidence__facts">
              <div className="evidence__fact">
                <dt>Document</dt>
                <dd>{provenance.source_title}</dd>
              </div>
              <div className="evidence__fact">
                <dt>Version</dt>
                <dd data-mono>v{provenance.version_number}</dd>
              </div>
              <div className="evidence__fact">
                <dt>Location</dt>
                <dd data-mono>
                  chars {provenance.source_location.start_offset}–
                  {provenance.source_location.end_offset}
                  {provenance.source_location.page
                    ? ` · p.${provenance.source_location.page}`
                    : ''}
                </dd>
              </div>
              <div className="evidence__fact">
                <dt>Submitted</dt>
                <dd data-mono>{formatStamp(provenance.submitted_at)}</dd>
              </div>
              <div className="evidence__fact">
                <dt>Kind</dt>
                <dd>{provenance.source_kind}</dd>
              </div>
              <div className="evidence__fact">
                <dt>Chunk id</dt>
                <dd data-mono className="evidence__id">
                  {provenance.chunk_id}
                </dd>
              </div>
            </dl>

            {provenance.superseded_by && (
              <div className="evidence__supersede">
                <Icon name="supersede" size={14} />
                <p>
                  This passage has been superseded. The replacement is recorded as{' '}
                  <span data-mono>{provenance.superseded_by.slice(0, 8)}…</span>.
                </p>
              </div>
            )}

            {provenance.revision_reference && (
              <div className="evidence__fact evidence__fact--full">
                <dt>Revision reference</dt>
                <dd data-mono>{provenance.revision_reference}</dd>
              </div>
            )}

            <p className="evidence__note">
              <Icon name="info" size={13} />
              Citations resolve to a position in this exact version. Re-indexing that version
              creates new chunks, so an older reference will report that it no longer exists rather
              than silently pointing somewhere else.
            </p>
          </div>
        )}
      </aside>
    </>
  );
}

function statusTone(status: Provenance['information_status']): 'accent' | 'brass' | 'danger' | 'neutral' {
  if (status === 'current') return 'accent';
  if (status === 'superseded' || status === 'archived') return 'brass';
  if (status === 'disputed') return 'danger';
  return 'neutral';
}

function formatStamp(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString(undefined, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}
