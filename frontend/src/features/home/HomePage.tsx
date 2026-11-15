import { Link } from 'react-router-dom';
import { PageContainer } from '../../components/layout/PageContainer';
import { Card } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { Icon } from '../../components/ui/Icon';
import { useAuth } from '../../lib/auth';
import { AGENT_CATALOG } from '../agents/agentCatalog';
import { SystemStatus } from './SystemStatus';
import { WorkspaceSummary } from './WorkspaceSummary';
import './HomePage.css';

const capabilities = [
  {
    title: 'Ask with evidence',
    body: 'Every answer is intended to trace back to the documents and notes it came from, with confidence reported honestly.',
  },
  {
    title: 'Keep knowledge current',
    body: 'Revisions, supersession and corrections are tracked so outdated claims are visibly retired rather than silently replaced.',
  },
  {
    title: 'Work with specialists',
    body: 'Talk to the orchestrator for composed answers, or to a specialist directly when you want one job done.',
  },
];

/** Home: product identity, real system status, and entry points. */
export function HomePage(): JSX.Element {
  const { status, user } = useAuth();
  const greeting = user?.email ? user.email.split('@')[0] : null;

  return (
    <PageContainer width="default">
      <section className="home-hero">
        <p className="home-hero__eyebrow">MNEMOS</p>
        <h1 className="home-hero__title">
          {greeting ? `Welcome back, ${greeting}` : 'A personal knowledge system that shows its work'}
        </h1>
        <p className="home-hero__lede">
          MNEMOS is built for questions you need to trust: a provenance-aware desk where your notes and
          documents become durable, citable knowledge — and where every claim can be traced, revised
          and challenged.
        </p>
        <div className="home-hero__actions">
          <Link to="/conversations" className="home-primary-link">
            Open a conversation
            <Icon name="conversations" size={16} />
          </Link>
          <Link to="/knowledge" className="home-secondary-link">
            <Icon name="workspace" size={16} />
            Knowledge workspace
          </Link>
          <Link to="/agents" className="home-secondary-link">
            <Icon name="agents" size={16} />
            Meet the agents
          </Link>
        </div>
        <p className="home-hero__footnote">
          Phase 1 foundation: the interface, data platform and authentication are in place. Agent
          intelligence and ingestion are not implemented yet.
        </p>
      </section>

      <section className="home-section" aria-labelledby="capabilities-heading">
        <h2 id="capabilities-heading" className="home-section__title">
          What MNEMOS is for
        </h2>
        <ul className="home-capabilities" role="list">
          {capabilities.map((item) => (
            <li key={item.title}>
              <Card padding="lg" className="home-capability">
                <h3 className="home-capability__title">{item.title}</h3>
                <p className="home-capability__body">{item.body}</p>
              </Card>
            </li>
          ))}
        </ul>
      </section>

      <div className="home-columns">
        <section className="home-section" aria-labelledby="agents-heading">
          <div className="home-section__header">
            <h2 id="agents-heading" className="home-section__title">
              Specialist roles
            </h2>
            <Link to="/agents" className="home-section__more">
              View directory
            </Link>
          </div>
          <ul className="home-agents" role="list">
            {AGENT_CATALOG.map((agent) => (
              <li key={agent.id} className="home-agent">
                <div className="home-agent__row">
                  <span className="home-agent__name">{agent.name}</span>
                  <Badge tone="neutral">Planned</Badge>
                </div>
                <p className="home-agent__summary">{agent.summary}</p>
              </li>
            ))}
          </ul>
        </section>

        <section className="home-section" aria-labelledby="status-heading">
          <h2 id="status-heading" className="home-section__title">
            System status
          </h2>
          <SystemStatus />
          <h2 id="workspaces-heading" className="home-section__title home-section__title--spaced">
            Your workspaces
          </h2>
          <WorkspaceSummary />
          <p className="home-status__note">
            {status === 'authenticated'
              ? 'Signed in with Supabase Auth.'
              : status === 'unconfigured'
                ? 'Supabase is not configured in this deployment, so authentication and stored data are unavailable.'
                : 'No active session.'}
          </p>
        </section>
      </div>

      <section className="home-section" aria-labelledby="recent-heading">
        <h2 id="recent-heading" className="home-section__title">
          Recent conversations
        </h2>
        <div className="home-empty">
          <p className="home-empty__title">No conversations yet</p>
          <p className="home-empty__body">
            Conversation storage and agent responses arrive in a later phase. Nothing is shown here
            until there is real data to show.
          </p>
        </div>
      </section>
    </PageContainer>
  );
}
