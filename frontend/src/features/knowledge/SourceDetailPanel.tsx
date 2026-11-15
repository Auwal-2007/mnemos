import { useCallback, useState } from 'react';
import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { ErrorState } from '../../components/ui/ErrorState';
import { LoadingState } from '../../components/ui/LoadingState';
import { toErrorMessage } from '../../lib/api/client';
import {
  deleteSource,
  fetchDownloadUrl,
  fetchSourceDetail,
  formatBytes,
} from '../../lib/api/knowledge';
import type { KnowledgeSource } from '../../lib/api/types';
import { useAsync } from '../../lib/hooks/useAsync';
import { presentStatus } from './status';
import './SourceDetailPanel.css';

export interface SourceDetailPanelProps {
  accessToken: string;
  source: KnowledgeSource;
  onDeleted: (sourceId: string) => void;
}

function formatTimestamp(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

/**
 * Detail view for one source: what was stored, what was extracted, and every
 * version that has ever been submitted. Nothing here is inferred — absent
 * data is shown as absent.
 */
export function SourceDetailPanel({
  accessToken,
  source,
  onDeleted,
}: SourceDetailPanelProps): JSX.Element {
  const [isDeleting, setIsDeleting] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const status = presentStatus(source.processing_status);

  const loader = useCallback(
    () => fetchSourceDetail(accessToken, source.id),
    [accessToken, source.id],
  );
  const { data, error, isLoading, reload } = useAsync(loader, [source.id, source.processing_status]);

  async function openOriginal(): Promise<void> {
    setActionError(null);
    try {
      const { url } = await fetchDownloadUrl(accessToken, source.id);
      window.open(url, '_blank', 'noopener,noreferrer');
    } catch (cause) {
      setActionError(toErrorMessage(cause));
    }
  }

  async function remove(): Promise<void> {
    setActionError(null);
    setIsDeleting(true);
    try {
      await deleteSource(accessToken, source.id);
      onDeleted(source.id);
    } catch (cause) {
      setActionError(toErrorMessage(cause));
    } finally {
      setIsDeleting(false);
    }
  }

  return (
    <section className="detail" aria-labelledby="detail-heading">
      <header className="detail__head">
        <div>
          <h2 className="detail__title" id="detail-heading">
            {source.title}
          </h2>
          <p className="detail__meta">
            {source.kind === 'note' ? 'Note' : (source.original_filename ?? 'Document')} ·{' '}
            {formatBytes(source.size_bytes)}
          </p>
        </div>
        <Badge tone={status.tone} title={status.description}>
          {status.label}
        </Badge>
      </header>

      <p className="detail__status-note">{status.description}</p>

      {source.processing_status === 'failed' && (
        <div className="detail__failure" role="alert">
          <strong>Processing failed</strong>
          <p>{source.processing_error_detail ?? 'No further detail was recorded.'}</p>
          {source.processing_error_code && (
            <p className="detail__code">Code: {source.processing_error_code}</p>
          )}
          <p className="detail__failure-note">
            The original file is still stored and can be downloaded. Nothing was
            silently discarded.
          </p>
        </div>
      )}

      <dl className="detail__facts">
        <div>
          <dt>Submitted</dt>
          <dd>{formatTimestamp(source.submitted_at)}</dd>
        </div>
        <div>
          <dt>Type</dt>
          <dd>{source.mime_type}</dd>
        </div>
        <div>
          <dt>Content hash</dt>
          <dd className="detail__hash" title={source.content_hash}>
            {source.content_hash.slice(0, 16)}…
          </dd>
        </div>
        <div>
          <dt>Processing attempts</dt>
          <dd>{source.processing_attempts}</dd>
        </div>
      </dl>

      <div className="detail__actions">
        {source.kind === 'document' && (
          <Button size="sm" onClick={() => void openOriginal()}>
            Open original
          </Button>
        )}
        <Button size="sm" variant="danger" loading={isDeleting} onClick={() => void remove()}>
          Delete source
        </Button>
      </div>
      <p className="detail__hint">
        Deleting removes the original file, its extracted text, all versions and
        every chunk derived from it. This cannot be undone.
      </p>

      {actionError && (
        <p className="detail__action-error" role="alert">
          {actionError}
        </p>
      )}

      <section className="detail__section" aria-labelledby="versions-heading">
        <h3 className="detail__section-title" id="versions-heading">
          Version history
        </h3>
        {isLoading && <LoadingState label="Loading versions…" />}
        {error && <ErrorState message={error} onRetry={reload} />}
        {data && data.versions.length === 0 && (
          <p className="detail__empty">No versions recorded.</p>
        )}
        {data && data.versions.length > 0 && (
          <ol className="detail__versions">
            {data.versions.map((version) => (
              <li key={version.id} className="detail__version">
                <span className="detail__version-number">v{version.version_number}</span>
                <span className="detail__version-meta">
                  {formatTimestamp(version.submitted_at)} ·{' '}
                  {version.extraction_method ?? 'no method recorded'}
                </span>
                {version.is_current && <Badge tone="success">Current</Badge>}
              </li>
            ))}
          </ol>
        )}
      </section>
    </section>
  );
}
