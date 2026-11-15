import { Link } from 'react-router-dom';
import { useWorkspaces } from '../../lib/api/useWorkspaces';
import { ErrorState } from '../../components/ui/ErrorState';
import { LoadingState } from '../../components/ui/LoadingState';
import './WorkspaceSummary.css';

/**
 * Real workspace data. Each state (no auth, unconfigured, loading, error,
 * empty, populated) is rendered honestly.
 */
export function WorkspaceSummary(): JSX.Element {
  const { data, error, isLoading, needsAuth, unconfigured, reload } = useWorkspaces();

  if (unconfigured) {
    return (
      <div className="ws-summary__notice">
        <p className="ws-summary__notice-title">Data layer not configured</p>
        <p className="ws-summary__notice-body">
          Supabase credentials are not present in this deployment, so workspaces cannot be loaded.
        </p>
      </div>
    );
  }

  if (needsAuth) {
    return (
      <div className="ws-summary__notice">
        <p className="ws-summary__notice-title">Sign in to see your workspaces</p>
        <p className="ws-summary__notice-body">
          Workspaces are private to your account and are never shown to anonymous visitors.
        </p>
        <Link to="/sign-in" className="ws-summary__link">
          Sign in
        </Link>
      </div>
    );
  }

  if (isLoading) return <LoadingState label="Loading workspaces…" />;

  if (error) {
    return (
      <ErrorState title="Could not load workspaces" message={error} onRetry={reload} />
    );
  }

  const workspaces = data ?? [];

  if (workspaces.length === 0) {
    return (
      <div className="ws-summary__notice">
        <p className="ws-summary__notice-title">No workspaces yet</p>
        <p className="ws-summary__notice-body">
          A default workspace is created automatically when your account is provisioned. If this
          stays empty, the signup trigger may not have run.
        </p>
      </div>
    );
  }

  return (
    <ul className="ws-summary" role="list">
      {workspaces.map((workspace) => (
        <li key={workspace.id} className="ws-summary__item">
          <span className="ws-summary__name">{workspace.name}</span>
          <span className="ws-summary__meta">
            {workspace.slug} · {workspace.owner_id.slice(0, 8)}
          </span>
        </li>
      ))}
    </ul>
  );
}
