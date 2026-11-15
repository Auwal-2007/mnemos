import { useState } from 'react';
import { Link } from 'react-router-dom';
import { PageContainer } from '../../components/layout/PageContainer';
import { Badge } from '../../components/ui/Badge';
import { Icon, type IconName } from '../../components/ui/Icon';
import { AGENT_CATALOG, type AgentId } from './agentCatalog';
import './AgentDirectoryPage.css';

const AGENT_ICONS: Record<AgentId, IconName> = {
  orchestrator: 'orchestrator',
  retrieval: 'retrieval',
  memory: 'memory',
  verification: 'verification',
};

/**
 * Agent directory.
 *
 * The composition is a roster on the left and the selected contract on the
 * right. Each role has its own icon, its own accent within the system's three
 * hues, and a stated phase — so the four are visually distinguishable without
 * inventing four new colours.
 *
 * Nothing here is operational. Every card says so, and the direct-conversation
 * link is present but labelled as an interface preview, because that route
 * genuinely exists and honestly reports that sending is disabled.
 */
export function AgentDirectoryPage(): JSX.Element {
  const [selected, setSelected] = useState<AgentId>('orchestrator');
  const active = AGENT_CATALOG.find((agent) => agent.id === selected)!;
  const orchestrator = AGENT_CATALOG.find((agent) => agent.kind === 'orchestrator')!;
  const specialists = AGENT_CATALOG.filter((agent) => agent.kind === 'specialist');

  return (
    <PageContainer width="wide">
      <header className="agents-page__header">
        <div>
          <p className="eyebrow">Agents</p>
          <h1 className="agents-page__title display">Specialist roles</h1>
          <p className="agents-page__lede">
            One orchestrator and three specialists, each with a written mandate and hard
            boundaries. These are contracts, not capabilities: no agent is connected to a model
            yet.
          </p>
        </div>
        <div className="agents-page__status">
          <Badge tone="brass" variant="dot">
            Not executable
          </Badge>
          <span className="agents-page__status-note">Contracts define intended behaviour</span>
        </div>
      </header>

      {/* -------------------------- Orchestration map -------------------------- */}
      <section className="agents-map" aria-labelledby="agents-map-heading">
        <div className="agents-map__head">
          <h2 className="agents-map__title" id="agents-map-heading">
            How a request is intended to travel
          </h2>
          <p className="agents-map__note">
            Delegation is unilateral: the orchestrator may call specialists, specialists never call
            each other.
          </p>
        </div>

        <div className="agents-map__diagram" aria-hidden="true">
          <div className="agents-map__node agents-map__node--root">
            <Icon name="orchestrator" size={16} />
            <span>{orchestrator.name}</span>
          </div>
          <div className="agents-map__fan">
            {specialists.map((agent) => (
              <div key={agent.id} className="agents-map__branch">
                <span className="agents-map__wire" />
                <div className="agents-map__node">
                  <Icon name={AGENT_ICONS[agent.id]} size={15} />
                  <span>{agent.name}</span>
                </div>
              </div>
            ))}
          </div>
          <div className="agents-map__fan agents-map__fan--output">
            {['Evidence', 'Composed answer', 'Revision record'].map((label) => (
              <div key={label} className="agents-map__branch">
                <span className="agents-map__wire agents-map__wire--out" />
                <div className="agents-map__pill">{label}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ----------------------------- Roster + detail ------------------------- */}
      <div className="agents-page__split">
        <nav className="agents-roster" aria-label="Agent roles">
          <ul role="list">
            {AGENT_CATALOG.map((agent) => (
              <li key={agent.id}>
                <button
                  type="button"
                  className={`agents-roster__item ${agent.id === selected ? 'is-active' : ''}`}
                  onClick={() => setSelected(agent.id)}
                  aria-pressed={agent.id === selected}
                >
                  <span className="agents-roster__icon">
                    <Icon name={AGENT_ICONS[agent.id]} size={16} />
                  </span>
                  <span className="agents-roster__text">
                    <span className="agents-roster__name">{agent.name}</span>
                    <span className="agents-roster__kind" data-mono>
                      {agent.kind === 'orchestrator' ? 'Orchestrator' : `Specialist · ${agent.targetPhase}`}
                    </span>
                  </span>
                  <Icon name="chevron-right" size={14} />
                </button>
              </li>
            ))}
          </ul>
        </nav>

        <article className="agent-contract" aria-labelledby="contract-name">
          <div className="agent-contract__head">
            <span className="agent-contract__glyph">
              <Icon name={AGENT_ICONS[active.id]} size={20} />
            </span>
            <div className="agent-contract__title-block">
              <h2 className="agent-contract__name" id="contract-name">
                {active.name}
              </h2>
              <p className="agent-contract__kind" data-mono>
                {active.kind === 'orchestrator' ? 'Orchestrator' : 'Specialist'} ·{' '}
                {active.targetPhase}
              </p>
            </div>
            <Badge tone="brass" variant="outline">
              Planned
            </Badge>
          </div>

          <p className="agent-contract__summary">{active.summary}</p>

          <div className="agent-contract__grid">
            <section>
              <h3 className="agent-contract__label">Responsibilities</h3>
              <ul className="agent-contract__list" role="list">
                {active.responsibilities.map((item) => (
                  <li key={item}>
                    <span className="agent-contract__mark" aria-hidden="true" />
                    {item}
                  </li>
                ))}
              </ul>
            </section>

            <section>
              <h3 className="agent-contract__label">Hard boundaries</h3>
              <ul className="agent-contract__list agent-contract__list--boundary" role="list">
                {active.boundaries.map((item) => (
                  <li key={item}>
                    <span className="agent-contract__mark" aria-hidden="true" />
                    {item}
                  </li>
                ))}
              </ul>
            </section>
          </div>

          <dl className="agent-contract__io">
            <div>
              <dt>Inputs</dt>
              <dd>{active.inputs.join(' · ')}</dd>
            </div>
            <div>
              <dt>Outputs</dt>
              <dd>{active.outputs.join(' · ')}</dd>
            </div>
          </dl>

          <div className="agent-contract__footer">
            <p className="agent-contract__disclaimer">
              <Icon name="info" size={13} />
              Direct conversation opens an interface preview. Sending is disabled until agent
              execution is implemented.
            </p>
            <Link
              to={`/app/conversations/agent/${active.id}`}
              className="agent-contract__cta"
            >
              Open interface preview
              <Icon name="arrow-right" size={14} />
            </Link>
          </div>
        </article>
      </div>
    </PageContainer>
  );
}
