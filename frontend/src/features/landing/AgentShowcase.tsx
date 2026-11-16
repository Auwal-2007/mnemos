/**
 * AgentShowcase — the orchestration topology.
 *
 * The layout is the argument: one orchestrator above, three specialists
 * below, and connector paths that only exist while a specialist is selected.
 * Selecting a specialist is a *documentation* interaction (it shows that
 * agent's contract), not an execution — the panel footer says so, because
 * implying live agent activity through animation alone would be dishonest.
 *
 * Content is sourced from AGENT_CATALOG, the same registry the authenticated
 * agent directory reads, so the public page cannot drift from the product.
 */

import { useState } from 'react';
import { AGENT_CATALOG, type AgentId } from '../agents/agentCatalog';
import { Icon, type IconName } from '../../components/ui/Icon';
import { useMotionPreference } from '../../lib/motion';
import { Reveal } from './Reveal';
import './AgentShowcase.css';

const AGENT_ICONS: Record<AgentId, IconName> = {
  orchestrator: 'orchestrator',
  retrieval: 'retrieval',
  memory: 'memory',
  verification: 'verification',
};

const specialists = AGENT_CATALOG.filter((agent) => agent.kind === 'specialist');
const orchestrator = AGENT_CATALOG.find((agent) => agent.kind === 'orchestrator')!;

export function AgentShowcase(): JSX.Element {
  const [selected, setSelected] = useState<AgentId>('retrieval');
  const reduced = useMotionPreference();
  const active = AGENT_CATALOG.find((agent) => agent.id === selected)!;

  return (
    <section className="agents-show" id="agents" aria-labelledby="agents-show-heading">
      <Reveal>
      <div className="agents-show__head">
        <p className="eyebrow">Four roles, one request</p>
        <h2 className="agents-show__title display" id="agents-show-heading">
          Specialists with
          <br />
          narrow mandates.
        </h2>
        <p className="agents-show__lede">
          MNEMOS does not have one model that does everything badly. It has four roles with
          written boundaries — and a specialist that cannot find evidence is required to say
          nothing rather than invent something.
        </p>
      </div>
      </Reveal>

      <Reveal>
      <div className="agents-show__grid">
        <div className="agents-show__diagram" role="group" aria-label="Agent topology">
          <div className="agents-show__orchestrator">
            <button
              type="button"
              className={`agent-node agent-node--orchestrator ${
                selected === 'orchestrator' ? 'is-active' : ''
              }`}
              onClick={() => setSelected('orchestrator')}
              aria-pressed={selected === 'orchestrator'}
            >
              <span className="agent-node__icon">
                <Icon name="orchestrator" size={20} />
              </span>
              <span className="agent-node__text">
                <span className="agent-node__name">{orchestrator.name}</span>
                <span className="agent-node__role">Coordination · composition</span>
              </span>
            </button>
          </div>

          {/* Connectors. Drawn in SVG so their curvature is consistent at any
              width; the active path animates a dash offset. */}
          <svg
            className="agents-show__wires"
            viewBox="0 0 600 90"
            preserveAspectRatio="none"
            aria-hidden="true"
          >
            {specialists.map((agent, index) => {
              const x = [100, 300, 500][index];
              const isActive = selected === agent.id;
              return (
                <g key={agent.id} className={isActive ? 'is-active' : ''}>
                  <path
                    className="agents-show__wire agents-show__wire--base"
                    d={`M300 4 C300 40, ${x} 34, ${x} 86`}
                  />
                  <path
                    className="agents-show__wire agents-show__wire--flow"
                    d={`M300 4 C300 40, ${x} 34, ${x} 86`}
                    style={{ animationPlayState: reduced ? 'paused' : 'running' }}
                  />
                </g>
              );
            })}
          </svg>

          <div className="agents-show__specialists">
            {specialists.map((agent) => (
              <button
                key={agent.id}
                type="button"
                className={`agent-node agent-node--specialist ${
                  selected === agent.id ? 'is-active' : ''
                }`}
                onClick={() => setSelected(agent.id)}
                aria-pressed={selected === agent.id}
              >
                <span className="agent-node__icon">
                  <Icon name={AGENT_ICONS[agent.id]} size={18} />
                </span>
                <span className="agent-node__text">
                  <span className="agent-node__name">{agent.name}</span>
                </span>
              </button>
            ))}
          </div>
        </div>

        <div className="agents-show__detail" aria-live="polite">
          <div className="agents-show__detail-head">
            <span className="agents-show__detail-icon">
              <Icon name={AGENT_ICONS[active.id]} size={18} />
            </span>
            <div>
              <h3 className="agents-show__detail-name">{active.name}</h3>
              <p className="agents-show__detail-kind">
                {active.kind === 'orchestrator' ? 'Orchestrator' : 'Specialist'}
              </p>
            </div>
          </div>

          <p className="agents-show__detail-summary">{active.summary}</p>

          <div className="agents-show__detail-block">
            <h4 className="agents-show__detail-label">Responsibilities</h4>
            <ul className="agents-show__list">
              {active.responsibilities.map((item) => (
                <li key={item}>
                  <span className="agents-show__li-mark" aria-hidden="true" />
                  {item}
                </li>
              ))}
            </ul>
          </div>

          <div className="agents-show__detail-block">
            <h4 className="agents-show__detail-label">Hard boundaries</h4>
            <ul className="agents-show__list agents-show__list--boundary">
              {active.boundaries.map((item) => (
                <li key={item}>
                  <span className="agents-show__li-mark" aria-hidden="true" />
                  {item}
                </li>
              ))}
            </ul>
          </div>

          <p className="agents-show__detail-status">
            <span className="agents-show__status-dot" aria-hidden="true" />
            Executable through the orchestrator. This panel documents the
            contract; it does not start anything.
          </p>
        </div>
      </div>
      </Reveal>
    </section>
  );
}
