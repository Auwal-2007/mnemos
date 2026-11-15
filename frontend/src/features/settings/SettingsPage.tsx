import { PageContainer } from '../../components/layout/PageContainer';
import { PageHeader } from '../../components/layout/PageHeader';
import { useTheme, type ThemePreference } from '../../app/ThemeProvider';
import { useAuth } from '../../lib/auth';
import { config } from '../../lib/config';
import './SettingsPage.css';

const themeOptions: { value: ThemePreference; label: string }[] = [
  { value: 'system', label: 'System' },
  { value: 'light', label: 'Light' },
  { value: 'dark', label: 'Dark' },
];

/** Real, working settings: appearance and an honest environment summary. */
export function SettingsPage(): JSX.Element {
  const { preference, setPreference } = useTheme();
  const { status, user, isConfigured } = useAuth();

  return (
    <PageContainer width="default">
      <PageHeader
        eyebrow="Settings"
        title="Preferences"
        description="Appearance and deployment details. Only settings that actually work are shown."
      />

      <section className="settings-section" aria-labelledby="appearance-heading">
        <h2 className="settings-section__title" id="appearance-heading">
          Appearance
        </h2>
        <div className="settings-card">
          <div className="settings-row">
            <div className="settings-row__text">
              <p className="settings-row__label">Theme</p>
              <p className="settings-row__hint">
                Applies immediately and is remembered on this device.
              </p>
            </div>
            <div className="segmented" role="group" aria-label="Theme preference">
              {themeOptions.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  className={`segmented__option ${preference === option.value ? 'is-selected' : ''}`}
                  onClick={() => setPreference(option.value)}
                  aria-pressed={preference === option.value}
                >
                  {option.label}
                </button>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section className="settings-section" aria-labelledby="account-heading">
        <h2 className="settings-section__title" id="account-heading">
          Account
        </h2>
        <div className="settings-card">
          <div className="settings-row">
            <div className="settings-row__text">
              <p className="settings-row__label">Identity</p>
              <p className="settings-row__hint">
                {status === 'authenticated'
                  ? user?.email ?? 'Signed in'
                  : status === 'unconfigured'
                    ? 'Authentication is not configured for this deployment.'
                    : 'Not signed in.'}
              </p>
            </div>
          </div>
          <div className="settings-row">
            <div className="settings-row__text">
              <p className="settings-row__label">Auth provider</p>
              <p className="settings-row__hint">
                {isConfigured ? 'Supabase Auth' : 'None configured'}
              </p>
            </div>
          </div>
        </div>
      </section>

      <section className="settings-section" aria-labelledby="deployment-heading">
        <h2 className="settings-section__title" id="deployment-heading">
          Deployment
        </h2>
        <div className="settings-card">
          <div className="settings-row">
            <div className="settings-row__text">
              <p className="settings-row__label">Environment</p>
              <p className="settings-row__hint">{config.appEnv}</p>
            </div>
          </div>
          <div className="settings-row">
            <div className="settings-row__text">
              <p className="settings-row__label">API endpoint</p>
              <p className="settings-row__hint settings-row__hint--mono">{config.apiBaseUrl}</p>
            </div>
          </div>
          <div className="settings-row">
            <div className="settings-row__text">
              <p className="settings-row__label">Request timeout</p>
              <p className="settings-row__hint">{config.requestTimeoutMs} ms</p>
            </div>
          </div>
        </div>
      </section>
    </PageContainer>
  );
}
