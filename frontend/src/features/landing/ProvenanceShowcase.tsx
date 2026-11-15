/**
 * ProvenanceShowcase — the distinguishing claim, shown rather than asserted.
 *
 * The illustration traces one sentence from a claim back through its chunk,
 * its exact character range, its document version, and the moment it was
 * submitted. It then shows the same claim being superseded, because the
 * interesting case is not "we store sources" but "we remember that this
 * changed and what it said before".
 *
 * The sample values are declared as illustrative in the panel itself.
 */

import { useState } from 'react';
import { Icon } from '../../components/ui/Icon';
import { Reveal } from './Reveal';
import './ProvenanceShowcase.css';

interface Trace {
  label: string;
  value: string;
  mono?: boolean;
}

const CLAIM_TRACE: Trace[] = [
  { label: 'Claim', value: '“The trial reduced median recovery time by 2.4 days.”' },
  { label: 'Passage', value: 'chunk 14 of 62 · 2 418–2 512', mono: true },
  { label: 'Version', value: 'v3 · current', mono: true },
  { label: 'Location', value: 'page 7 · §4.2 Results', mono: true },
  { label: 'Submitted', value: '12 March 2026, 09:41' },
  { label: 'Content hash', value: 'a91f…4c7e', mono: true },
];

const REVISIONS = [
  {
    id: 'v3',
    label: 'Current',
    tone: 'current' as const,
    text: 'Median recovery time reduced by 2.4 days (n=412).',
    meta: 'Revised 12 Mar 2026 · supersedes v2',
  },
  {
    id: 'v2',
    label: 'Superseded',
    tone: 'superseded' as const,
    text: 'Median recovery time reduced by 1.8 days (n=210, interim).',
    meta: 'Superseded 12 Mar 2026 by a larger cohort',
  },
  {
    id: 'v1',
    label: 'Disputed',
    tone: 'disputed' as const,
    text: 'Median recovery time reduced by 3.1 days.',
    meta: 'Flagged: conflicts with the v3 cohort result',
  },
];

export function ProvenanceShowcase(): JSX.Element {
  const [revision, setRevision] = useState(0);
  const active = REVISIONS[revision];

  return (
    <section className="prov" id="provenance" aria-labelledby="prov-heading">
      <Reveal>
      <div className="prov__inner">
        <div className="prov__copy">
          <p className="eyebrow">The part that matters</p>
          <h2 className="prov__title display" id="prov-heading">
            An answer you can
            <br />
            walk backwards.
          </h2>
          <p className="prov__lede">
            Most tools cite a document. MNEMOS cites a <em>position</em> in a <em>version</em> of a
            document — and remembers what the same claim said before it changed. When evidence is
            thin or contradictory, that is reported too.
          </p>

          <ul className="prov__points" role="list">
            {[
              {
                title: 'Claim-level, not document-level',
                body: 'Each assertion carries the passages that support it, so you can check the sentence rather than the file.',
              },
              {
                title: 'Revisions are additive',
                body: 'Nothing is overwritten. A superseded statement stays readable, marked as retired, with what replaced it.',
              },
              {
                title: 'Conflicts surface',
                body: 'When two sources disagree, both are shown and neither is silently chosen.',
              },
            ].map((point) => (
              <li key={point.title} className="prov__point">
                <span className="prov__point-mark" aria-hidden="true">
                  <Icon name="check" size={12} strokeWidth={2.2} />
                </span>
                <div>
                  <h3 className="prov__point-title">{point.title}</h3>
                  <p className="prov__point-body">{point.body}</p>
                </div>
              </li>
            ))}
          </ul>
        </div>

        <div className="prov__panel">
          <div className="prov__panel-head">
            <span className="prov__panel-label" data-mono>
              Evidence trace
            </span>
            <span className="prov__panel-sample">Illustrative example</span>
          </div>

          <div className="prov__trace">
            {CLAIM_TRACE.map((row, index) => (
              <div
                key={row.label}
                className="prov__trace-row"
                style={{ animationDelay: `${index * 55}ms` }}
              >
                <span className="prov__trace-label">{row.label}</span>
                <span className={`prov__trace-value ${row.mono ? 'prov__trace-value--mono' : ''}`}>
                  {row.value}
                </span>
                {index < CLAIM_TRACE.length - 1 && (
                  <span className="prov__trace-rail" aria-hidden="true" />
                )}
              </div>
            ))}
          </div>

          <div className="prov__revisions">
            <div className="prov__revisions-head">
              <span className="prov__panel-label" data-mono>
                Revision history
              </span>
              <span className="prov__revisions-count" data-numeric>
                {REVISIONS.length} states
              </span>
            </div>

            <div className="prov__revision-tabs" role="tablist" aria-label="Revision states">
              {REVISIONS.map((item, index) => (
                <button
                  key={item.id}
                  type="button"
                  role="tab"
                  aria-selected={index === revision}
                  className={`prov__revision-tab prov__revision-tab--${item.tone} ${
                    index === revision ? 'is-active' : ''
                  }`}
                  onClick={() => setRevision(index)}
                >
                  {item.label}
                </button>
              ))}
            </div>

            <div className={`prov__revision-card prov__revision-card--${active.tone}`}>
              <div className="prov__revision-top">
                <span className="prov__revision-id" data-mono>
                  {active.id}
                </span>
                <span className="prov__revision-status">{active.label}</span>
              </div>
              <p className="prov__revision-text">{active.text}</p>
              <p className="prov__revision-meta" data-mono>
                {active.meta}
              </p>
            </div>
          </div>
        </div>
      </div>
      </Reveal>
    </section>
  );
}
