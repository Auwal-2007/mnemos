import { Link } from 'react-router-dom';
import { PageContainer } from '../../components/layout/PageContainer';
import { PageHeader } from '../../components/layout/PageHeader';
import { Badge } from '../../components/ui/Badge';
import { Icon } from '../../components/ui/Icon';
import { AGENT_CATALOG } from './agentCatalog';
import './AgentDirectoryPage.css';

/** Directory of the planned specialist roles. Nothing here is operational. */
export function AgentDirectoryPage(): JSX.Element {
  return (
    <PageContainer width="default">
      <PageHeader
        eyebrow="Agents"
        title="Specialist roles"
        description="MNEMOS is designed around a central orchestrator and three specialists. These are the intended responsibilities and boundaries; no agent is connected to a model yet."
      />

      <div className="agent-banner" role="note">
        <Icon name="info" size={16} />
        <p>
          Planned capability. The contracts below define how agents will be allowed to behave —
          they are not an indication that agent intelligence or orchestration exists.
        </p>
      </div>

      <ul className="agent-grid" role="list">
        {AGENT_CATALOG.map((agent) => (
          <li key={agent.id}>
            <article className="agent-card" aria-labelledby={`agent-${agent.id}-name`}>
              <div className="agent-card__head">
                <div className="agent-card__title-block">
                  <h2 className="agent-card__name" id={`agent-${agent.id}-name`}>
                    {agent.name}
                  </h2>
                  <p className="agent-card__kind">
                    {agent.kind === 'orchestrator' ? 'Orchestrator' : 'Specialist'} ·{' '}
                    {agent.targetPhase}
                  </p>
                </div>
                <Badge tone="neutral">Planned</Badge>
              </div>

              <p className="agent-card__summary">{agent.summary}</p>

              <section className="agent-card__section">
                <h3 className="agent-card__label">Responsibilities</h3>
                <ul className="agent-card__list" role="list">
                  {agent.responsibilities.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </section>

              <section className="agent-card__section">
                <h3 className="agent-card__label">Boundaries</h3>
                <ul className="agent-card__list agent-card__list--muted" role="list">
                  {agent.boundaries.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </section>

              <dl className="agent-card__io">
                <div>
                  <dt>Inputs</dt>
                  <dd>{agent.inputs.join(' · ')}</dd>
                </div>
                <div>
                  <dt>Outputs</dt>
                  <dd>{agent.outputs.join(' · ')}</dd>
                </div>
              </dl>

              <Link
                to={`/conversations/agent/${agent.id}`}
                className="agent-card__link"
                aria-label={`Open the ${agent.name} conversation interface`}
              >
                Open conversation interface
                <span aria-hidden="true">→</span>
              </Link>
            </article>
          </li>
        ))}
      </ul>
    </PageContainer>
  );
}
