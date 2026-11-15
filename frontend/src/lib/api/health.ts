import { api } from './client';
import type { HealthResponse, ReadinessResponse } from './types';

/** Liveness probe used by the integration check. */
export function fetchHealth(): Promise<HealthResponse> {
  return api.get<HealthResponse>('/health', { timeoutMs: 8000 });
}

/** Readiness probe: which integrations are configured server-side. */
export function fetchReadiness(): Promise<ReadinessResponse> {
  return api.get<ReadinessResponse>('/ready', { timeoutMs: 8000 });
}
