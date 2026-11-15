import { useCallback } from 'react';
import { fetchHealth, fetchReadiness } from '../../lib/api/health';
import { useAsync } from '../../lib/hooks';
import { ErrorState } from '../../components/ui/ErrorState';
import { LoadingState } from '../../components/ui/LoadingState';
import './SystemStatus.css';

/**
 * Real backend integration check: liveness plus which integrations are
 * configured server-side. Values are never displayed, only presence.
 */
export function SystemStatus(): JSX.Element {
  const loader = useCallback(async () => {
    const [health, readiness] = await Promise.all([fetchHealth(), fetchReadiness()]);
    return { health, readiness };
  }, []);

  const { data, error, isLoading, reload } = useAsync(loader);

  if (isLoading) return <LoadingState label="Checking API…" />;

  if (error || !data) {
    return (
      <ErrorState
        title="API unreachable"
        message={error ?? 'The backend did not respond.'}
        onRetry={reload}
      />
    );
  }

  return (
    <div className="sys-status">
      <div className="sys-status__row">
        <span className="sys-status__label">API</span>
        <span className="sys-status__value">
          <span className="dot dot--ok" aria-hidden="true" />
          v{data.health.version} · {data.health.environment}
        </span>
      </div>
      {data.readiness.checks.map((check) => (
        <div className="sys-status__row" key={check.name}>
          <span className="sys-status__label">{check.name.replace(/_/g, ' ')}</span>
          <span className="sys-status__value">
            <span
              className={`dot ${check.configured ? 'dot--ok' : 'dot--off'}`}
              aria-hidden="true"
            />
            {check.configured ? 'Configured' : 'Not configured'}
          </span>
        </div>
      ))}
    </div>
  );
}
