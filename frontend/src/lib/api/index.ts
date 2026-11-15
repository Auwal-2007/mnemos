/** Public API surface for the API layer. */

export { ApiError, api, request, toErrorMessage } from './client';
export type { ApiErrorCode, RequestOptions } from './client';
export { apiUrl, config, isSupabaseConfigured } from '../config';
export {
  createWorkspace,
  fetchPreferences,
  fetchProfile,
  fetchWorkspaceMembers,
  fetchWorkspaces,
  updatePreferences,
  updateProfile,
} from './workspaces';
export type {
  HealthResponse,
  ListResponse,
  ReadinessCheck,
  ReadinessResponse,
  Profile,
  UserPreferences,
  UserProfile,
  Workspace,
  WorkspaceMember,
  WorkspaceRole,
} from './types';
