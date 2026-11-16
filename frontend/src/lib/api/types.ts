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

// ---------------------------------------------------------------------------
// Phase 3 / 4 — conversations, retrieval, memory, agents
//
// These mirror the backend response schemas exactly (verified against the
// generated OpenAPI document), so a field rename on the server surfaces as a
// type error here rather than as undefined rendered in the UI.
// ---------------------------------------------------------------------------

export type AnswerStatus = 'answered' | 'abstained' | 'degraded' | string;
export type AgentRole = 'orchestrator' | 'retrieval_specialist' | 'memory_specialist' | 'verification_specialist';

export interface Conversation {
  id: string;
  workspace_id: string;
  owner_id: string;
  title: string;
  agent_role: AgentRole | string | null;
  is_archived: boolean;
  created_at: string;
  updated_at: string;
}

export interface ConversationList {
  items: Conversation[];
  total: number;
}

export interface Message {
  id: string;
  conversation_id: string;
  role: 'user' | 'assistant' | 'system' | string;
  content: string;
  sequence_number: number;
  execution_id: string | null;
  created_at: string;
}

export interface MessageList {
  items: Message[];
  total: number;
}

/** One citation attached to a claim. Provenance identity is never optional. */
export interface Citation {
  provenance_id: string;
  chunk_id: string;
  source_id: string;
  source_title: string;
  source_kind: string;
  version_number: number;
  page: number | null;
  start_offset: number | null;
  end_offset: number | null;
  excerpt: string;
  information_status: string;
}

export interface Claim {
  text: string;
  citations: Citation[];
}

export interface ExecutionSummary {
  id: string;
  agent_role: AgentRole | string;
  model_id: string;
  status: string;
  latency_ms: number | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  total_tokens: number | null;
}

export interface Answer {
  answer_id: string;
  status: AnswerStatus;
  content: string;
  abstention_reason: string | null;
  claims: Claim[];
  evidence_considered: number;
  evidence_cited: number;
  evidence: Citation[];
  degraded_reason: string | null;
  execution: ExecutionSummary | null;
}

export interface AskResponse {
  conversation_id: string;
  question: Message;
  message: Message;
  answer: Answer;
}

export interface AnswerDetail {
  answer: Answer;
  claims: ClaimDetail[];
  metadata: Record<string, unknown>;
}

export interface ClaimDetail {
  id: string;
  claim_index: number;
  text: string;
  support: 'supported' | 'partially_supported' | 'unsupported' | 'contradicted' | 'unverified' | string;
  verification_note: string | null;
  citations: Citation[];
}

// --- retrieval -------------------------------------------------------------

export interface RetrievalScores {
  lexical_rank: number | null;
  semantic_rank: number | null;
  lexical_score: number | null;
  semantic_similarity: number | null;
  fused_score: number;
}

export interface RetrievedPassage {
  chunk_id: string;
  provenance_id: string;
  source_id: string;
  document_version_id: string;
  source_title: string;
  source_kind: string;
  version_number: number;
  version_is_current: boolean;
  information_status: string;
  chunk_index: number;
  content: string;
  char_count: number;
  source_location: Record<string, unknown>;
  page: number | null;
  start_offset: number | null;
  end_offset: number | null;
  matched_by: string;
  scores: RetrievalScores;
}

export interface SearchResponse {
  query: string;
  passages: RetrievedPassage[];
  total: number;
  limit: number;
  candidate_count: number;
  include_superseded: boolean;
  /** False when only the lexical retriever ran. Surfaced so the UI can say so. */
  hybrid: boolean;
  degraded_reason: string | null;
  metadata: Record<string, unknown>;
}

// --- verification ----------------------------------------------------------

export interface ClaimVerification {
  claim_id: string;
  verdict: string;
  method: string;
  confidence: number | null;
  explanation: string;
}

export interface VerificationCounts {
  supported: number;
  unsupported: number;
  unverified: number;
  contradicted: number;
  reliability: number | null;
  method: string;
}

export interface VerificationResult extends VerificationCounts {
  answer_id: string;
  total: number;
  fully_verified: boolean;
  claims: ClaimVerification[];
}

// --- memory ----------------------------------------------------------------

export interface Correction {
  id: string;
  workspace_id: string;
  provenance_id: string;
  corrected_text: string;
  rationale: string | null;
  status: 'proposed' | 'approved' | 'rejected' | 'applied' | string;
  proposed_by: string;
  reviewed_by: string | null;
  applied_provenance_id: string | null;
  is_self_review: boolean;
}

export interface CorrectionList {
  items: Correction[];
  total: number;
}

export interface Conflict {
  id: string;
  workspace_id: string;
  provenance_a: string;
  provenance_b: string;
  detected_reason: string;
  detection_method: string;
  score: number | null;
  status: 'open' | 'resolved' | 'dismissed' | string;
  resolved_by: string | null;
  resolution_note: string | null;
}

export interface ConflictList {
  items: Conflict[];
  total: number;
}

export interface ApplyCorrectionResult {
  correction_id: string;
  revision_provenance_id: string;
  status: string;
}

export interface DetectConflictsResult {
  candidates: Array<Record<string, unknown>>;
  recorded_ids: string[];
}

// --- agents ----------------------------------------------------------------

export interface AgentStep {
  capability: string;
  status: string;
  detail: Record<string, unknown>;
  latency_ms: number | null;
}

export interface AgentRun {
  role: AgentRole | string;
  status: string;
  latency_ms: number | null;
  step_count: number;
  error_code: string | null;
  output_summary: Record<string, unknown>;
  steps: AgentStep[];
}

export interface AgentAskResponse {
  conversation_id: string;
  answer: Answer;
  execution: ExecutionSummary;
  agent_trace: AgentRun[];
  degraded: boolean;
  verification: VerificationCounts | null;
  verification_skipped_reason: string | null;
}

export interface OrchestrationSummary {
  id: string;
  workspace_id: string;
  conversation_id: string | null;
  answer_id: string | null;
  question: string;
  plan: Array<Record<string, unknown>>;
  status: string;
  started_at: string;
  completed_at: string | null;
  total_latency_ms: number | null;
  total_tokens: number | null;
  metadata: Record<string, unknown>;
}

export interface OrchestrationDetail extends OrchestrationSummary {
  agent_trace: AgentRun[];
}

export interface OrchestrationList {
  items: OrchestrationSummary[];
  total: number;
}
