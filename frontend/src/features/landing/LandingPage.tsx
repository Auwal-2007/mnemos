import { lazy, Suspense } from 'react';
import { Link } from 'react-router-dom';
import { MarketingShell } from '../../components/layout/MarketingShell';
import { MnemosMark } from '../../components/brand/MnemosMark';
import { Icon } from '../../components/ui/Icon';
import { useAuth } from '../../lib/auth';
import { useSpotlight } from '../../lib/motion/pointer';
import { AgentShowcase } from './AgentShowcase';
import { WorkspaceBand, RetrievalBand, PillarsBand } from './FeatureSections';
import { ProductDemo } from './ProductDemo';
import { ProvenanceShowcase } from './ProvenanceShowcase';
import './LandingPage.css';

/**
 * The 3D hero is the single heaviest asset on the public site, so it is split
 * out and fetched only after first paint. Until it resolves, the hero shows
 * its CSS/SVG composition — which is a designed fallback, not a hole.
 */
const HeroOrbit = lazy(async () => {
  const module = await import('./HeroOrbit');
  return { default: module.HeroOrbit };
});

const CAPABILITIES = [
  'Personal knowledge workspace',
  'Hybrid retrieval',
  'Evidence-backed answers',
  'Revision-aware memory',
  'Specialist agents',
  'Source provenance',
];

export function LandingPage(): JSX.Element {
  const { status } = useAuth();
  const heroSpot = useSpotlight<HTMLDivElement>();
  const signedIn = status === 'authenticated';
  const entry = signedIn ? '/app' : '/sign-in';

  return (
    <MarketingShell>
      <div className="landing">
        {/* ------------------------------ Hero ------------------------------ */}
        <section className="hero" ref={heroSpot.ref} aria-labelledby="hero-heading">
          <div className="hero__veil" aria-hidden="true" />
          <div className="hero__grid" aria-hidden="true" />

          <div className="hero__inner">
            <div className="hero__copy">
              <div className="hero__badge">
                <span className="hero__badge-dot" aria-hidden="true" />
                <span>Knowledge intelligence · under active development</span>
              </div>

              <h1 className="hero__title display" id="hero-heading">
                Your knowledge
                <br />
                deserves more than
                <br />
                <span className="hero__title-em">a search bar.</span>
              </h1>

              <p className="hero__lede">
                MNEMOS is a personal knowledge instrument. It keeps what you have read and written,
                answers from it with the exact passages that support each claim, and never forgets
                that it changed its mind.
              </p>

              <div className="hero__actions">
                <Link to={entry} className="hero__cta hero__cta--primary">
                  {signedIn ? 'Open your workspace' : 'Enter MNEMOS'}
                  <Icon name="arrow-right" size={16} />
                </Link>
                <a href="#how" className="hero__cta hero__cta--ghost">
                  <Icon name="play" size={13} />
                  See how it works
                </a>
              </div>

              <p className="hero__fineprint">
                <Icon name="lock" size={12} />
                Your sources stay in your own Supabase project. No phrase you type leaves it to
                build an ad profile — there are no ads here.
              </p>
            </div>

            <div className="hero__visual">
              <div className="hero__visual-frame">
                <Suspense fallback={<div className="hero__visual-skeleton" aria-hidden="true" />}>
                  <HeroOrbit />
                </Suspense>
                <div className="hero__visual-labels" aria-hidden="true">
                  <span className="hero__label hero__label--a">sources</span>
                  <span className="hero__label hero__label--b">evidence</span>
                  <span className="hero__label hero__label--c">answer</span>
                </div>
              </div>
              <p className="hero__visual-caption">
                <Icon name="info" size={12} />
                A rendering of how material consolidates. Not a live session.
              </p>
            </div>
          </div>

          <div className="hero__marquee" aria-hidden="true">
            <div className="hero__marquee-track">
              {[...CAPABILITIES, ...CAPABILITIES].map((item, index) => (
                <span key={`${item}-${index}`} className="hero__marquee-item">
                  <MnemosMark size={11} />
                  {item}
                </span>
              ))}
            </div>
          </div>
        </section>

        {/* ------------------------- Product demonstration ------------------------- */}
        <ProductDemo />

        {/* ---------------------------- Feature bands ----------------------------- */}
        <WorkspaceBand />
        <RetrievalBand />
        <AgentShowcase />
        <ProvenanceShowcase />
        <PillarsBand />

        {/* ------------------------------- Final CTA ------------------------------- */}
        <section className="closing" aria-labelledby="closing-heading">
          <div className="closing__inner">
            <div className="closing__glow" aria-hidden="true" />
            <p className="eyebrow">Start here</p>
            <h2 className="closing__title display" id="closing-heading">
              Give your reading
              <br />
              somewhere to accumulate.
            </h2>
            <p className="closing__lede">
              Create a workspace, add a handful of sources, and watch them become a corpus you can
              question — with the receipts attached.
            </p>
            <div className="closing__actions">
              <Link to={entry} className="hero__cta hero__cta--primary">
                {signedIn ? 'Open your workspace' : 'Create your workspace'}
                <Icon name="arrow-right" size={16} />
              </Link>
              <Link to="/app/agents" className="hero__cta hero__cta--ghost">
                <Icon name="agents" size={15} />
                Read the agent contracts
              </Link>
            </div>
            <p className="closing__note">
              No credit card. No model calls are made until you configure a provider.
            </p>
          </div>
        </section>
      </div>
    </MarketingShell>
  );
}
