import { useCallback } from 'react';
import { useAuth } from '../auth';
import { useAsync, type AsyncState } from '../hooks/useAsync';
import { fetchWorkspaces } from './workspaces';
import type { Workspace } from './types';

export interface WorkspacesState extends AsyncState<Workspace[]> {
  /** True when there is no authenticated session to query with. */
  needsAuth: boolean;
  /** True when Supabase is not configured for this deployment. */
  unconfigured: boolean;
}

/**
 * Load the authenticated user's workspaces from the backend.
 *
 * Returns no data (and a clear reason) when there is no session, instead of
 * inventing a placeholder workspace.
 */
export function useWorkspaces(): WorkspacesState {
  const { accessToken, status, isConfigured } = useAuth();

  const loader = useCallback(async () => {
    if (!accessToken) return [];
    return fetchWorkspaces(accessToken);
  }, [accessToken]);

  const state = useAsync(loader, [accessToken, status]);

  return {
    ...state,
    needsAuth: !accessToken,
    unconfigured: !isConfigured,
  };
}
