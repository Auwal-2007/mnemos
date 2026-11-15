/**
 * Workspace API calls.
 *
 * These hit the authenticated backend endpoints, which verify the Supabase
 * token server-side and enforce RLS in the database. The frontend never
 * talks to Postgres directly for these operations.
 */

import { api } from './client';
import type { Profile, UserPreferences, Workspace, WorkspaceMember } from './types';

export function fetchProfile(accessToken: string): Promise<Profile> {
  return api.get<Profile>('/me', { accessToken });
}

export function updateProfile(
  accessToken: string,
  payload: { display_name: string | null },
): Promise<Profile> {
  return api.patch<Profile>('/me', payload, { accessToken });
}

export function fetchPreferences(accessToken: string): Promise<UserPreferences> {
  return api.get<UserPreferences>('/me/preferences', { accessToken });
}

export function updatePreferences(
  accessToken: string,
  theme: 'system' | 'light' | 'dark',
): Promise<UserPreferences> {
  return api.post<UserPreferences>('/me/preferences', { theme }, { accessToken });
}

export function fetchWorkspaces(accessToken: string): Promise<Workspace[]> {
  return api.get<Workspace[]>('/workspaces', { accessToken });
}

export function createWorkspace(
  accessToken: string,
  payload: { name: string; slug: string; description?: string | null },
): Promise<Workspace> {
  return api.post<Workspace>('/workspaces', payload, { accessToken });
}

export function fetchWorkspaceMembers(
  accessToken: string,
  workspaceId: string,
): Promise<{ items: WorkspaceMember[]; total: number }> {
  return api.get(`/workspaces/${workspaceId}/members`, { accessToken });
}
