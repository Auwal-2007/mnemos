/**
 * Feature sections.
 *
 * Deliberately *asymmetric*: each capability gets a different composition —
 * a wide editorial row, a tall offset pair, a full-bleed technical band — so
 * the page has rhythm. Repeating one three-column card grid is what makes a
 * product page look generated, so that pattern is used exactly once, and only
 * for the three small facts that genuinely are parallel.
 */

import { Icon } from '../../components/ui/Icon';
import { useTilt } from '../../lib/motion/pointer';
import { Reveal } from './Reveal';
import './FeatureSections.css';

/* -------------------------------------------------------------------------
   Band 1 — editorial split: workspace, with a real interface fragment
   ---------------------------------------------------------------------- */

function WorkspaceFragment(): JSX.Element {
  return (
    <div className="frag frag--workspace" aria-hidden="true">
      <div className="frag__bar">
        <span className="frag__dot" />
        <span className="frag__dot" />
        <span className="frag__dot" />
        <span className="frag__bar-title" data-mono>
          knowledge / sources
        </span>
      </div>
      <div className="frag__body">
        {[
          { name: 'Field notes — Lagos site survey', meta: 'PDF · 14 pages', state: 'ready' },
          { name: 'Interview: procurement lead', meta: 'Note · 2 148 chars', state: 'ready' },
          { name: 'Q3 cohort dataset', meta: 'CSV · 4 210 rows', state: 'extracted' },
        ].map((row) => (
          <div key={row.name} className="frag__row">
            <span className="frag__row-icon">
              <Icon name="document" size={14} />
            </span>
            <span className="frag__row-text">
              <span className="frag__row-name">{row.name}</span>
              <span className="frag__row-meta" data-mono>
                {row.meta}
              </span>
            </span>
            <span className={`frag__state frag__state--${row.state}`}>
              {row.state === 'ready' ? 'Indexed' : 'Not indexed'}
            </span>
          </div>
        ))}
      </div>
      <div className="frag__foot">
        <span data-mono>3 sources · 1 awaiting indexing</span>
      </div>
    </div>
  );
}

export function WorkspaceBand(): JSX.Element {
  const tilt = useTilt<HTMLDivElement>(3.5);
  return (
    <section className="band band--workspace" id="product" aria-labelledby="workspace-band-heading">
      <Reveal>
      <div className="band__inner band__inner--split">
        <div className="band__copy">
          <p className="eyebrow">01 — The archive</p>
          <h2 className="band__title display" id="workspace-band-heading">
            Everything you know,
            <br />
            in one place that remembers.
          </h2>
          <p className="band__body">
            Drop in PDFs, plain text and written notes. Each keeps its original file, its versions
            and the exact text extracted from it. Nothing is summarised away before you can see it.
          </p>
          <ul className="band__list" role="list">
            <li>
              <span className="band__li-mark" aria-hidden="true" />
              Private by construction — row-level security scopes every read to your workspace
            </li>
            <li>
              <span className="band__li-mark" aria-hidden="true" />
              Versioned, never overwritten — an upload is a new version, not a replacement
            </li>
            <li>
              <span className="band__li-mark" aria-hidden="true" />
              Honest status — processing state is read back from the database, not animated
            </li>
          </ul>
        </div>
        <div className="band__visual" ref={tilt.ref}>
          <WorkspaceFragment />
        </div>
      </div>
      </Reveal>
    </section>
  );
}

/* -------------------------------------------------------------------------
   Band 2 — reversed split with a query→evidence illustration
   ---------------------------------------------------------------------- */

function RetrievalFragment(): JSX.Element {
  return (
    <div className="frag frag--retrieval" aria-hidden="true">
      <div className="frag__bar">
        <Icon name="search" size={12} />
        <span className="frag__query">what did the survey conclude about site drainage?</span>
        <span className="frag__caret" />
      </div>
      <div className="frag__hits">
        {[
          { score: 0.91, title: 'Field notes — Lagos site survey', loc: 'p.11 · §5.1', tone: 'high' },
          { score: 0.83, title: 'Interview: procurement lead', loc: 'chars 812–904', tone: 'high' },
          { score: 0.61, title: 'Q3 cohort dataset', loc: 'p.2 · §1', tone: 'mid' },
        ].map((hit) => (
          <div key={hit.title} className="frag__hit">
            <span className="frag__hit-score" data-numeric>
              {hit.score.toFixed(2)}
            </span>
            <span className="frag__hit-body">
              <span className="frag__hit-title">{hit.title}</span>
              <span className="frag__hit-loc" data-mono>
                {hit.loc}
              </span>
            </span>
            <span className={`frag__hit-bar frag__hit-bar--${hit.tone}`} />
          </div>
        ))}
      </div>
      <div className="frag__foot">
        <span data-mono>scoped to your workspace · 3 of 3 passages shown</span>
      </div>
    </div>
  );
}

export function RetrievalBand(): JSX.Element {
  return (
    <section className="band band--retrieval" aria-labelledby="retrieval-band-heading">
      <Reveal>
      <div className="band__inner band__inner--split band__inner--reverse">
        <div className="band__copy">
          <p className="eyebrow">02 — Retrieval</p>
          <h2 className="band__title display" id="retrieval-band-heading">
            Finds the passage,
            <br />
            not just the document.
          </h2>
          <p className="band__body">
            Dense vectors answer “this is about the same thing”. Lexical search answers “this
            contains that exact term”. Both run, then their rankings are fused — because one alone
            always has a blind spot.
          </p>
          <ul className="band__list" role="list">
            <li>
              <span className="band__li-mark" aria-hidden="true" />
              pgvector cosine similarity alongside PostgreSQL full-text search
            </li>
            <li>
              <span className="band__li-mark" aria-hidden="true" />
              Ranked fusion rather than trusting a single score, which favours popularity
            </li>
            <li>
              <span className="band__li-mark" aria-hidden="true" />
              Every hit carries a chunk id, so it resolves to a quotable position
            </li>
          </ul>
        </div>
        <div className="band__visual">
          <RetrievalFragment />
        </div>
      </div>
      </Reveal>
    </section>
  );
}

/* -------------------------------------------------------------------------
   Band 3 — technical band, full-bleed, three columns (used once)
   ---------------------------------------------------------------------- */

const PILLARS = [
  {
    icon: 'lock' as const,
    title: 'Your data stays yours',
    body: 'Supabase row-level security is enforced in the database, not in application code that could be bypassed.',
  },
  {
    icon: 'fingerprint' as const,
    title: 'Deterministic by default',
    body: 'Chunking is reproducible, configuration is recorded per chunk, and an index can be rebuilt identically.',
  },
  {
    icon: 'eye' as const,
    title: 'No invented certainty',
    body: 'Confidence is reported only where evidence exists. An empty result is a valid answer, not a failure.',
  },
];

export function PillarsBand(): JSX.Element {
  return (
    <section className="pillars" aria-labelledby="pillars-heading">
      <Reveal>
      <div className="pillars__inner">
        <div className="pillars__head">
          <p className="eyebrow">Principles</p>
          <h2 className="pillars__title display" id="pillars-heading">
            Built to be trusted
            <br />
            with things that matter.
          </h2>
        </div>
        <ul className="pillars__grid" role="list">
          {PILLARS.map((pillar) => (
            <li key={pillar.title} className="pillar">
              <span className="pillar__icon">
                <Icon name={pillar.icon} size={17} />
              </span>
              <h3 className="pillar__title">{pillar.title}</h3>
              <p className="pillar__body">{pillar.body}</p>
            </li>
          ))}
        </ul>
      </div>
      </Reveal>
    </section>
  );
}
