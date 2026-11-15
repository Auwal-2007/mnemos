import { useEffect, useState } from 'react';
import { PageContainer } from '../../components/layout/PageContainer';
import { PageHeader } from '../../components/layout/PageHeader';
import { Badge } from '../../components/ui/Badge';
import { EmptyState } from '../../components/ui/EmptyState';
import { ErrorState } from '../../components/ui/ErrorState';
import { Icon } from '../../components/ui/Icon';
import { LoadingState } from '../../components/ui/LoadingState';
import { useAuth } from '../../lib/auth';
import { useWorkspaces } from '../../lib/api/useWorkspaces';
import { useSources } from '../../lib/api/useSources';
import type { IngestionResult } from '../../lib/api/types';
import { SourceDetailPanel } from './SourceDetailPanel';
import { SourceList } from './SourceList';
import { SourceSubmitPanel } from './SourceSubmitPanel';
import { presentStatus } from './status';
import './KnowledgePage.css';

/**
 * The knowledge workspace: submit documents or notes, watch their real
 * processing status, and inspect what was stored.
 *
 * Every number on this page comes from the API. There are no sample sources
 * and no invented percentages: an empty corpus says it is empty.
 */
export function KnowledgePage(): JSX.Element {
  const { accessToken } = useAuth();
  const workspaces = useWorkspaces();
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  // Select the first workspace once they load; never fabricate one.
  useEffect(() => {
    if (!workspaceId && workspaces.data && workspaces.data.length > 0) {
      setWorkspaceId(workspaces.data[0].id);
    }
  }, [workspaceId, workspaces.data]);

  const sources = useSources(workspaceId);
  const selected = sources.sources.find((source) => source.id === selectedId) ?? null;

  function handleSubmitted(result: IngestionResult): void {
    sources.upsert(result.source);
    setSelectedId(result.source.id);
  }

  const activeWorkspace = workspaces.data?.find((item) => item.id === workspaceId) ?? null;
  const readyCount = sources.sources.filter((source) => source.processing_status === 'ready').length;
  const failedCount = sources.sources.filter((source) => source.processing_status === 'failed').length;

  return (
    <PageContainer width="wide">
      <PageHeader
        eyebrow="Knowledge workspace"
        title="Your corpus"
        description="Upload documents and write notes. Each one is stored privately, versioned, and extracted into text that later phases can cite."
        actions={
          activeWorkspace ? (
            <select
              className="kb-workspace"
              aria-label="Workspace"
              value={workspaceId ?? ''}
              onChange={(event) => {
                setWorkspaceId(event.target.value);
                setSelectedId(null);
              }}
            >
              {workspaces.data?.map((workspace) => (
                <option key={workspace.id} value={workspace.id}>
                  {workspace.name}
                </option>
              ))}
            </select>
          ) : (
            <Badge tone="neutral">No workspace</Badge>
          )
        }
      />

      {workspaces.isLoading && <LoadingState label="Loading workspaces…" />}

      {workspaces.error && (
        <ErrorState
          title="Workspaces could not be loaded"
          message={workspaces.error}
          onRetry={workspaces.reload}
        />
      )}

      {!workspaces.isLoading && !workspaces.error && workspaces.needsAuth && (
        <EmptyState
          title="Sign in to add sources"
          description="Your corpus is private to your account. Sign in to upload documents and write notes."
        />
      )}

      {!workspaces.isLoading &&
        !workspaces.error &&
        !workspaces.needsAuth &&
        workspaces.data?.length === 0 && (
          <EmptyState
            title="No workspace yet"
            description="A workspace holds your documents and notes. One is created automatically when you sign up; if you see this, none exists for your account yet."
          />
        )}

      {activeWorkspace && (
        <>
          <SourceSubmitPanel
            workspaceId={workspaceId}
            accessToken={accessToken}
            onSubmitted={handleSubmitted}
            onSourceUpdated={(sourceId) => setSelectedId(sourceId)}
          />

          <div className="kb-grid">
            <section className="kb-column" aria-labelledby="kb-sources-heading">
              <div className="kb-column__head">
                <h2 className="kb-column__title" id="kb-sources-heading">
                  Sources
                  {sources.sources.length > 0 && (
                    <span className="kb-column__count"> ({sources.sources.length})</span>
                  )}
                </h2>
                <span className="kb-column__summary">
                  {readyCount} searchable
                  {failedCount > 0 && ` · ${failedCount} failed`}
                </span>
              </div>

              {sources.isLoading && <LoadingState label="Loading sources…" />}
              {sources.error && (
                <ErrorState message={sources.error} onRetry={sources.reload} />
              )}
              {!sources.isLoading && !sources.error && sources.sources.length === 0 && (
                <div className="kb-empty">
                  <Icon name="sources" size={22} />
                  <h3>Nothing submitted yet</h3>
                  <p>
                    Upload a PDF, Markdown or text file above, or write a note. Sources
                    appear here with their real processing status.
                  </p>
                </div>
              )}
              {sources.sources.length > 0 && (
                <SourceList
                  sources={sources.sources}
                  selectedId={selectedId}
                  onSelect={setSelectedId}
                />
              )}
            </section>

            <section className="kb-column kb-column--detail" aria-labelledby="kb-detail-heading">
              <h2 className="kb-column__title kb-column__title--visually-hidden" id="kb-detail-heading">
                Source detail
              </h2>
              {selected ? (
                <SourceDetailPanel
                  key={selected.id}
                  accessToken={accessToken ?? ''}
                  source={selected}
                  onDeleted={(sourceId) => {
                    sources.remove(sourceId);
                    setSelectedId(null);
                  }}
                />
              ) : (
                <div className="kb-empty kb-empty--detail">
                  <Icon name="document" size={22} />
                  <h3>Select a source</h3>
                  <p>
                    Choose a source to see its versions, extraction result and deletion
                    behaviour.
                  </p>
                </div>
              )}
            </section>
          </div>

          <section className="kb-status-legend" aria-labelledby="kb-legend-heading">
            <h2 className="kb-status-legend__title" id="kb-legend-heading">
              What the statuses mean
            </h2>
            <ul className="kb-status-legend__list">
              {(['validating', 'extracting', 'extracted', 'indexing', 'ready', 'failed'] as const).map(
                (status) => {
                  const presented = presentStatus(status);
                  return (
                    <li key={status}>
                      <Badge tone={presented.tone}>{presented.label}</Badge>
                      <span>{presented.description}</span>
                    </li>
                  );
                },
              )}
            </ul>
          </section>
        </>
      )}
    </PageContainer>
  );
}
