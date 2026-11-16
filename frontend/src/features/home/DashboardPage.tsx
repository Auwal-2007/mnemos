import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { PageContainer } from '../../components/layout/PageContainer';
import { Badge } from '../../components/ui/Badge';
import { EmptyState } from '../../components/ui/EmptyState';
import { ErrorState } from '../../components/ui/ErrorState';
import { Icon } from '../../components/ui/Icon';
import { LoadingState } from '../../components/ui/LoadingState';
import { useAuth } from '../../lib/auth';
import { useSources } from '../../lib/api/useSources';
import { useWorkspaces } from '../../lib/api/useWorkspaces';
import { AGENT_CATALOG } from '../agents/agentCatalog';
import { presentStatus } from '../knowledge/status';
import { SystemStatus } from './SystemStatus';
import { DashboardTimeline } from './DashboardTimeline';
import { KpiStrip } from './KpiStrip';
import './DashboardPage.css';

/**
 * The dashboard.
 *
 * Every figure here is counted from data the API actually returned. There is
 * no seeded activity feed, no invented "insights", and no chart. When the
 * corpus is empty the page says so and offers the single action that would
 * change that.
 *
 * The layout is intentionally asymmetric — a wide working column and a narrow
 * context column — because a symmetric grid of equal cards is the shape that
 * reads as a template.
 */
export function DashboardPage(): JSX.Element {
  const { user, status: authStatus } = useAuth();
  const workspaces = useWorkspaces();
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);

  useEffect(() => {
    if (!workspaceId && workspaces.data && workspaces.data.length > 0) {
      setWorkspaceId(workspaces.data[0].id);
    }
  }, [workspaceId, workspaces.data]);

  const sources = useSources(workspaceId);
  const activeWorkspace = workspaces.data?.find((item) => item.id === workspaceId) ?? null;
  const displayName = user?.email ? user.email.split('@')[0] : null;

  const counts = {
    total: sources.sources.length,
    ready: sources.sources.filter((source) => source.processing_status === 'ready').length,
    processing: sources.sources.filter((source) =>
      ['pending', 'validating', 'extracting', 'chunking', 'indexing'].includes(
        source.processing_status,
      ),
    ).length,
    failed: sources.sources.filter((source) => source.processing_status === 'failed').length,
    extracted: sources.sources.filter((source) => source.processing_status === 'extracted').length,
  };

  const recent = [...sources.sources]
    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
    .slice(0, 5);

  const isSignedIn = authStatus === 'authenticated';

  return (
    <PageContainer width="wide">
      <div className="dash">
        {/* ------------------------------ Header ------------------------------ */}
        <header className="dash__header">
          <div>
            <p className="eyebrow">
              {activeWorkspace ? activeWorkspace.name : 'Workspace'}
            </p>
            <h1 className="dash__title display">
              {displayName ? (
                <>
                  {greeting()}, <span className="dash__title-name">{displayName}.</span>
                </>
              ) : (
                'Your knowledge desk'
              )}
            </h1>
            <p className="dash__subtitle">
              {isSignedIn
                ? 'Everything below is measured from your own corpus.'
                : 'Sign in to see your corpus. Nothing is simulated in the meantime.'}
            </p>
          </div>

          <div className="dash__header-actions">
            <Link to="/app/knowledge" className="dash__action dash__action--primary">
              <Icon name="plus" size={15} />
              Add a source
            </Link>
            <Link to="/app/conversations" className="dash__action">
              <Icon name="conversations" size={15} />
              Ask a question
            </Link>
          </div>
        </header>

        {/* ------------------------------- KPIs ------------------------------- */}
        <KpiStrip counts={counts} loading={sources.isLoading} hasWorkspace={Boolean(workspaceId)} />

        {/* ------------------------------ Columns ----------------------------- */}
        <div className="dash__columns">
          <div className="dash__main">
            <section className="dash__section" aria-labelledby="recent-sources">
              <div className="dash__section-head">
                <h2 className="dash__section-title" id="recent-sources">
                  Recently added
                </h2>
                {recent.length > 0 && (
                  <Link to="/app/knowledge" className="dash__section-link">
                    All sources
                    <Icon name="arrow-right" size={13} />
                  </Link>
                )}
              </div>

              {!isSignedIn ? (
                <EmptyState
                  icon={<Icon name="lock" size={18} />}
                  title="No session"
                  description="Sign in to load your workspace. The dashboard deliberately shows nothing rather than stand-in data."
                  action={
                    <Link to="/sign-in" className="dash__inline-cta">
                      Sign in
                    </Link>
                  }
                />
              ) : sources.isLoading ? (
                <LoadingState variant="panel" label="Loading sources" rows={4} />
              ) : sources.error ? (
                <ErrorState message={sources.error} onRetry={sources.reload} />
              ) : recent.length === 0 ? (
                <EmptyState
                  icon={<Icon name="library" size={18} />}
                  title="Your archive is empty"
                  description="Add a PDF, a text file or a note. It will be stored privately, versioned, extracted and indexed — then it becomes something you can ask about."
                  action={
                    <Link to="/app/knowledge" className="dash__inline-cta">
                      Add your first source
                    </Link>
                  }
                  footnote="Nothing appears here until a real source exists."
                />
              ) : (
                <ul className="dash__sources" role="list">
                  {recent.map((source) => {
                    const status = presentStatus(source.processing_status);
                    return (
                      <li key={source.id}>
                        <Link to="/app/knowledge" className="dash__source">
                          <span className="dash__source-icon" aria-hidden="true">
                            <Icon name={source.kind === 'note' ? 'note' : 'document'} size={16} />
                          </span>
                          <span className="dash__source-body">
                            <span className="dash__source-title">{source.title}</span>
                            <span className="dash__source-meta" data-mono>
                              {formatDate(source.created_at)} · {source.kind}
                            </span>
                          </span>
                          <Badge tone={status.tone} variant="dot">
                            {status.label}
                          </Badge>
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              )}
            </section>

            <section className="dash__section" aria-labelledby="activity-heading">
              <div className="dash__section-head">
                <h2 className="dash__section-title" id="activity-heading">
                  Knowledge pipeline
                </h2>
                <span className="dash__section-note">Derived from source states</span>
              </div>
              <DashboardTimeline
                total={counts.total}
                ready={counts.ready}
                extracted={counts.extracted}
                failed={counts.failed}
                processing={counts.processing}
                enabled={isSignedIn && Boolean(workspaceId)}
              />
            </section>
          </div>

          <aside className="dash__side" aria-label="Context">
            <section className="dash__panel" aria-labelledby="agents-side-heading">
              <div className="dash__section-head">
                <h2 className="dash__section-title" id="agents-side-heading">
                  Agents
                </h2>
                <Link to="/app/agents" className="dash__section-link">
                  Contracts
                </Link>
              </div>
              <ul className="dash__agents" role="list">
                {AGENT_CATALOG.map((agent) => (
                  <li key={agent.id} className="dash__agent">
                    <span className="dash__agent-dot" aria-hidden="true" />
                    <span className="dash__agent-body">
                      <span className="dash__agent-name">{agent.name}</span>
                      <span className="dash__agent-phase" data-mono>
                        Available
                      </span>
                    </span>
                  </li>
                ))}
              </ul>
              <p className="dash__panel-note">
                Agent execution is not implemented. These roles describe the intended system; they
                cannot be invoked yet.
              </p>
            </section>

            <section className="dash__panel" aria-labelledby="status-side-heading">
              <div className="dash__section-head">
                <h2 className="dash__section-title" id="status-side-heading">
                  Integrations
                </h2>
              </div>
              <SystemStatus />
            </section>

            <section className="dash__panel dash__panel--quiet" aria-labelledby="next-side-heading">
              <h2 className="dash__section-title" id="next-side-heading">
                What is next
              </h2>
              <p className="dash__panel-note">
                Retrieval, answer composition and evidence verification are the next build phase.
                Until then, sources can be ingested, chunked and indexed, but nothing can answer a
                question about them.
              </p>
            </section>
          </aside>
        </div>
      </div>
    </PageContainer>
  );
}

function greeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return 'Good morning';
  if (hour < 18) return 'Good afternoon';
  return 'Good evening';
}

function formatDate(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return 'unknown date';
  return date.toLocaleDateString(undefined, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  });
}
