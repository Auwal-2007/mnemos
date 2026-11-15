import { useCountUp } from './useCountUp';
import './KpiStrip.css';

interface Counts {
  total: number;
  ready: number;
  processing: number;
  failed: number;
  extracted: number;
}

interface KpiStripProps {
  counts: Counts;
  loading: boolean;
  hasWorkspace: boolean;
}

/**
 * Four counts from the corpus.
 *
 * They are rendered as a *strip with a shared baseline* rather than four
 * floating cards, so they read as one measurement of one system. Numbers
 * animate up from zero on first paint only when motion is allowed; the value
 * itself always comes from the API and never from a constant.
 */
export function KpiStrip({ counts, loading, hasWorkspace }: KpiStripProps): JSX.Element {
  const items = [
    {
      key: 'total',
      label: 'Sources',
      value: counts.total,
      note: 'stored in this workspace',
      tone: 'neutral' as const,
    },
    {
      key: 'ready',
      label: 'Searchable',
      value: counts.ready,
      note: counts.total ? `${Math.round((counts.ready / counts.total) * 100)}% of corpus` : 'nothing indexed yet',
      tone: 'accent' as const,
    },
    {
      key: 'processing',
      label: 'In pipeline',
      value: counts.processing,
      note: counts.processing ? 'being processed now' : 'idle',
      tone: 'brass' as const,
    },
    {
      key: 'failed',
      label: 'Needs attention',
      value: counts.failed,
      note: counts.failed ? 'open to see why' : 'no failures',
      tone: counts.failed > 0 ? ('danger' as const) : ('neutral' as const),
    },
  ];

  return (
    <section className="kpi" aria-label="Corpus summary">
      {items.map((item) => (
        <div key={item.key} className={`kpi__item kpi__item--${item.tone}`}>
          <span className="kpi__label">{item.label}</span>
          <span className="kpi__value" data-numeric>
            {!hasWorkspace ? (
              <span className="kpi__empty">—</span>
            ) : loading ? (
              <span className="kpi__pending" aria-hidden="true" />
            ) : (
              <Count value={item.value} />
            )}
          </span>
          <span className="kpi__note">{item.note}</span>
          <span className="kpi__rule" aria-hidden="true" />
        </div>
      ))}
    </section>
  );
}

function Count({ value }: { value: number }): JSX.Element {
  const display = useCountUp(value);
  return <>{display.toLocaleString()}</>;
}
