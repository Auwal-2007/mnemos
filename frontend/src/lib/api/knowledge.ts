/**
 * Knowledge API calls (Phase 2).
 *
 * Uploads use multipart/form-data, which the JSON-oriented client helper does
 * not handle, so this module performs the fetch directly while reusing the
 * same error normalization and base-URL resolution.
 */

import { apiUrl } from '../config';
import { ApiError, api, type ApiErrorCode } from './client';
import type {
  ChunkSummary,
  DocumentVersion,
  IngestionResult,
  KnowledgeSource,
  Provenance,
  SourceDetail,
} from './types';

interface ErrorEnvelope {
  error?: { code?: string; message?: string; request_id?: string; details?: unknown };
}

function mapStatus(status: number, code?: string): ApiErrorCode {
  if (code === 'validation_error' || code === 'ingestion_rejected') return 'validation_error';
  if (code === 'service_not_configured') return 'service_not_configured';
  if (status === 401) return 'unauthorized';
  if (status === 403) return 'forbidden';
  if (status === 404) return 'not_found';
  if (status >= 500) return 'server_error';
  return 'unknown';
}

/** Perform a multipart upload with the same error contract as `request`. */
async function uploadRequest<T>(
  path: string,
  form: FormData,
  accessToken: string,
  idempotencyKey?: string,
  timeoutMs = 60_000,
): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(new DOMException('Timeout', 'TimeoutError')), timeoutMs);

  const headers: Record<string, string> = { Accept: 'application/json' };
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
  if (idempotencyKey) headers['Idempotency-Key'] = idempotencyKey;

  let response: Response;
  try {
    response = await fetch(apiUrl(path), {
      method: 'POST',
      headers,
      body: form,
      signal: controller.signal,
      credentials: 'omit',
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'TimeoutError') {
      throw new ApiError({
        code: 'timeout',
        message: 'The upload took too long. Please try again.',
        status: 0,
      });
    }
    if (error instanceof DOMException && error.name === 'AbortError') throw error;
    throw new ApiError({
      code: 'network_error',
      message: 'Unable to reach the server. Check your connection and try again.',
      status: 0,
    });
  } finally {
    clearTimeout(timer);
  }

  const text = await response.text();
  let parsed: unknown;
  try {
    parsed = text ? JSON.parse(text) : undefined;
  } catch {
    parsed = undefined;
  }

  if (!response.ok) {
    const envelope = (parsed ?? {}) as ErrorEnvelope;
    throw new ApiError({
      code: mapStatus(response.status, envelope.error?.code),
      message: envelope.error?.message ?? 'The upload failed. Please try again.',
      status: response.status,
      requestId: envelope.error?.request_id ?? response.headers.get('X-Request-ID') ?? undefined,
      details: envelope.error?.details,
    });
  }

  return parsed as T;
}

export function fetchSources(
  accessToken: string,
  workspaceId: string,
  signal?: AbortSignal,
): Promise<KnowledgeSource[]> {
  return api.get<KnowledgeSource[]>(
    `/knowledge/workspaces/${workspaceId}/sources`,
    { accessToken, signal },
  );
}

export function fetchSourceDetail(
  accessToken: string,
  sourceId: string,
  signal?: AbortSignal,
): Promise<SourceDetail> {
  return api.get<SourceDetail>(`/knowledge/sources/${sourceId}`, { accessToken, signal });
}

export function fetchSourceVersions(
  accessToken: string,
  sourceId: string,
): Promise<DocumentVersion[]> {
  return api.get<DocumentVersion[]>(`/knowledge/sources/${sourceId}/versions`, { accessToken });
}

export function fetchSourceChunks(
  accessToken: string,
  sourceId: string,
): Promise<{ items: ChunkSummary[]; total: number }> {
  return api.get(`/knowledge/sources/${sourceId}/chunks`, { accessToken });
}

export function fetchProvenance(accessToken: string, chunkId: string): Promise<Provenance> {
  return api.get<Provenance>(`/knowledge/chunks/${chunkId}/provenance`, { accessToken });
}

export function deleteSource(accessToken: string, sourceId: string): Promise<void> {
  return api.delete<void>(`/knowledge/sources/${sourceId}`, { accessToken });
}

export function fetchDownloadUrl(
  accessToken: string,
  sourceId: string,
): Promise<{ url: string; expires_in_seconds: number }> {
  return api.get(`/knowledge/sources/${sourceId}/download`, { accessToken });
}

export function uploadDocument(
  accessToken: string,
  workspaceId: string,
  file: File,
  options: { title?: string; idempotencyKey?: string } = {},
): Promise<IngestionResult> {
  const form = new FormData();
  form.append('file', file);
  if (options.title) form.append('title', options.title);
  return uploadRequest<IngestionResult>(
    `/knowledge/workspaces/${workspaceId}/sources/upload`,
    form,
    accessToken,
    options.idempotencyKey,
  );
}

export function createNote(
  accessToken: string,
  workspaceId: string,
  payload: { title: string; content: string; idempotency_key?: string },
): Promise<IngestionResult> {
  return api.post<IngestionResult>(
    `/knowledge/workspaces/${workspaceId}/sources/note`,
    { workspace_id: workspaceId, ...payload },
    { accessToken },
  );
}

export function uploadNewVersion(
  accessToken: string,
  sourceId: string,
  file: File,
  idempotencyKey?: string,
): Promise<IngestionResult> {
  const form = new FormData();
  form.append('file', file);
  return uploadRequest<IngestionResult>(
    `/knowledge/sources/${sourceId}/versions/upload`,
    form,
    accessToken,
    idempotencyKey,
  );
}

export function createNoteVersion(
  accessToken: string,
  sourceId: string,
  content: string,
  idempotencyKey?: string,
): Promise<IngestionResult> {
  return api.post<IngestionResult>(
    `/knowledge/sources/${sourceId}/versions/note`,
    { workspace_id: 'ignored', title: 'ignored', content, idempotency_key: idempotencyKey },
    { accessToken },
  );
}

/** Human-readable size for source rows. */
export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} kB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export const UPLOAD_MAX_BYTES = 50 * 1024 * 1024;
export const SUPPORTED_EXTENSIONS = ['.pdf', '.md', '.markdown', '.txt'];

export interface IndexSourceResult {
  source_id: string;
  processing_status: string;
  chunk_count: number;
  chunks_created: boolean;
  embeddings_created: number;
  embedding_model: string | null;
  embedding_dimension: number | null;
  error_code: string | null;
  error_message: string | null;
}

export function indexSource(accessToken: string, sourceId: string): Promise<IndexSourceResult> {
  return api.post<IndexSourceResult>(`/knowledge/sources/${sourceId}/index`, undefined, {
    accessToken,
  });
}

export function reindexSource(accessToken: string, sourceId: string): Promise<IndexSourceResult> {
  return api.post<IndexSourceResult>(`/knowledge/sources/${sourceId}/reindex`, undefined, {
    accessToken,
  });
}
