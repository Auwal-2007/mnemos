import './DashboardTimeline.css';

interface TimelineProps {
  total: number;
  ready: number;
  extracted: number;
  failed: number;
  processing: number;
  enabled: boolean;
}

/**
 * A proportional picture of where the corpus sits in the pipeline.
 *
 * This is a *stacked bar plus stage list*, not a time-series chart: there is
 * no historical data to plot, and drawing an axis that implies history would
 * be invention. The bar is divided into real current states only, and a stage
 * with zero sources is shown as empty rather than omitted, so the shape of
 * the pipeline stays visible.
 */
export function DashboardTimeline({
  total,
  ready,
  extracted,
  failed,
  processing,
  enabled,
}: TimelineProps): JSX.Element {
  const stages = [
    { id: 'ready', label: 'Ready to search', count: ready, tone: 'accent' },
    { id: 'extracted', label: 'Extracted, not indexed', count: extracted, tone: 'brass' },
    { id: 'processing', label: 'Processing', count: processing, tone: 'neutral' },
    { id: 'failed', label: 'Failed', count: failed, tone: 'danger' },
  ];

  if (!enabled) {
    return (
      <p className="timeline__inert">
        The pipeline view appears once you are signed in with a workspace.
      </p>
    );
  }

  if (total === 0) {
    return (
      <p className="timeline__inert">
        No sources yet, so every stage is empty. Add one to watch it move through extraction and
        indexing.
      </p>
    );
  }

  return (
    <div className="timeline">
      <div
        className="timeline__bar"
        role="img"
        aria-label={`Corpus state: ${stages
          .map((stage) => `${stage.count} ${stage.label.toLowerCase()}`)
          .join(', ')}`}
      >
        {stages
          .filter((stage) => stage.count > 0)
          .map((stage) => (
            <span
              key={stage.id}
              className={`timeline__segment timeline__segment--${stage.tone}`}
              style={{ flexGrow: stage.count }}
            />
          ))}
      </div>

      <ul className="timeline__legend" role="list">
        {stages.map((stage) => (
          <li key={stage.id} className="timeline__legend-item">
            <span className={`timeline__swatch timeline__swatch--${stage.tone}`} aria-hidden="true" />
            <span className="timeline__legend-label">{stage.label}</span>
            <span className="timeline__legend-count" data-numeric>
              {stage.count}
            </span>
            <span className="timeline__legend-pct" data-numeric>
              {total ? `${Math.round((stage.count / total) * 100)}%` : '—'}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
