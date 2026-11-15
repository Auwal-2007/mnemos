/**
 * Centralized API client.
 *
 * Responsibilities: base URL resolution, timeouts, JSON handling,
 * error normalization, correlation ids, and (later) bearer tokens.
 * Components never call fetch directly.
 */

import { apiUrl, config } from '../config';

export type ApiErrorCode =
  | 'network_error'
  | 'timeout'
  | 'unauthorized'
  | 'forbidden'
  | 'not_found'
  | 'validation_error'
  | 'service_not_configured'
  | 'server_error'
  | 'unknown';

export class ApiError extends Error {
  readonly code: ApiErrorCode;
  readonly status: number;
  readonly requestId?: string;
  readonly details?: unknown;

  constructor(params: {
    code: ApiErrorCode;
    message: string;
    status: number;
    requestId?: string;
    details?: unknown;
  }) {
    super(params.message);
    this.name = 'ApiError';
    this.code = params.code;
    this.status = params.status;
    this.requestId = params.requestId;
    this.details = params.details;
  }

  /** True when retrying the same request could plausibly succeed. */
  get isRetryable(): boolean {
    return this.code === 'network_error' || this.code === 'timeout' || this.status >= 500;
  }
}

interface ErrorEnvelope {
  error?: {
    code?: string;
    message?: string;
    request_id?: string;
    details?: unknown;
  };
}

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  body?: unknown;
  signal?: AbortSignal;
  timeoutMs?: number;
  /** Bearer token, supplied by the auth layer. Never persisted here. */
  accessToken?: string;
  headers?: Record<string, string>;
}

function mapStatus(status: number, code?: string): ApiErrorCode {
  if (code === 'validation_error') return 'validation_error';
  if (code === 'service_not_configured') return 'service_not_configured';
  if (status === 401) return 'unauthorized';
  if (status === 403) return 'forbidden';
  if (status === 404) return 'not_found';
  if (status >= 500) return 'server_error';
  return 'unknown';
}

function createTimeoutSignal(timeoutMs: number, external?: AbortSignal): AbortSignal {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(new DOMException('Timeout', 'TimeoutError')), timeoutMs);

  if (external) {
    if (external.aborted) {
      controller.abort(external.reason);
    } else {
      external.addEventListener('abort', () => controller.abort(external.reason), { once: true });
    }
  }

  // Clear the timer once the request settles to avoid leaked timers.
  controller.signal.addEventListener('abort', () => clearTimeout(timer), { once: true });
  return controller.signal;
}

/**
 * Perform a typed JSON request against the MNEMOS API.
 * Throws {@link ApiError} for every non-success outcome.
 */
export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const {
    method = 'GET',
    body,
    signal,
    timeoutMs = config.requestTimeoutMs,
    accessToken,
    headers = {},
  } = options;

  const requestHeaders: Record<string, string> = {
    Accept: 'application/json',
    ...headers,
  };
  if (body !== undefined) requestHeaders['Content-Type'] = 'application/json';
  if (accessToken) requestHeaders.Authorization = `Bearer ${accessToken}`;

  let response: Response;
  try {
    response = await fetch(apiUrl(path), {
      method,
      headers: requestHeaders,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: createTimeoutSignal(timeoutMs, signal),
      credentials: 'omit',
    });
  } catch (error) {
    const isAbort = error instanceof DOMException && error.name === 'TimeoutError';
    if (isAbort) {
      throw new ApiError({
        code: 'timeout',
        message: 'The server took too long to respond. Please try again.',
        status: 0,
      });
    }
    if (error instanceof DOMException && error.name === 'AbortError') throw error;
    throw new ApiError({
      code: 'network_error',
      message: 'Unable to reach the server. Check your connection and try again.',
      status: 0,
    });
  }

  const requestId = response.headers.get('X-Request-ID') ?? undefined;

  if (response.status === 204) return undefined as T;

  const text = await response.text();
  let parsed: unknown = undefined;
  if (text) {
    try {
      parsed = JSON.parse(text);
    } catch {
      parsed = undefined;
    }
  }

  if (!response.ok) {
    const envelope = (parsed ?? {}) as ErrorEnvelope;
    throw new ApiError({
      code: mapStatus(response.status, envelope.error?.code),
      message: envelope.error?.message ?? 'The request failed. Please try again.',
      status: response.status,
      requestId: envelope.error?.request_id ?? requestId,
      details: envelope.error?.details,
    });
  }

  return parsed as T;
}

export const api = {
  get: <T>(path: string, options?: Omit<RequestOptions, 'method' | 'body'>) =>
    request<T>(path, { ...options, method: 'GET' }),
  post: <T>(path: string, body?: unknown, options?: Omit<RequestOptions, 'method' | 'body'>) =>
    request<T>(path, { ...options, method: 'POST', body }),
  patch: <T>(path: string, body?: unknown, options?: Omit<RequestOptions, 'method' | 'body'>) =>
    request<T>(path, { ...options, method: 'PATCH', body }),
  delete: <T>(path: string, options?: Omit<RequestOptions, 'method' | 'body'>) =>
    request<T>(path, { ...options, method: 'DELETE' }),
};

/** Human-readable message for any thrown value. */
export function toErrorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return 'Something went wrong. Please try again.';
}
