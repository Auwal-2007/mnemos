import { NavLink } from 'react-router-dom';
import { primaryNavigation } from '../../app/navigation';
import { useAuth } from '../../lib/auth';
import { Icon } from '../ui/Icon';
import { UserMenu } from './UserMenu';
import './Sidebar.css';

export interface SidebarProps {
  collapsed: boolean;
  onToggleCollapsed: () => void;
  /** False when the rail width is dictated by the viewport, not the user. */
  canToggle?: boolean;
}

/** Persistent desktop navigation rail. */
export function Sidebar({
  collapsed,
  onToggleCollapsed,
  canToggle = true,
}: SidebarProps): JSX.Element {
  const { status } = useAuth();

  return (
    <nav className="sidebar" aria-label="Primary">
      <div className="sidebar__header">
        <NavLink to="/" className="sidebar__brand" aria-label="MNEMOS home">
          <span className="sidebar__mark" aria-hidden="true">
            M
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
            <Icon name="chevron-left" size={16} />
          </button>
        )}
      </div>

      <ul className="sidebar__nav" role="list">
        {primaryNavigation.map((item) => (
          <li key={item.id}>
            <NavLink
              to={item.path}
              end={item.path === '/'}
              className={({ isActive }) => `sidebar__link ${isActive ? 'is-active' : ''}`}
              title={collapsed ? item.label : undefined}
            >
              <span className="sidebar__icon" aria-hidden="true">
                <Icon name={item.icon} size={18} />
              </span>
              {!collapsed && (
                <span className="sidebar__label">
                  {item.label}
                  {item.status === 'planned' && (
                    <span className="sidebar__planned" title="Planned for a later phase">
                      Planned
                    </span>
                  )}
                </span>
              )}
            </NavLink>
          </li>
        ))}
      </ul>

      <div className="sidebar__footer">
        <UserMenu collapsed={collapsed} />
        {!collapsed && status === 'unconfigured' && (
          <p className="sidebar__hint">Authentication is not configured for this deployment.</p>
        )}
      </div>
    </nav>
  );
}
