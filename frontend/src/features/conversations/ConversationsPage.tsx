import { Link } from 'react-router-dom';
import { PageContainer } from '../../components/layout/PageContainer';
import { Badge } from '../../components/ui/Badge';
import { EmptyState } from '../../components/ui/EmptyState';
import { Icon, type IconName } from '../../components/ui/Icon';
import { AGENT_CATALOG, type AgentId } from '../agents/agentCatalog';
import './ConversationsPage.css';

const AGENT_ICONS: Record<AgentId, IconName> = {
  orchestrator: 'orchestrator',
  retrieval: 'retrieval',
  memory: 'memory',
  verification: 'verification',
};

/**
 * Entry point to both conversation modes.
 *
 * The two modes are presented as two *different kinds of conversation* rather
 * than two cards of equal weight: orchestrated is the primary path and gets
 * the width to show the delegation chain; direct access is a compact list of
 * specialists underneath.
 */
export function ConversationsPage(): JSX.Element {
  const specialists = AGENT_CATALOG.filter((agent) => agent.kind === 'specialist');

  return (
    <PageContainer width="default">
      <div className="conv-page">
        <header className="conv-page__header">
          <p className="eyebrow">Conversations</p>
          <h1 className="conv-page__title display">Talk to MNEMOS</h1>
          <p className="conv-page__lede">
            Two ways to ask: one request answered by the orchestrator after consulting the
            specialists, or a direct line to a single specialist. Both are grounded in your
            indexed knowledge, and every claim carries a citation you can open.
          </p>
        </header>

        <section className="conv-primary" aria-labelledby="mode-orchestrated">
          <div className="conv-primary__body">
            <div className="conv-primary__head">
              <h2 className="conv-primary__title" id="mode-orchestrated">
                Orchestrated
              </h2>
              <Badge tone="accent" variant="outline">
                Mode A
              </Badge>
            </div>
            <p className="conv-primary__text">
              You ask once. The orchestrator is intended to decompose the request, consult the
              specialists that are relevant, reconcile what they return, and answer with citations.
              Where evidence is insufficient it must say so rather than fill the gap.
            </p>

            <ol className="conv-chain" aria-label="Intended delegation order">
              {['Request', 'Retrieval', 'Composition', 'Verification', 'Answer'].map(
                (label, index) => (
                  <li key={label} className="conv-chain__step">
                    <span className="conv-chain__index" data-mono>
                      {String(index + 1).padStart(2, '0')}
                    </span>
                    <span className="conv-chain__label">{label}</span>
                    {index < 4 && <span className="conv-chain__arrow" aria-hidden="true" />}
                  </li>
                ),
              )}
            </ol>

            <Link to="/app/conversations/orchestrator" className="conv-primary__cta">
              Open orchestrator interface
              <Icon name="arrow-right" size={15} />
            </Link>
          </div>

          <div className="conv-primary__aside" aria-hidden="true">
            <div className="conv-primary__glow" />
            <div className="conv-primary__glyph">
              <Icon name="orchestrator" size={26} />
            </div>
            <p className="conv-primary__aside-label" data-mono>
              One request · one composed answer
            </p>
          </div>
        </section>

        <section className="conv-specialists" aria-labelledby="mode-direct">
          <div className="conv-specialists__head">
            <h2 className="conv-specialists__title" id="mode-direct">
              Direct specialist
            </h2>
            <p className="conv-specialists__note">
              When you already know which job you need done.
            </p>
          </div>

          <ul className="conv-specialists__list" role="list">
            {specialists.map((agent) => (
              <li key={agent.id}>
                <Link to={`/app/conversations/agent/${agent.id}`} className="conv-specialist">
                  <span className="conv-specialist__icon">
                    <Icon name={AGENT_ICONS[agent.id]} size={16} />
                  </span>
                  <span className="conv-specialist__body">
                    <span className="conv-specialist__name">{agent.name}</span>
                    <span className="conv-specialist__summary">{agent.summary}</span>
                  </span>
                  <span className="conv-specialist__meta">
                    <Badge tone="brass" variant="dot">
                      Planned
                    </Badge>
                    <Icon name="arrow-right" size={14} />
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </section>

        <section className="conv-page__history" aria-labelledby="history-heading">
          <div className="conv-page__history-head">
            <h2 className="conv-page__history-title" id="history-heading">
              Conversation history
            </h2>
            <span className="conv-page__history-count" data-mono>
              0 stored
            </span>
          </div>
          <EmptyState
            icon={<Icon name="history" size={18} />}
            title="No conversations recorded"
            description="Persistence is not implemented yet. When conversations can be stored, they appear here with their agent, message count and the evidence they cited."
            footnote="This area is never populated with sample data."
          />
        </section>
      </div>
    </PageContainer>
  );
}
