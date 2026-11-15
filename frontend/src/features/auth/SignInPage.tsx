import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../../lib/auth';
import { Button } from '../../components/ui/Button';
import { Spinner } from '../../components/ui/Spinner';
import { Icon } from '../../components/ui/Icon';
import { MnemosMark } from '../../components/brand/MnemosMark';
import './SignInPage.css';

/** Real Supabase email/password sign-in. States unavailability honestly. */
export function SignInPage(): JSX.Element {
  const { status, isConfigured, signInWithPassword, signUpWithPassword } = useAuth();
  const navigate = useNavigate();
  const [mode, setMode] = useState<'sign-in' | 'sign-up'>('sign-in');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const shell = (content: JSX.Element): JSX.Element => (
    <div className="auth-page">
      <aside className="auth-page__panel" aria-label="About MNEMOS">
        <Link to="/" className="auth-page__brand">
          <MnemosMark size={20} />
          <span className="auth-page__brand-word">MNEMOS</span>
        </Link>

        <div className="auth-page__pitch">
          <p className="auth-page__pitch-title">
            Answers that show
            <br />
            their sources.
            <br />
            <em>Memory that remembers.</em>
          </p>
          <p className="auth-page__pitch-body">
            Your documents, notes and revisions become one corpus you can question — with the
            exact passage behind every claim.
          </p>
          <ul className="auth-page__pitch-points" role="list">
            <li>
              <Icon name="lock" size={13} />
              Row-level security scopes every read to your own workspace.
            </li>
            <li>
              <Icon name="fingerprint" size={13} />
              Citations resolve to a character range in a specific version.
            </li>
            <li>
              <Icon name="info" size={13} />
              No capability is implied that is not built. The interface says what is real.
            </li>
          </ul>
        </div>

        <p className="auth-card__eyebrow" style={{ margin: 0 }}>
          v0.1.0 · under active development
        </p>
      </aside>

      <div className="auth-page__form-side">{content}</div>
    </div>
  );

  const handleSubmit = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    setError(null);
    setNotice(null);
    setSubmitting(true);
    try {
      if (mode === 'sign-in') {
        await signInWithPassword(email, password);
        navigate('/');
      } else {
        const result = await signUpWithPassword(email, password);
        setNotice(
          result.needsConfirmation
            ? 'Check your inbox to confirm the address, then sign in.'
            : 'Account created. You are signed in.',
        );
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Authentication failed.');
    } finally {
      setSubmitting(false);
    }
  };

  if (!isConfigured) {
    return shell(
      <div className="auth-card">
        <p className="auth-card__eyebrow">Not configured</p>
        <h1 className="auth-card__title">Authentication is unavailable</h1>
        <p className="auth-card__body">
          This deployment has no Supabase credentials, so accounts cannot be created or used yet.
          Set <code>VITE_SUPABASE_URL</code> and <code>VITE_SUPABASE_ANON_KEY</code>, then reload.
        </p>
        <Link to="/" className="auth-card__back">
          Return to the public site
        </Link>
      </div>,
    );
  }

  if (status === 'loading') {
    return shell(
      <div className="auth-card auth-card--center">
        <Spinner label="Checking session" />
      </div>,
    );
  }

  if (status === 'authenticated') {
    return shell(
      <div className="auth-card">
        <p className="auth-card__eyebrow">Session active</p>
        <h1 className="auth-card__title">You are already signed in</h1>
        <p className="auth-card__body">
          Your corpus is loaded and editable. Continue to the workspace.
        </p>
        <Link to="/app" className="auth-card__primary-link">
          Open your workspace
        </Link>
      </div>,
    );
  }

  return shell(
    <div className="auth-card">
        <p className="auth-card__eyebrow">{mode === 'sign-in' ? 'Welcome back' : 'Get started'}</p>
        <h1 className="auth-card__title">{mode === 'sign-in' ? 'Sign in' : 'Create an account'}</h1>
        <p className="auth-card__body">
          Identity is managed by Supabase Auth. Credentials are sent directly to Supabase over TLS and
          are never stored by this application.
        </p>

        <form className="auth-form" onSubmit={(event) => void handleSubmit(event)} noValidate>
          <div className="auth-field">
            <label className="auth-field__label" htmlFor="auth-email">
              Email
            </label>
            <input
              id="auth-email"
              className="auth-field__input"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </div>
          <div className="auth-field">
            <label className="auth-field__label" htmlFor="auth-password">
              Password
            </label>
            <input
              id="auth-password"
              className="auth-field__input"
              type="password"
              autoComplete={mode === 'sign-in' ? 'current-password' : 'new-password'}
              required
              minLength={8}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </div>

          {error && (
            <p className="auth-message auth-message--error" role="alert">
              {error}
            </p>
          )}
          {notice && (
            <p className="auth-message auth-message--notice" role="status">
              {notice}
            </p>
          )}

          <Button type="submit" variant="primary" size="lg" fullWidth loading={submitting}>
            {mode === 'sign-in' ? 'Sign in' : 'Create account'}
          </Button>
        </form>

        <button
          type="button"
          className="auth-switch"
          onClick={() => {
            setMode(mode === 'sign-in' ? 'sign-up' : 'sign-in');
            setError(null);
            setNotice(null);
          }}
        >
          {mode === 'sign-in' ? 'Need an account? Create one' : 'Have an account? Sign in'}
        </button>

        <Link to="/" className="auth-card__back">
          Back to the public site
        </Link>
      </div>,
  );
}
