import { NavLink } from 'react-router-dom';
import { navigationGroups, primaryNavigation } from '../../app/navigation';
import { Icon } from '../ui/Icon';
import { UserMenu } from './UserMenu';
import { MnemosMark } from '../brand/MnemosMark';
import './MobileNav.css';

export interface MobileNavProps {
  open: boolean;
  onClose: () => void;
}

/**
 * Mobile navigation: a slide-in drawer with full labels plus a persistent
 * bottom bar for the four primary destinations.
 */
export function MobileNav({ open, onClose }: MobileNavProps): JSX.Element {
  return (
    <>
      {open && (
        <div className="drawer__scrim" onClick={onClose} role="presentation" aria-hidden="true" />
      )}
      <aside
        className={`drawer ${open ? 'drawer--open' : ''}`}
        aria-label="Navigation menu"
        aria-hidden={!open}
        // Inert-like behaviour without relying on the experimental attribute.
        {...(open ? {} : { style: { visibility: 'hidden' } })}
      >
        <div className="drawer__header">
          <span className="drawer__brand">
            <MnemosMark size={17} />
            MNEMOS
          </span>
          <button
            type="button"
            className="drawer__close"
            onClick={onClose}
            aria-label="Close navigation menu"
          >
            <Icon name="close" size={18} />
          </button>
        </div>

        <div className="drawer__groups">
          {navigationGroups.map((group) => (
            <div key={group.id} className="drawer__group">
              <p className="drawer__group-label">{group.label}</p>
              <ul className="drawer__nav" role="list">
                {group.items.map((item) => (
                  <li key={item.id}>
                    <NavLink
                      to={item.path}
                      end={item.path === '/app'}
                      onClick={onClose}
                      className={({ isActive }) => `drawer__link ${isActive ? 'is-active' : ''}`}
                    >
                      <span className="drawer__icon" aria-hidden="true">
                        <Icon name={item.icon} size={18} />
                      </span>
                      <span>{item.label}</span>
                      {item.status === 'planned' && <span className="drawer__planned">Planned</span>}
                    </NavLink>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="drawer__footer">
          <UserMenu collapsed={false} />
        </div>
      </aside>

      <nav className="bottom-nav" aria-label="Primary mobile">
        {primaryNavigation
          .filter((item) => ['home', 'knowledge', 'conversations', 'agents'].includes(item.id))
          .map((item) => (
            <NavLink
              key={item.id}
              to={item.path}
              end={item.path === '/app'}
              className={({ isActive }) => `bottom-nav__link ${isActive ? 'is-active' : ''}`}
            >
              <Icon name={item.icon} size={18} />
              <span className="bottom-nav__label">{item.label.split(' ')[0]}</span>
            </NavLink>
          ))}
      </nav>
    </>
  );
}
