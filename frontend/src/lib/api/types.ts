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

// --- Phase 2: knowledge ---------------------------------------------------

export type SourceKind = 'document' | 'note';

export type ProcessingStatus =
  | 'pending'
  | 'validating'
  | 'extracting'
  | 'extracted'
  | 'chunking'
  | 'indexing'
  | 'ready'
  | 'failed';

export type ExtractionStatus = 'pending' | 'extracting' | 'extracted' | 'failed';

export type EmbeddingStatus = 'pending' | 'embedded' | 'failed';

export type InformationStatus =
  | 'current'
  | 'superseded'
  | 'disputed'
  | 'archived'
  | 'pending_review';

/** Where a chunk sits inside the original document. */
export interface SourceLocation {
  start_offset: number;
  end_offset: number;
  page?: number | null;
  section?: string | null;
}

export interface KnowledgeSource {
  id: string;
  workspace_id: string;
  owner_id: string;
  kind: SourceKind;
  title: string;
  original_filename: string | null;
  mime_type: string;
  size_bytes: number;
  content_hash: string;
  processing_status: ProcessingStatus;
  processing_error_code: string | null;
  processing_error_detail: string | null;
  processing_attempts: number;
  metadata: Record<string, unknown>;
  submitted_at: string;
  created_at: string;
  updated_at: string;
}

export interface DocumentVersion {
  id: string;
  source_id: string;
  version_number: number;
  content_hash: string;
  size_bytes: number;
  mime_type: string;
  extraction_status: ExtractionStatus;
  extraction_method: string | null;
  is_current: boolean;
  submitted_at: string;
  created_at: string;
}

export interface SourceDetail extends KnowledgeSource {
  versions: DocumentVersion[];
  current_version: DocumentVersion | null;
}

export interface ExtractionOutcome {
  status: string;
  method: string | null;
  char_count: number;
  page_count: number;
  segment_count: number;
  error_code: string | null;
  error_message: string | null;
}

export interface IngestionResult {
  source: KnowledgeSource;
  version_id: string | null;
  version_number: number | null;
  extraction: ExtractionOutcome;
  duplicate_of_existing: boolean;
}

export interface ChunkSummary {
  chunk_id: string;
  document_version_id: string;
  chunk_index: number;
  char_count: number;
  source_location: SourceLocation;
  embedding_status: EmbeddingStatus;
  preview: string;
}

export interface Provenance {
  provenance_id: string;
  chunk_id: string;
  source_id: string;
  document_version_id: string;
  workspace_id: string;
  source_title: string;
  source_kind: SourceKind;
  version_number: number;
  source_location: SourceLocation;
  chunk_index: number;
  information_status: InformationStatus;
  revision_reference: string | null;
  superseded_by: string | null;
  document_created_at: string;
  submitted_at: string;
  resolution_metadata: Record<string, unknown>;
}
