import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../../lib/auth';
import { Button } from '../../components/ui/Button';
import { Spinner } from '../../components/ui/Spinner';
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
    return (
      <div className="auth-page">
        <div className="auth-card">
          <p className="auth-card__eyebrow">MNEMOS</p>
          <h1 className="auth-card__title">Authentication is not configured</h1>
          <p className="auth-card__body">
            This deployment has no Supabase credentials, so accounts cannot be created or used yet.
            Set <code>VITE_SUPABASE_URL</code> and <code>VITE_SUPABASE_ANON_KEY</code>, then reload.
          </p>
          <Link to="/" className="auth-card__back">
            Continue to the interface
          </Link>
        </div>
      </div>
    );
  }

  if (status === 'loading') {
    return (
      <div className="auth-page">
        <div className="auth-card auth-card--center">
          <Spinner label="Checking session" />
        </div>
      </div>
    );
  }

  if (status === 'authenticated') {
    return (
      <div className="auth-page">
        <div className="auth-card">
          <h1 className="auth-card__title">You are already signed in</h1>
          <Link to="/" className="auth-card__back">
            Go to the application
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <p className="auth-card__eyebrow">MNEMOS</p>
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
          Back to the application
        </Link>
      </div>
    </div>
  );
}
