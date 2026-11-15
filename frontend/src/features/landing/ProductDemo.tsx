/**
 * ProductDemo — a controlled illustration of the pipeline.
 *
 * IMPORTANT: this is a diagram, not an execution. Nothing here calls the API,
 * no model runs, and the panel says so in its own words ("illustrated
 * walkthrough"). The numbers shown are fixed and describe the example
 * document, never a live system.
 *
 * Step data mirrors the actual implemented pipeline (validate → extract →
 * chunk → embed → retrieve → compose → verify → remember) so the illustration
 * cannot drift from what the product claims to do without someone noticing.
 */

import { useEffect, useState } from 'react';
import { useMotionPreference } from '../../lib/motion';
import { Icon, type IconName } from '../../components/ui/Icon';
import { Reveal } from './Reveal';
import './ProductDemo.css';

interface Step {
  id: string;
  ordinal: string;
  title: string;
  detail: string;
  /** Which part of the system performs this, in the product's own vocabulary. */
  actor: string;
  icon: IconName;
  phase: 'implemented' | 'planned';
}

const STEPS: Step[] = [
  {
    id: 'ingest',
    ordinal: '01',
    title: 'A document enters the archive',
    detail:
      'The original file is stored privately and never modified. A content hash is taken so an identical upload is recognised rather than duplicated.',
    actor: 'Ingestion service',
    icon: 'upload',
    phase: 'implemented',
  },
  {
    id: 'extract',
    ordinal: '02',
    title: 'Text is extracted, with its coordinates',
    detail:
      'Every character carries its page and offset, so a quote can later be traced to an exact position in an exact version.',
    actor: 'Extraction',
    icon: 'document',
    phase: 'implemented',
  },
  {
    id: 'index',
    ordinal: '03',
    title: 'Knowledge is chunked and indexed',
    detail:
      'Deterministic passage windows are embedded and stored as vectors. The chunking configuration is recorded on every chunk, so the corpus can be rebuilt identically.',
    actor: 'Indexing service',
    icon: 'layers',
    phase: 'implemented',
  },
  {
    id: 'retrieve',
    ordinal: '04',
    title: 'An agent retrieves evidence',
    detail:
      'The Retrieval Specialist searches only inside your workspace, ranking passages by similarity and lexical match, and returns them with source identifiers.',
    actor: 'Retrieval Specialist',
    icon: 'retrieval',
    phase: 'planned',
  },
  {
    id: 'orchestrate',
    ordinal: '05',
    title: 'The orchestrator coordinates',
    detail:
      'One request is decomposed, specialists are consulted in parallel where they do not depend on each other, and their findings are reconciled into a single position.',
    actor: 'MNEMOS Orchestrator',
    icon: 'orchestrator',
    phase: 'planned',
  },
  {
    id: 'answer',
    ordinal: '06',
    title: 'An answer arrives with its sources',
    detail:
      'Each claim carries the passages that support it. Where evidence is thin, the answer says so instead of filling the gap.',
    actor: 'Composition',
    icon: 'quote',
    phase: 'planned',
  },
  {
    id: 'remember',
    ordinal: '07',
    title: 'A revision is recorded',
    detail:
      'When something changes, the prior statement is superseded rather than deleted. Ask the same question next month and you can see what changed and why.',
    actor: 'Memory Specialist',
    icon: 'supersede',
    phase: 'planned',
  },
];

/** Total run time of the auto-advance cycle, in ms. */
const CYCLE_MS = 4200;

export function ProductDemo(): JSX.Element {
  const [active, setActive] = useState(0);
  const [playing, setPlaying] = useState(true);
  const reduced = useMotionPreference();

  useEffect(() => {
    if (!playing || reduced) return undefined;
    const timer = window.setTimeout(() => {
      setActive((current) => (current + 1) % STEPS.length);
    }, CYCLE_MS);
    return () => window.clearTimeout(timer);
  }, [active, playing, reduced]);

  const step = STEPS[active];

  return (
    <section className="demo" id="how" aria-labelledby="demo-heading">
      <Reveal className="demo__head-wrap">
      <div className="demo__head">
        <p className="eyebrow">Illustrated walkthrough</p>
        <h2 className="demo__title display" id="demo-heading">
          What actually happens
          <br />
          when you ask.
        </h2>
        <p className="demo__lede">
          Follow one document from arrival to a cited answer. Steps marked{' '}
          <span className="demo__badge demo__badge--live">built</span> run today; steps marked{' '}
          <span className="demo__badge demo__badge--planned">planned</span> describe the design and
          are not yet executable in the product.
        </p>
      </div>
      </Reveal>

      <Reveal>
      <div className="demo__stage">
        <ol className="demo__rail" role="list">
          {STEPS.map((item, index) => (
            <li key={item.id}>
              <button
                type="button"
                className={`demo__step ${index === active ? 'is-active' : ''} ${
                  index < active ? 'is-past' : ''
                }`}
                onClick={() => {
                  setActive(index);
                  setPlaying(false);
                }}
                aria-current={index === active ? 'step' : undefined}
              >
                <span className="demo__step-ordinal" data-mono>
                  {item.ordinal}
                </span>
                <span className="demo__step-body">
                  <span className="demo__step-title">{item.title}</span>
                  <span className="demo__step-actor">{item.actor}</span>
                </span>
                <span
                  className={`demo__step-status demo__step-status--${item.phase}`}
                  aria-label={item.phase === 'implemented' ? 'Built' : 'Planned'}
                  title={item.phase === 'implemented' ? 'Implemented' : 'Planned'}
                />
              </button>
            </li>
          ))}
        </ol>

        <div className="demo__panel" aria-live="polite">
          <div className="demo__panel-top" key={step.id}>
            <div className="demo__panel-icon">
              <Icon name={step.icon} size={18} />
            </div>
            <div>
              <p className="demo__panel-ordinal" data-mono>
                Step {step.ordinal} / 07
              </p>
              <h3 className="demo__panel-title">{step.title}</h3>
            </div>
          </div>
          <p className="demo__panel-detail" key={`${step.id}-detail`}>
            {step.detail}
          </p>
          <div className="demo__panel-footer">
            <span className="demo__panel-actor">
              <Icon name="circled-dot" size={13} />
              {step.actor}
            </span>
            <span
              className={`demo__pill demo__pill--${step.phase === 'implemented' ? 'live' : 'planned'}`}
            >
              {step.phase === 'implemented' ? 'Implemented' : 'Planned'}
            </span>
          </div>

          {!reduced && (
            <div className="demo__progress" aria-hidden="true">
              <span
                key={active}
                className="demo__progress-bar"
                style={{
                  animationDuration: `${CYCLE_MS}ms`,
                  animationPlayState: playing ? 'running' : 'paused',
                }}
              />
            </div>
          )}
        </div>
      </div>
      </Reveal>

      <p className="demo__disclaimer">
        <Icon name="info" size={14} />
        This is a fixed illustration of the pipeline, not a live execution. No model runs on this
        page and no data is sent anywhere.
      </p>
    </section>
  );
}
