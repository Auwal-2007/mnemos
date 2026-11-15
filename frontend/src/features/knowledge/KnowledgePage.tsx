import { useEffect, useMemo, useState } from 'react';
import { PageContainer } from '../../components/layout/PageContainer';
import { Badge } from '../../components/ui/Badge';
import { EmptyState } from '../../components/ui/EmptyState';
import { ErrorState } from '../../components/ui/ErrorState';
import { Icon } from '../../components/ui/Icon';
import { LoadingState } from '../../components/ui/LoadingState';
import { useAuth } from '../../lib/auth';
import { useWorkspaces } from '../../lib/api/useWorkspaces';
import { useSources } from '../../lib/api/useSources';
import type { IngestionResult, KnowledgeSource } from '../../lib/api/types';
import { SourceDetailPanel } from './SourceDetailPanel';
import { SourceList } from './SourceList';
import { SourceSubmitPanel } from './SourceSubmitPanel';
import './KnowledgePage.css';

type Filter = 'all' | 'searchable' | 'processing' | 'attention';

const FILTERS: { id: Filter; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'searchable', label: 'Searchable' },
  { id: 'processing', label: 'Processing' },
  { id: 'attention', label: 'Needs attention' },
];

/**
 * The knowledge workspace.
 *
 * Structure: a persistent left rail for submission and filtering, a list of
 * sources, and a detail surface. Every number comes from the API — the empty
 * corpus says it is empty, and no sample sources exist anywhere.
 */
export function KnowledgePage(): JSX.Element {
  const { accessToken } = useAuth();
  const workspaces = useWorkspaces();
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>('all');
  const [query, setQuery] = useState('');

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

  const counts = useMemo(
    () => ({
      ready: sources.sources.filter((source) => source.processing_status === 'ready').length,
      failed: sources.sources.filter((source) => source.processing_status === 'failed').length,
      processing: sources.sources.filter((source) =>
        ['pending', 'validating', 'extracting', 'chunking', 'indexing'].includes(
          source.processing_status,
        ),
      ).length,
    }),
    [sources.sources],
  );

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return sources.sources.filter((source) => {
      if (needle && !source.title.toLowerCase().includes(needle)) return false;
      if (filter === 'searchable') return source.processing_status === 'ready';
      if (filter === 'attention') return source.processing_status === 'failed';
      if (filter === 'processing')
        return ['pending', 'validating', 'extracting', 'chunking', 'indexing'].includes(
          source.processing_status,
        );
      return true;
    });
  }, [sources.sources, filter, query]);

  return (
    <PageContainer width="wide">
      <div className="kb">
        <header className="kb__header">
          <div className="kb__header-text">
            <p className="eyebrow">Knowledge workspace</p>
            <h1 className="kb__title display">Your corpus</h1>
            <p className="kb__lede">
              Everything you add is stored privately, versioned, extracted into citable text and
              indexed for retrieval. Nothing here is summarised away before you can see it.
            </p>
          </div>

          <div className="kb__header-side">
            {activeWorkspace ? (
              <label className="kb__workspace">
                <span className="visually-hidden">Workspace</span>
                <Icon name="layers" size={14} />
                <select
                  className="kb__workspace-select"
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
                <Icon name="chevron-down" size={13} />
              </label>
            ) : (
              <Badge tone="neutral" variant="outline">
                No workspace
              </Badge>
            )}

            {sources.sources.length > 0 && (
              <div className="kb__tally" data-mono>
                <span>{sources.sources.length} sources</span>
                <span className="kb__tally-sep">·</span>
                <span className="kb__tally-ready">{counts.ready} searchable</span>
                {counts.failed > 0 && (
                  <>
                    <span className="kb__tally-sep">·</span>
                    <span className="kb__tally-fail">{counts.failed} failed</span>
                  </>
                )}
              </div>
            )}
          </div>
        </header>

        {workspaces.isLoading && <LoadingState label="Loading workspaces…" variant="panel" rows={3} />}

        {workspaces.error && (
          <ErrorState
            title="Workspaces could not be loaded"
            message={workspaces.error}
            onRetry={workspaces.reload}
          />
        )}

        {!workspaces.isLoading && !workspaces.error && workspaces.needsAuth && (
          <EmptyState
            icon={<Icon name="lock" size={20} />}
            title="Sign in to add sources"
            description="Your corpus is private to your account. Sign in to upload documents and write notes."
            size="hero"
            action={
              <a className="kb__cta" href="/sign-in">
                Sign in
              </a>
            }
          />
        )}

        {!workspaces.isLoading &&
          !workspaces.error &&
          !workspaces.needsAuth &&
          workspaces.data?.length === 0 && (
            <EmptyState
              icon={<Icon name="workspace" size={20} />}
              title="No workspace yet"
              description="A workspace holds your documents and notes. One is created automatically when you sign up; if you see this, none exists for your account yet."
              size="hero"
            />
          )}

        {activeWorkspace && (
          <div className="kb__layout">
            {/* ------------------------- Left rail ------------------------- */}
            <aside className="kb__rail" aria-label="Add and filter">
              <SourceSubmitPanel
                workspaceId={workspaceId}
                accessToken={accessToken}
                onSubmitted={handleSubmitted}
                onSourceUpdated={(sourceId) => setSelectedId(sourceId)}
              />

              <section className="kb__filters" aria-labelledby="kb-filter-heading">
                <h2 className="kb__filters-title" id="kb-filter-heading">
                  Filter
                </h2>
                <div className="kb__search">
                  <Icon name="search" size={14} />
                  <input
                    type="search"
                    className="kb__search-input"
                    placeholder="Find a source…"
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                    aria-label="Filter sources by title"
                  />
                </div>
                <div className="kb__chips" role="group" aria-label="Filter by state">
                  {FILTERS.map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      className={`kb__chip ${filter === item.id ? 'is-active' : ''}`}
                      onClick={() => setFilter(item.id)}
                      aria-pressed={filter === item.id}
                    >
                      {item.label}
                      {item.id === 'attention' && counts.failed > 0 && (
                        <span className="kb__chip-count" data-numeric>
                          {counts.failed}
                        </span>
                      )}
                    </button>
                  ))}
                </div>
              </section>

              <section className="kb__legend" aria-labelledby="kb-legend-heading">
                <h2 className="kb__legend-title" id="kb-legend-heading">
                  Status meanings
                </h2>
                <ul className="kb__legend-list" role="list">
                  {(['extracting', 'extracted', 'ready', 'failed'] as const).map((status) => (
                    <li key={status}>
                      <StatusMeaning status={status} />
                    </li>
                  ))}
                </ul>
              </section>
            </aside>

            {/* -------------------------- Source list ------------------------- */}
            <section className="kb__list" aria-labelledby="kb-sources-heading">
              <div className="kb__list-head">
                <h2 className="kb__list-title" id="kb-sources-heading">
                  Sources
                  <span className="kb__list-count" data-numeric>
                    {filtered.length}
                    {filtered.length !== sources.sources.length && ` / ${sources.sources.length}`}
                  </span>
                </h2>
                {activeWorkspace && (
                  <span className="kb__list-note">
                    {counts.processing > 0 ? `${counts.processing} in pipeline` : 'idle'}
                  </span>
                )}
              </div>

              {sources.isLoading && <LoadingState label="Loading sources…" variant="rows" rows={5} />}

              {sources.error && <ErrorState message={sources.error} onRetry={sources.reload} />}

              {!sources.isLoading && !sources.error && sources.sources.length === 0 && (
                <EmptyState
                  icon={<Icon name="sources" size={18} />}
                  title="Nothing submitted yet"
                  description="Upload a PDF, Markdown or text file from the panel beside this list, or write a note. Sources appear here with their real processing status."
                  footnote="Processing status is read back from the database after each step."
                />
              )}

              {!sources.isLoading && sources.sources.length > 0 && filtered.length === 0 && (
                <EmptyState
                  icon={<Icon name="filter" size={18} />}
                  title="No source matches"
                  description="Nothing in this workspace matches that filter or search term. Clear them to see everything again."
                  action={
                    <button
                      type="button"
                      className="kb__clear"
                      onClick={() => {
                        setFilter('all');
                        setQuery('');
                      }}
                    >
                      Clear filters
                    </button>
                  }
                />
              )}

              {filtered.length > 0 && (
                <SourceList
                  sources={filtered}
                  selectedId={selectedId}
                  onSelect={setSelectedId}
                />
              )}
            </section>

            {/* --------------------------- Detail ---------------------------- */}
            <section className="kb__detail" aria-labelledby="kb-detail-heading">
              <h2 className="visually-hidden" id="kb-detail-heading">
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
                <div className="kb__detail-empty">
                  <span className="kb__detail-empty-icon" aria-hidden="true">
                    <Icon name="fingerprint" size={22} />
                  </span>
                  <h3>Select a source</h3>
                  <p>
                    Open a source to see its versions, extraction result, chunk offsets and
                    indexing state — the evidence trail behind anything it will support.
                  </p>
                </div>
              )}
            </section>
          </div>
        )}
      </div>
    </PageContainer>
  );
}

function StatusMeaning({ status }: { status: 'extracting' | 'extracted' | 'ready' | 'failed' }): JSX.Element {
  const map = {
    extracting: { label: 'Extracting', text: 'Reading text and structure from the original.' },
    extracted: { label: 'Extracted', text: 'Text ready; not chunked or embedded, so not searchable.' },
    ready: { label: 'Ready', text: 'Chunked, embedded and searchable.' },
    failed: { label: 'Failed', text: 'Processing stopped. Open the source for the reason.' },
  } as const;
  const item = map[status];
  return (
    <>
      <span className={`kb__legend-dot kb__legend-dot--${status}`} aria-hidden="true" />
      <span className="kb__legend-label">{item.label}</span>
      <span className="kb__legend-text">{item.text}</span>
    </>
  );
}

export type { KnowledgeSource };
