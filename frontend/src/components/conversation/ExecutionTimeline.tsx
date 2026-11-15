import { Icon, type IconName } from '../ui/Icon';
import './ExecutionTimeline.css';

export interface ExecutionStep {
  id: string;
  actor: string;
  role: string;
  state: 'complete' | 'active' | 'pending' | 'skipped';
  detail?: string;
}

interface ExecutionTimelineProps {
  steps: ExecutionStep[];
  /** When false, the timeline is a labelled static plan rather than a trace. */
  live?: boolean;
}

const ICONS: Record<string, IconName> = {
  'MNEMOS Orchestrator': 'orchestrator',
  'Retrieval Specialist': 'retrieval',
  'Memory Management Specialist': 'memory',
  'Evidence Verification Specialist': 'verification',
};

/**
 * The delegation trace.
 *
 * Rendered only from real execution events when they exist. On the current
 * build there are none, so the component is used in `live={false}` mode: it
 * shows the planned sequence with every step explicitly marked as not run.
 * That distinction is stated in the header, not just implied by styling.
 */
export function ExecutionTimeline({ steps, live = false }: ExecutionTimelineProps): JSX.Element {
  return (
    <section className="trace" aria-labelledby="trace-heading">
      <div className="trace__head">
        <h2 className="trace__title" id="trace-heading">
          Execution
        </h2>
        <span className={`trace__mode ${live ? 'trace__mode--live' : ''}`}>
          {live ? 'Live' : 'Planned — not run'}
        </span>
      </div>

      <ol className="trace__steps" role="list">
        {steps.map((step, index) => (
          <li key={step.id} className={`trace__step trace__step--${step.state}`}>
            <span className="trace__rail" aria-hidden="true">
              <span className="trace__dot" />
              {index < steps.length - 1 && <span className="trace__line" />}
            </span>

            <span className="trace__body">
              <span className="trace__row">
                <span className="trace__actor">
                  <Icon name={ICONS[step.actor] ?? 'circled-dot'} size={14} />
                  {step.actor}
                </span>
                <span className="trace__state" data-mono>
                  {stateLabel(step.state)}
                </span>
              </span>
              <span className="trace__role">{step.role}</span>
              {step.detail && <span className="trace__detail">{step.detail}</span>}
            </span>
          </li>
        ))}
      </ol>
    </section>
  );
}

function stateLabel(state: ExecutionStep['state']): string {
  switch (state) {
    case 'complete':
      return 'done';
    case 'active':
      return 'running';
    case 'skipped':
      return 'skipped';
    default:
      return 'queued';
  }
}
