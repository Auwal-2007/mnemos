import { PageContainer } from '../../components/layout/PageContainer';
import { PageHeader } from '../../components/layout/PageHeader';
import { Badge } from '../../components/ui/Badge';
import { EmptyState } from '../../components/ui/EmptyState';
import { Icon } from '../../components/ui/Icon';

export interface PlannedAreaPageProps {
  title: string;
  description: string;
  detail: string;
}

/**
 * Honest placeholder for a navigation destination whose feature does not
 * exist yet. It explains the gap instead of simulating functionality.
 */
export function PlannedAreaPage({
  title,
  description,
  detail,
}: PlannedAreaPageProps): JSX.Element {
  return (
    <PageContainer width="default">
      <PageHeader
        eyebrow="Planned area"
        title={title}
        description={description}
        actions={<Badge tone="warning">Not implemented</Badge>}
      />
      <EmptyState
        icon={<Icon name="info" size={20} />}
        title="This area is reserved for a later phase"
        description={detail}
      />
    </PageContainer>
  );
}
