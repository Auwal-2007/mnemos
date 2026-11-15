import { PageContainer } from '../../components/layout/PageContainer';
import { PageHeader } from '../../components/layout/PageHeader';
import { SystemStatus } from './SystemStatus';
import { WorkspaceSummary } from './WorkspaceSummary';

/**
 * Operational readiness: which integrations this deployment actually has
 * credentials for. Read straight from `/health` and `/ready`; nothing here is
 * inferred or assumed.
 */
export function SystemStatusPage(): JSX.Element {
  return (
    <PageContainer width="default">
      <PageHeader
        eyebrow="System"
        title="Deployment status"
        description="Live readiness checks from the API. A capability that is not configured is reported as missing rather than quietly unavailable."
      />
      <div className="system-page">
        <SystemStatus />
        <WorkspaceSummary />
      </div>
    </PageContainer>
  );
}
