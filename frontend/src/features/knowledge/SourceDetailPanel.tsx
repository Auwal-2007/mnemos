import { useCallback, useState } from 'react';
import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { ErrorState } from '../../components/ui/ErrorState';
import { LoadingState } from '../../components/ui/LoadingState';
import { toErrorMessage } from '../../lib/api/client';
import {
  deleteSource,
  fetchDownloadUrl,
  fetchSourceChunks,
  fetchSourceDetail,
  formatBytes,
  indexSource,
  reindexSource,
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
  const [isIndexing, setIsIndexing] = useState(false);
  const [indexNotice, setIndexNotice] = useState<string | null>(null);
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

  const chunkLoader = useCallback(
    () => fetchSourceChunks(accessToken, source.id),
    [accessToken, source.id],
  );
  const chunks = useAsync(chunkLoader, [source.id, source.processing_status]);

  async function runIndex(rebuild: boolean): Promise<void> {
    setActionError(null);
    setIndexNotice(null);
    setIsIndexing(true);
    try {
      const result = rebuild
        ? await reindexSource(accessToken, source.id)
        : await indexSource(accessToken, source.id);
      if (result.error_code) {
        setIndexNotice(
          `Indexing did not complete: ${result.error_message ?? result.error_code}`,
        );
      } else {
        setIndexNotice(
          `Indexed ${result.chunk_count} chunk${result.chunk_count === 1 ? '' : 's'}` +
            (result.embedding_model
              ? ` with ${result.embedding_model} (${result.embedding_dimension} dimensions).`
              : '. Embeddings were not created.'),
        );
      }
      chunks.reload();
      reload();
    } catch (cause) {
      setActionError(toErrorMessage(cause));
    } finally {
      setIsIndexing(false);
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

      <section className="detail__section" aria-labelledby="index-heading">
        <h3 className="detail__section-title" id="index-heading">
          Search index
        </h3>
        <p className="detail__index-note">
          {source.processing_status === 'ready'
            ? 'This source is chunked, embedded and searchable.'
            : source.processing_status === 'extracted'
              ? 'Text is extracted but not chunked or embedded, so it is not searchable yet. Indexing needs an embedding provider configured on the server.'
              : 'Indexing runs after extraction succeeds.'}
        </p>
        <div className="detail__actions">
          <Button
            size="sm"
            loading={isIndexing}
            disabled={isIndexing || source.processing_status === 'failed'}
            onClick={() => void runIndex(false)}
          >
            {source.processing_status === 'ready' ? 'Index again' : 'Index for search'}
          </Button>
          {source.processing_status === 'ready' && (
            <Button size="sm" variant="ghost" loading={isIndexing} onClick={() => void runIndex(true)}>
              Rebuild index
            </Button>
          )}
        </div>
        {indexNotice && (
          <p className="detail__index-notice" role="status">
            {indexNotice}
          </p>
        )}
      </section>

      <section className="detail__section" aria-labelledby="chunks-heading">
        <h3 className="detail__section-title" id="chunks-heading">
          Chunks
        </h3>
        {chunks.isLoading && <LoadingState label="Loading chunks…" />}
        {chunks.error && <ErrorState message={chunks.error} onRetry={chunks.reload} />}
        {chunks.data && chunks.data.items.length === 0 && (
          <p className="detail__empty">No chunks yet.</p>
        )}
        {chunks.data && chunks.data.items.length > 0 && (
          <>
            <p className="detail__index-note">
              {chunks.data.items.length} chunk{chunks.data.items.length === 1 ? '' : 's'} ·
              each resolves to an exact character range in this version.
            </p>
            <ol className="detail__chunks">
              {chunks.data.items.slice(0, 5).map((chunk) => (
                <li key={chunk.chunk_id} className="detail__chunk">
                  <span className="detail__chunk-index">#{chunk.chunk_index}</span>
                  <span className="detail__chunk-location">
                    chars {chunk.source_location.start_offset}–
                    {chunk.source_location.end_offset}
                    {chunk.source_location.page ? ` · p.${chunk.source_location.page}` : ''}
                  </span>
                  <span className="detail__chunk-preview">{chunk.preview}</span>
                </li>
              ))}
            </ol>
            {chunks.data.items.length > 5 && (
              <p className="detail__empty">
                Showing the first 5 of {chunks.data.items.length}.
              </p>
            )}
          </>
        )}
      </section>

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
