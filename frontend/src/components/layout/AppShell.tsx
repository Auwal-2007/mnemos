import { useEffect, useState } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { AnimatePresence, motion } from 'framer-motion';
import { pageVariants, useMotionPreference } from '../../lib/motion';
import { useMediaQuery } from '../../lib/hooks';
import { Sidebar } from './Sidebar';
import { MobileNav } from './MobileNav';
import { CommandPalette } from './CommandPalette';
import { MnemosMark } from '../brand/MnemosMark';
import { Icon } from '../ui/Icon';
import './AppShell.css';

/**
 * Top-level product layout.
 * Desktop: persistent collapsible sidebar + content column.
 * Mobile:  compact top bar + slide-in drawer + bottom navigation.
 *
 * Nav labels are decided by the *effective* rail width, not the user's stored
 * preference, because below 1024px the rail is 68px regardless.
 */
export function AppShell(): JSX.Element {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const location = useLocation();
  const reduced = useMotionPreference();
  const variants = pageVariants(reduced);

  const isTablet = useMediaQuery('(max-width: 1023px)');
  const isMobile = useMediaQuery('(max-width: 767px)');
  const effectiveCollapsed = sidebarCollapsed || isTablet;

  useEffect(() => {
    setDrawerOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    if (!drawerOpen) return undefined;
    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = previous;
    };
  }, [drawerOpen]);

  // Global palette shortcut. Meta on macOS, Control elsewhere; both work.
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent): void => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        setPaletteOpen((open) => !open);
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, []);

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
          onOpenPalette={() => setPaletteOpen(true)}
        />
      </div>

      <MobileNav open={drawerOpen} onClose={() => setDrawerOpen(false)} />

      <div className="shell__main">
        {/* Rendered only at mobile widths rather than hidden with CSS, so the
            accessibility tree never contains a second, invisible copy of the
            menu and search controls. */}
        {isMobile && (
          <MobileTopBar
            onOpenDrawer={() => setDrawerOpen(true)}
            onOpenPalette={() => setPaletteOpen(true)}
          />
        )}
        <main id="main-content" className="shell__content" tabIndex={-1}>
          <AnimatePresence mode="wait" initial={false}>
            <motion.div
              key={location.pathname}
              className="shell__page"
              initial={variants.initial}
              animate={variants.animate}
              exit={variants.exit}
            >
              <Outlet />
            </motion.div>
          </AnimatePresence>
        </main>
      </div>

      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
    </div>
  );
}

function MobileTopBar({
  onOpenDrawer,
  onOpenPalette,
}: {
  onOpenDrawer: () => void;
  onOpenPalette: () => void;
}): JSX.Element {
  return (
    <header className="mobile-topbar">
      <button
        type="button"
        className="mobile-topbar__menu"
        onClick={onOpenDrawer}
        aria-label="Open navigation menu"
        aria-expanded={false}
      >
        <Icon name="menu" size={18} />
      </button>

      <span className="mobile-topbar__brand">
        <MnemosMark size={16} />
        <span>MNEMOS</span>
      </span>

      <button
        type="button"
        className="mobile-topbar__search"
        onClick={onOpenPalette}
        aria-label="Search and jump to a page"
      >
        <Icon name="search" size={17} />
      </button>
    </header>
  );
}
