import { Link } from 'react-router-dom';
import { PageContainer } from '../../components/layout/PageContainer';
import { EmptyState } from '../../components/ui/EmptyState';
import { Icon } from '../../components/ui/Icon';

export function NotFoundPage({
  title = 'Page not found',
  message = 'There is nothing at this address. It may have moved, or the link may be incorrect.',
}: {
  title?: string;
  message?: string;
}): JSX.Element {
  return (
    <PageContainer width="default">
      <EmptyState
        icon={<Icon name="alert" size={20} />}
        title={title}
        description={message}
        action={
          <Link to="/" className="notfound__link">
            Return home
          </Link>
        }
      />
    </PageContainer>
  );
}
