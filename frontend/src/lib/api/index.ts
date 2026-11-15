/** Public API surface for the API layer. */

export { ApiError, api, request, toErrorMessage } from './client';
export type { ApiErrorCode, RequestOptions } from './client';
export { apiUrl, config, isSupabaseConfigured } from '../config';
export type {
  HealthResponse,
  ListResponse,
  ReadinessCheck,
  ReadinessResponse,
  UserProfile,
  Workspace,
} from './types';
