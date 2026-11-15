/**
 * Typed API contracts mirroring the backend schemas.
 * Kept hand-written and small; the backend OpenAPI schema is authoritative.
 */

export interface HealthResponse {
  status: string;
  service: string;
  version: string;
  environment: string;
}

export interface ReadinessCheck {
  name: string;
  configured: boolean;
  required: boolean;
}

export interface ReadinessResponse {
  status: string;
  checks: ReadinessCheck[];
}

export interface ListResponse<T> {
  items: T[];
  total: number;
}

/** Mirrors backend `ProfileResponse`. */
export interface Profile {
  id: string;
  email: string | null;
  display_name: string | null;
  avatar_url: string | null;
  created_at: string;
  updated_at: string;
}

/** Backwards-compatible alias. */
export type UserProfile = Profile;

export type WorkspaceRole = 'owner' | 'editor' | 'viewer';

export interface Workspace {
  id: string;
  owner_id: string;
  name: string;
  slug: string;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export interface WorkspaceMember {
  workspace_id: string;
  user_id: string;
  role: WorkspaceRole;
  created_at: string;
}

export interface UserPreferences {
  user_id: string;
  theme: 'system' | 'light' | 'dark';
  locale: string;
  created_at: string;
  updated_at: string;
}
