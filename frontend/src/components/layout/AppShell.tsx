import { useEffect, useState } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { useMediaQuery } from '../../lib/hooks';
import { Sidebar } from './Sidebar';
import { MobileNav } from './MobileNav';
import './AppShell.css';

/**
 * Top-level application layout.
 * Desktop: persistent collapsible sidebar + content column.
 * Mobile:  top bar + slide-in drawer + bottom navigation.
 */
export function AppShell(): JSX.Element {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const location = useLocation();

  // Below 1024px the rail is 72px wide regardless of the user's preference,
  // so the component must render icon-only to avoid clipped labels.
  const isTablet = useMediaQuery('(max-width: 1023px)');
  const effectiveCollapsed = sidebarCollapsed || isTablet;

  // Close the mobile drawer whenever navigation occurs.
  useEffect(() => {
    setDrawerOpen(false);
  }, [location.pathname]);

  // Lock body scroll while the drawer is open.
  useEffect(() => {
    if (!drawerOpen) return undefined;
    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = previous;
    };
  }, [drawerOpen]);

  return (
    <div className={`shell ${effectiveCollapsed ? 'shell--collapsed' : ''}`}>
      <a className="skip-link" href="#main-content">
        Skip to main content
      </a>

      <div className="shell__sidebar">
        <Sidebar
          collapsed={effectiveCollapsed}
          onToggleCollapsed={() => setSidebarCollapsed((value) => !value)}
          canToggle={!isTablet}
        />
      </div>

      <MobileNav open={drawerOpen} onClose={() => setDrawerOpen(false)} />

      <div className="shell__main">
        <MobileTopBar onOpenDrawer={() => setDrawerOpen(true)} />
        <main id="main-content" className="shell__content" tabIndex={-1}>
          <Outlet />
        </main>
      </div>
    </div>
  );
}

function MobileTopBar({ onOpenDrawer }: { onOpenDrawer: () => void }): JSX.Element {
  return (
    <header className="mobile-topbar">
      <button
        type="button"
        className="mobile-topbar__menu"
        onClick={onOpenDrawer}
        aria-label="Open navigation menu"
        aria-expanded={false}
      >
        <MenuIcon />
      </button>
      <span className="mobile-topbar__brand">MNEMOS</span>
    </header>
  );
}

function MenuIcon(): JSX.Element {
  return (
    <svg
      width="20"
      height="20"
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      aria-hidden="true"
    >
      <path d="M3 5h14M3 10h14M3 15h14" />
    </svg>
  );
}
