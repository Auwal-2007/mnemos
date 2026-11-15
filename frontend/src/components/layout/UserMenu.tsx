import { useEffect, useId, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../../lib/auth';
import { useToast } from '../../app/ToastProvider';
import { Icon } from '../ui/Icon';
import './UserMenu.css';

/** Authenticated identity + account menu. Reports its real state honestly. */
export function UserMenu({ collapsed }: { collapsed: boolean }): JSX.Element {
  const { status, user, signOut, isConfigured } = useAuth();
  const { notify } = useToast();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const menuId = useId();
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return undefined;
    const onPointerDown = (event: MouseEvent): void => {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('mousedown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [open]);

  const displayName = user?.email ?? 'Not signed in';
  const initials = user?.email ? user.email.slice(0, 2).toUpperCase() : '—';

  const handleSignOut = async (): Promise<void> => {
    setBusy(true);
    try {
      await signOut();
      notify('You have been signed out.', 'success');
      navigate('/');
    } catch {
      notify('Sign out failed. Please try again.', 'error');
    } finally {
      setBusy(false);
      setOpen(false);
    }
  };

  return (
    <div className="user-menu" ref={containerRef}>
      <button
        type="button"
        className="user-menu__trigger"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-controls={menuId}
        aria-haspopup="menu"
        title={collapsed ? displayName : undefined}
      >
        <span className="user-menu__avatar" aria-hidden="true">
          {initials}
        </span>
        {!collapsed && (
          <span className="user-menu__identity">
            <span className="user-menu__name">{displayName}</span>
            <span className="user-menu__status">
              {status === 'authenticated'
                ? 'Signed in'
                : status === 'unconfigured'
                  ? 'Auth not configured'
                  : status === 'loading'
                    ? 'Checking session…'
                    : 'Signed out'}
            </span>
          </span>
        )}
      </button>

      {open && (
        <div className="user-menu__panel" id={menuId} role="menu">
          <div className="user-menu__panel-header">
            <span className="user-menu__panel-name">{displayName}</span>
            <span className="user-menu__panel-meta">
              {isConfigured ? 'Supabase Auth' : 'No auth provider configured'}
            </span>
          </div>
          <Link to="/settings" className="user-menu__item" role="menuitem" onClick={() => setOpen(false)}>
            <Icon name="settings" size={16} />
            Settings
          </Link>
          {status === 'authenticated' ? (
            <button
              type="button"
              className="user-menu__item"
              role="menuitem"
              onClick={() => void handleSignOut()}
              disabled={busy}
            >
              <Icon name="logout" size={16} />
              {busy ? 'Signing out…' : 'Sign out'}
            </button>
          ) : (
            <Link
              to="/sign-in"
              className="user-menu__item"
              role="menuitem"
              onClick={() => setOpen(false)}
            >
              <Icon name="user" size={16} />
              Sign in
            </Link>
          )}
        </div>
      )}
    </div>
  );
}
