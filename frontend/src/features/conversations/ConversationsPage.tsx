import { Link } from 'react-router-dom';
import { PageContainer } from '../../components/layout/PageContainer';
import { PageHeader } from '../../components/layout/PageHeader';
import { Badge } from '../../components/ui/Badge';
import { AGENT_CATALOG } from '../agents/agentCatalog';
import './ConversationsPage.css';

/** Entry point to both conversation modes. */
export function ConversationsPage(): JSX.Element {
  return (
    <PageContainer width="default">
      <PageHeader
        eyebrow="Conversations"
        title="Talk to MNEMOS"
        description="Two modes are supported by the interface: one conversation with the orchestrator, or a direct line to a specialist. Neither is connected to a model yet."
      />

      <div className="conv-modes">
        <section className="conv-mode" aria-labelledby="mode-orchestrated">
          <div className="conv-mode__head">
            <h2 className="conv-mode__title" id="mode-orchestrated">
              Orchestrated
            </h2>
            <Badge tone="accent">Mode A</Badge>
          </div>
          <p className="conv-mode__body">
            You ask once. The orchestrator is intended to consult the specialists, reconcile their
            findings and answer with citations.
          </p>
          <Link to="/conversations/orchestrator" className="conv-mode__link">
            Open orchestrator interface
            <span aria-hidden="true">→</span>
          </Link>
        </section>

        <section className="conv-mode" aria-labelledby="mode-direct">
          <div className="conv-mode__head">
            <h2 className="conv-mode__title" id="mode-direct">
              Direct specialist
            </h2>
            <Badge tone="neutral">Mode B</Badge>
          </div>
          <p className="conv-mode__body">
            You choose the specialist and work with that single role — useful when you know exactly
            which job you need done.
          </p>
          <ul className="conv-mode__agents" role="list">
            {AGENT_CATALOG.filter((agent) => agent.kind === 'specialist').map((agent) => (
              <li key={agent.id}>
                <Link to={`/conversations/agent/${agent.id}`} className="conv-mode__agent-link">
                  <span>{agent.name}</span>
                  <span aria-hidden="true">→</span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      </div>

      <section className="conv-history" aria-labelledby="history-heading">
        <h2 className="conv-history__title" id="history-heading">
          Conversation history
        </h2>
        <div className="conv-history__empty">
          <p className="conv-history__empty-title">No conversations recorded</p>
          <p className="conv-history__empty-body">
            Persistence is not implemented yet. When conversations can be stored, they will be
            listed here — this area is never populated with sample data.
          </p>
        </div>
      </section>
    </PageContainer>
  );
}
