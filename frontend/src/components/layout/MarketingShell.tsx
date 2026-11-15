import { useEffect, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { MnemosLockup } from '../brand/MnemosMark';
import { useAuth } from '../../lib/auth';
import './MarketingShell.css';

interface MarketingShellProps {
  children: React.ReactNode;
}

const SECTIONS = [
  { id: 'product', label: 'Product' },
  { id: 'agents', label: 'Agents' },
  { id: 'provenance', label: 'Provenance' },
  { id: 'how', label: 'How it works' },
];

/**
 * Public site shell.
 *
 * The header changes state at two thresholds: it gains a hairline and a
 * blurred backdrop once the page has scrolled, and a scroll-progress rule
 * tracks position. Both exist to tell the visitor where they are, not to
 * decorate.
 */
export function MarketingShell({ children }: MarketingShellProps): JSX.Element {
  const [scrolled, setScrolled] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const { status } = useAuth();
  const location = useLocation();

  useEffect(() => {
    const onScroll = (): void => setScrolled(window.scrollY > 24);
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  useEffect(() => {
    setMenuOpen(false);
  }, [location.pathname]);

  const signedIn = status === 'authenticated';

  return (
    <div className="site">
      <a className="skip-link" href="#main-content">
        Skip to main content
      </a>

      <header className={`site-header ${scrolled ? 'is-scrolled' : ''}`}>
        <div className="site-header__inner">
          <Link to="/" className="site-header__brand" aria-label="MNEMOS home">
            <MnemosLockup size={20} />
          </Link>

          <nav className="site-nav" aria-label="Sections">
            {SECTIONS.map((section) => (
              <a key={section.id} className="site-nav__link" href={`#${section.id}`}>
                {section.label}
              </a>
            ))}
          </nav>

          <div className="site-header__actions">
            <Link className="site-header__ghost" to={signedIn ? '/app' : '/sign-in'}>
              {signedIn ? 'Dashboard' : 'Sign in'}
            </Link>
            <Link className="site-header__cta" to={signedIn ? '/app' : '/sign-in'}>
              {signedIn ? 'Open workspace' : 'Open MNEMOS'}
            </Link>
            <button
              type="button"
              className="site-header__menu"
              aria-label={menuOpen ? 'Close menu' : 'Open menu'}
              aria-expanded={menuOpen}
              onClick={() => setMenuOpen((open) => !open)}
            >
              <span className={`site-header__burger ${menuOpen ? 'is-open' : ''}`} aria-hidden="true">
                <span />
                <span />
              </span>
            </button>
          </div>
        </div>

        {menuOpen && (
          <div className="site-mobile-menu">
            {SECTIONS.map((section) => (
              <a
                key={section.id}
                href={`#${section.id}`}
                className="site-mobile-menu__link"
                onClick={() => setMenuOpen(false)}
              >
                {section.label}
              </a>
            ))}
            <Link className="site-mobile-menu__link" to={signedIn ? '/app' : '/sign-in'}>
              {signedIn ? 'Open workspace' : 'Sign in'}
            </Link>
          </div>
        )}
      </header>

      <main id="main-content" className="site-main">
        {children}
      </main>

      <footer className="site-footer">
        <div className="site-footer__inner">
          <div className="site-footer__brand">
            <MnemosLockup size={20} />
            <p className="site-footer__tagline">
              A personal knowledge instrument. Answers that show their sources, memory that
              remembers how it changed.
            </p>
          </div>

          <div className="site-footer__columns">
            <div className="site-footer__column">
              <h2 className="site-footer__heading">Product</h2>
              <a href="#product" className="site-footer__link">
                Overview
              </a>
              <a href="#agents" className="site-footer__link">
                Agents
              </a>
              <a href="#provenance" className="site-footer__link">
                Provenance
              </a>
              <a href="#how" className="site-footer__link">
                How it works
              </a>
            </div>
            <div className="site-footer__column">
              <h2 className="site-footer__heading">Workspace</h2>
              <Link to="/app" className="site-footer__link">
                Dashboard
              </Link>
              <Link to="/app/knowledge" className="site-footer__link">
                Knowledge
              </Link>
              <Link to="/app/agents" className="site-footer__link">
                Agent directory
              </Link>
              <Link to="/app/settings" className="site-footer__link">
                Settings
              </Link>
            </div>
            <div className="site-footer__column">
              <h2 className="site-footer__heading">Account</h2>
              <Link to="/sign-in" className="site-footer__link">
                Sign in
              </Link>
              <Link to="/sign-in" className="site-footer__link">
                Create an account
              </Link>
              <Link to="/app/system" className="site-footer__link">
                System status
              </Link>
            </div>
          </div>
        </div>

        <div className="site-footer__base">
          <p className="site-footer__legal">
            MNEMOS is under active development. Capabilities that are not yet implemented say so
            plainly, here and in the product.
          </p>
          <p className="site-footer__meta" data-mono>
            v0.1.0 · Supabase · pgvector · OpenRouter
          </p>
        </div>
      </footer>
    </div>
  );
}
