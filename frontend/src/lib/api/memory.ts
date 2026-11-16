/**
 * Memory API calls (Phase 3C).
 *
 * "Memory" here is revision-aware: a correction does not overwrite a record, it
 * creates a reviewable proposal that, once applied, links to a new revision. The
 * original stays readable. This module therefore exposes the whole lifecycle —
 * propose, review, apply — rather than a single "update" call, because presenting
 * a correction as an overwrite would misrepresent what the system does.
 */

import { api } from './client';
import type {
  ApplyCorrectionResult,
  Conflict,
  ConflictList,
  Correction,
  CorrectionList,
  DetectConflictsResult,
} from './types';

export function fetchCorrections(
  accessToken: string,
  workspaceId: string,
  signal?: AbortSignal,
): Promise<CorrectionList> {
  return api.get<CorrectionList>(
    `/memory/workspaces/${encodeURIComponent(workspaceId)}/corrections`,
    { accessToken, signal },
  );
}

export interface ProposeCorrectionInput {
  provenanceId: string;
  correctedText: string;
  rationale?: string;
}

export function proposeCorrection(
  accessToken: string,
  workspaceId: string,
  input: ProposeCorrectionInput,
): Promise<Correction> {
  return api.post<Correction>(
    `/memory/workspaces/${encodeURIComponent(workspaceId)}/corrections`,
    {
      provenance_id: input.provenanceId,
      corrected_text: input.correctedText,
      rationale: input.rationale ?? null,
    },
    { accessToken },
  );
}

/**
 * Approve or reject a proposed correction.
 *
 * Self-review is blocked by a database trigger, not by this call, so a user
 * approving their own correction gets a server-side refusal rather than a
 * silently skipped check.
 */
export function reviewCorrection(
  accessToken: string,
  correctionId: string,
  approve: boolean,
  note?: string,
): Promise<Correction> {
  return api.post<Correction>(
    `/memory/corrections/${encodeURIComponent(correctionId)}/review`,
    { approve, note: note ?? null },
    { accessToken },
  );
}

export function applyCorrection(
  accessToken: string,
  correctionId: string,
): Promise<ApplyCorrectionResult> {
  return api.post<ApplyCorrectionResult>(
    `/memory/corrections/${encodeURIComponent(correctionId)}/apply`,
    undefined,
    { accessToken },
  );
}

export function fetchConflicts(
  accessToken: string,
  workspaceId: string,
  signal?: AbortSignal,
): Promise<ConflictList> {
  return api.get<ConflictList>(
    `/memory/workspaces/${encodeURIComponent(workspaceId)}/conflicts`,
    { accessToken, signal },
  );
}

export function detectConflicts(
  accessToken: string,
  workspaceId: string,
): Promise<DetectConflictsResult> {
  return api.post<DetectConflictsResult>(
    `/memory/workspaces/${encodeURIComponent(workspaceId)}/conflicts/detect`,
    undefined,
    { accessToken, timeoutMs: 120_000 },
  );
}

export function resolveConflict(
  accessToken: string,
  conflictId: string,
  dismiss: boolean,
  note?: string,
): Promise<Conflict> {
  return api.post<Conflict>(
    `/memory/conflicts/${encodeURIComponent(conflictId)}/resolve`,
    { dismiss, note: note ?? null },
    { accessToken },
  );
}
