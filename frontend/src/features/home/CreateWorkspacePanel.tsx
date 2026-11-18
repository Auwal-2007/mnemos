import { useCallback, useState } from 'react';
import { Button } from '../../components/ui/Button';
import { Icon } from '../../components/ui/Icon';
import { useAuth } from '../../lib/auth';
import { toErrorMessage } from '../../lib/api/client';
import { createWorkspace } from '../../lib/api/workspaces';
import './CreateWorkspacePanel.css';

/**
 * Create the first (or another) workspace.
 *
 * This existed only as an unused API function: a signed-in user with no
 * workspace had no way to make one, so the conversation pages were permanently
 * unusable and blamed a missing session. Signup creates a default workspace via
 * a database trigger, but anything that removes it — or a user who wants a
 * second one — had no path forward in the interface.
 */
export function CreateWorkspacePanel({ onCreated }: { onCreated: () => void }): JSX.Element {
  const { accessToken } = useAuth();
  const [name, setName] = useState('');
  const [isCreating, setIsCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = useCallback(async () => {
    const trimmed = name.trim();
    if (!accessToken || !trimmed) return;
    setIsCreating(true);
    setError(null);
    try {
      // The slug is derived from the name rather than asked for: it is a URL
      // identifier, and making a user invent one is a pointless obstacle.
      const slug = trimmed
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, '-')
        .replace(/^-+|-+$/g, '')
        .slice(0, 40);
      await createWorkspace(accessToken, {
        name: trimmed,
        slug: slug.length >= 3 ? slug : `workspace-${Date.now().toString(36)}`,
        description: null,
      });
      setName('');
      onCreated();
    } catch (cause) {
      setError(toErrorMessage(cause));
    } finally {
      setIsCreating(false);
    }
  }, [accessToken, name, onCreated]);

  return (
    <form
      className="create-ws"
      onSubmit={(event) => {
        event.preventDefault();
        void submit();
      }}
    >
      <div className="create-ws__head">
        <Icon name="workspace" size={18} />
        <h2 className="create-ws__title">Create a workspace</h2>
      </div>
      <p className="create-ws__lede">
        A workspace holds your sources, conversations and memory. Everything in it is private to
        you and the people you invite.
      </p>
      <label className="create-ws__label" htmlFor="workspace-name">
        Name
      </label>
      <input
        id="workspace-name"
        className="create-ws__input"
        value={name}
        onChange={(event) => setName(event.target.value)}
        placeholder="Research"
        maxLength={80}
        required
      />
      {error && (
        <p className="create-ws__error" role="alert">
          {error}
        </p>
      )}
      <Button type="submit" disabled={isCreating || name.trim().length === 0}>
        {isCreating ? 'Creating…' : 'Create workspace'}
      </Button>
    </form>
  );
}
