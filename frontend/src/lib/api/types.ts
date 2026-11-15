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

export interface UserProfile {
  id: string;
  email: string | null;
  display_name: string | null;
  avatar_url: string | null;
  created_at: string;
}

export interface Workspace {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  owner_id: string;
  created_at: string;
  updated_at: string;
}
