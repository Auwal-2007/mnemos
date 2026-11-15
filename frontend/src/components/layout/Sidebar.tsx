import { NavLink } from 'react-router-dom';
import { navigationGroups } from '../../app/navigation';
import { useAuth } from '../../lib/auth';
import { MnemosMark } from '../brand/MnemosMark';
import { Icon } from '../ui/Icon';
import { UserMenu } from './UserMenu';
import './Sidebar.css';

export interface SidebarProps {
  collapsed: boolean;
  onToggleCollapsed: () => void;
  /** False when the rail width is dictated by the viewport, not the user. */
  canToggle?: boolean;
  onOpenPalette?: () => void;
}

/**
 * Persistent desktop navigation rail.
 *
 * Structure carries meaning here: groups are labelled, the active item gets a
 * brass marker on the rail edge (brass = the record you are looking at), and
 * a single "planned" dot marks anything not yet executable. Collapsing hides
 * labels but keeps hit areas at 40px so the rail stays usable.
 */
export function Sidebar({
  collapsed,
  onToggleCollapsed,
  canToggle = true,
  onOpenPalette,
}: SidebarProps): JSX.Element {
  const { status } = useAuth();

  return (
    <nav className="sidebar" aria-label="Primary">
      <div className="sidebar__header">
        <NavLink to="/app" className="sidebar__brand" aria-label="MNEMOS overview">
          <span className="sidebar__mark" aria-hidden="true">
            <MnemosMark size={19} />
          </span>
          {!collapsed && <span className="sidebar__wordmark">MNEMOS</span>}
        </NavLink>
        {canToggle && (
          <button
            type="button"
            className={`sidebar__collapse ${collapsed ? 'is-collapsed' : ''}`}
            onClick={onToggleCollapsed}
            aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            aria-pressed={collapsed}
          >
            <Icon name="chevron-left" size={14} />
          </button>
        )}
      </div>

      {onOpenPalette && (
        <button
          type="button"
          className="sidebar__search"
          onClick={onOpenPalette}
          aria-label="Search and jump to a page"
        >
          <Icon name="search" size={14} />
          {!collapsed && (
            <>
              <span className="sidebar__search-label">Jump to…</span>
              <kbd className="sidebar__kbd">⌘K</kbd>
            </>
          )}
        </button>
      )}

      <div className="sidebar__groups">
        {navigationGroups.map((group) => (
          <div key={group.id} className="sidebar__group">
            {!collapsed && <p className="sidebar__group-label">{group.label}</p>}
            <ul className="sidebar__nav" role="list">
              {group.items.map((item) => (
                <li key={item.id}>
                  <NavLink
                    to={item.path}
                    end={item.path === '/app'}
                    className={({ isActive }) => `sidebar__link ${isActive ? 'is-active' : ''}`}
                    title={collapsed ? item.label : undefined}
                  >
                    <span className="sidebar__link-rail" aria-hidden="true" />
                    <span className="sidebar__icon" aria-hidden="true">
                      <Icon name={item.icon} size={17} />
                    </span>
                    {!collapsed && (
                      <span className="sidebar__label">
                        {item.label}
                        {item.status === 'planned' && (
                          <span className="sidebar__planned" title="Planned for a later phase" />
                        )}
                      </span>
                    )}
                  </NavLink>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>

      <div className="sidebar__footer">
        <UserMenu collapsed={collapsed} />
        {!collapsed && status === 'unconfigured' && (
          <p className="sidebar__hint">Authentication is not configured for this deployment.</p>
        )}
      </div>
    </nav>
  );
}
