"""Verification, correction and conflict persistence (Phase 3C).

Split by privilege, as elsewhere:

* verdicts and conflict *records* are written by the server (a user who could
  write their own verdicts could mark their own claims supported);
* a correction is *proposed* by a user, but reviewed and applied through
  server-side paths that re-check the actor.

Applying a correction goes through the `apply_knowledge_correction` function so
the revision, supersession and correction status change are one transaction.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, cast

from postgrest.exceptions import APIError
from supabase import Client

from app.core.errors import MnemosError, NotFoundError
from app.domain.conversation import CitationDraft, Claim, ClaimSupport
from app.domain.verification import (
    ClaimVerdict,
    ConflictCandidate,
    Correction,
    CorrectionStatus,
    VerificationMethod,
)

logger = logging.getLogger("mnemos.repositories.verification")


def _correction(row: dict[str, Any]) -> Correction:
    from app.repositories.supabase_repositories import _parse_datetime

    def optional_dt(key: str) -> datetime | None:
        value = row.get(key)
        return _parse_datetime(value) if value else None

    return Correction(
        id=str(row["id"]),
        workspace_id=str(row["workspace_id"]),
        provenance_id=str(row["provenance_id"]),
        corrected_text=str(row["corrected_text"]),
        rationale=cast("str | None", row.get("rationale")),
        status=CorrectionStatus(str(row["status"])),
        proposed_by=str(row["proposed_by"]),
        reviewed_by=cast("str | None", row.get("reviewed_by")),
        reviewed_at=optional_dt("reviewed_at"),
        applied_provenance_id=cast("str | None", row.get("applied_provenance_id")),
        created_at=_parse_datetime(row.get("created_at")),
    )


class SupabaseVerificationRepository:
    """Verdicts and claim support updates."""

    def __init__(self, read_client: Client, write_client: Client) -> None:
        self._read = read_client
        self._write = write_client

    def save_verification(
        self,
        *,
        claim_id: str,
        workspace_id: str,
        verdict: ClaimVerdict,
        execution_id: str | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "claim_id": claim_id,
            "workspace_id": workspace_id,
            "verdict": verdict.verdict,
            "method": verdict.method.value,
            "explanation": verdict.explanation or None,
            "supporting_chunk_ids": verdict.supporting_chunk_ids,
            "contradicted_by_chunk_ids": verdict.contradicted_by_chunk_ids,
        }
        if verdict.confidence is not None:
            payload["confidence"] = verdict.confidence
        if execution_id is not None:
            payload["execution_id"] = execution_id
        try:
            # One verdict per claim: re-verifying replaces the previous verdict
            # rather than accumulating contradictory ones.
            self._write.table("claim_verifications").upsert(
                payload, on_conflict="claim_id"
            ).execute()
        except APIError as exc:
            raise _translate(exc) from exc

    def update_claim_support(
        self, claim_id: str, *, support: ClaimSupport, note: str | None
    ) -> None:
        try:
            self._write.table("claims").update(
                {
                    "support": support.value,
                    "verification_note": note,
                    "verified_at": datetime.now(UTC).isoformat(),
                }
            ).eq("id", claim_id).execute()
        except APIError as exc:
            raise _translate(exc) from exc

    def claims_for_answer(self, answer_id: str) -> list[Claim]:
        try:
            claim_response = (
                self._read.table("claims")
                .select("*")
                .eq("answer_id", answer_id)
                .order("claim_index", desc=False)
                .execute()
            )
            claim_ids = [str(row["id"]) for row in claim_response.data or []]
            if claim_ids:
                citation_response = (
                    self._read.table("claim_citations")
                    .select("claim_id,provenance_id,quoted_text,relevance")
                    .in_("claim_id", claim_ids)
                    .execute()
                )
            else:
                citation_response = None
        except APIError as exc:
            raise _translate(exc) from exc

        by_claim: dict[str, list[CitationDraft]] = {}
        for row in (citation_response.data if citation_response else []) or []:
            record = cast("dict[str, Any]", row)
            by_claim.setdefault(str(record["claim_id"]), []).append(
                CitationDraft(
                    provenance_id=str(record["provenance_id"]),
                    quoted_text=cast("str | None", record.get("quoted_text")),
                    relevance=cast("float | None", record.get("relevance")),
                )
            )

        return [
            Claim(
                id=str(row["id"]),
                answer_id=answer_id,
                claim_index=int(row["claim_index"]),
                text=str(row["text"]),
                support=ClaimSupport(str(row["support"])),
                verification_note=cast("str | None", row.get("verification_note")),
                citations=by_claim.get(str(row["id"]), []),
            )
            for row in claim_response.data or []
        ]

    def passages_for(
        self, workspace_id: str, provenance_ids: Sequence[str]
    ) -> dict[str, dict[str, str]]:
        """Return provenance id -> {chunk_id, text} for verification grounds.

        Reads `provenance_text_for_workspace`, a SECURITY INVOKER function, so
        RLS decides visibility. A provenance id the caller cannot see simply
        comes back empty rather than raising, which lets a partially visible
        answer still be verified against what is visible.
        """
        if not provenance_ids:
            return {}
        try:
            rows = self._read.rpc(
                "provenance_text_for_workspace",
                {"p_workspace_id": workspace_id, "p_provenance_ids": list(provenance_ids)},
            ).execute()
        except APIError as exc:
            raise _translate(exc) from exc
        return {
            str(row["provenance_id"]): {
                "chunk_id": str(row["chunk_id"]),
                "text": str(row["content"]),
            }
            for row in rows.data or []
        }


class SupabaseCorrectionRepository:
    """Corrections: propose (user path), review and apply (server paths)."""

    def __init__(self, read_client: Client, write_client: Client) -> None:
        self._read = read_client
        self._write = write_client

    def create(
        self,
        *,
        workspace_id: str,
        provenance_id: str,
        corrected_text: str,
        rationale: str | None,
        proposed_by: str,
    ) -> Correction:
        payload: dict[str, Any] = {
            "workspace_id": workspace_id,
            "provenance_id": provenance_id,
            "corrected_text": corrected_text,
            "rationale": rationale,
            "proposed_by": proposed_by,
        }
        try:
            response = self._read.table("knowledge_corrections").insert(payload).execute()
        except APIError as exc:
            raise _translate(exc) from exc
        rows = response.data or []
        if not rows:
            raise _write_failed("The correction could not be proposed.")
        return _correction(cast("dict[str, Any]", rows[0]))

    def get(self, correction_id: str) -> Correction | None:
        try:
            response = (
                self._read.table("knowledge_corrections")
                .select("*")
                .eq("id", correction_id)
                .maybe_single()
                .execute()
            )
        except APIError as exc:
            raise _translate(exc) from exc
        if not response or not response.data:
            return None
        return _correction(cast("dict[str, Any]", response.data))

    def list_for_workspace(
        self, workspace_id: str, *, status: str | None = None, limit: int = 50
    ) -> list[Correction]:
        try:
            query = (
                self._read.table("knowledge_corrections")
                .select("*")
                .eq("workspace_id", workspace_id)
                .order("created_at", desc=True)
                .limit(limit)
            )
            if status:
                query = query.eq("status", status)
            response = query.execute()
        except APIError as exc:
            raise _translate(exc) from exc
        return [_correction(cast("dict[str, Any]", row)) for row in response.data or []]

    def review(
        self, correction_id: str, *, status: CorrectionStatus, reviewed_by: str
    ) -> Correction:
        try:
            response = (
                self._write.table("knowledge_corrections")
                .update(
                    {
                        "status": status.value,
                        "reviewed_by": reviewed_by,
                        "reviewed_at": datetime.now(UTC).isoformat(),
                    }
                )
                .eq("id", correction_id)
                .execute()
            )
        except APIError as exc:
            raise _translate(exc) from exc
        rows = response.data or []
        if not rows:
            raise NotFoundError(message="Correction not found.")
        return _correction(cast("dict[str, Any]", rows[0]))

    def apply(self, correction_id: str, *, actor: str) -> str:
        try:
            response = self._read.rpc(
                "apply_knowledge_correction",
                {"p_correction_id": correction_id, "p_actor": actor},
            ).execute()
        except APIError as exc:
            raise _translate(exc) from exc
        value = response.data
        if isinstance(value, str):
            return value
        if isinstance(value, list) and value:
            first = value[0]
            if isinstance(first, str):
                return first
            if isinstance(first, dict):
                for key in ("apply_knowledge_correction", "id"):
                    if key in first:
                        return str(first[key])
        raise _write_failed("The correction could not be applied.")


class SupabaseConflictRepository:
    """Conflict records."""

    def __init__(self, read_client: Client, write_client: Client) -> None:
        self._read = read_client
        self._write = write_client

    def record(self, *, workspace_id: str, candidate: ConflictCandidate) -> str:
        # The schema stores pairs in canonical order with a unique constraint, so
        # one conflict is one row regardless of discovery order.
        first, second = sorted([candidate.provenance_a, candidate.provenance_b])
        payload: dict[str, Any] = {
            "workspace_id": workspace_id,
            "provenance_a": first,
            "provenance_b": second,
            "detected_reason": candidate.reason,
            "detection_method": candidate.method.value,
        }
        if candidate.score is not None:
            payload["score"] = candidate.score
        try:
            response = self._write.table("knowledge_conflicts").insert(payload).execute()
        except APIError as exc:
            raise _translate(exc) from exc
        rows = response.data or []
        if not rows:
            raise _write_failed("The conflict could not be recorded.")
        return str(cast("dict[str, Any]", rows[0])["id"])

    def get(self, conflict_id: str) -> dict[str, Any] | None:
        """Fetch one conflict as the caller. RLS hides other workspaces."""
        try:
            response = (
                self._read.table("knowledge_conflicts")
                .select("*")
                .eq("id", conflict_id)
                .maybe_single()
                .execute()
            )
        except APIError as exc:
            raise _translate(exc) from exc
        if not response or not response.data:
            return None
        return cast("dict[str, Any]", response.data)

    def list_for_workspace(
        self, workspace_id: str, *, status: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        try:
            query = (
                self._read.table("knowledge_conflicts")
                .select("*")
                .eq("workspace_id", workspace_id)
                .order("created_at", desc=True)
                .limit(limit)
            )
            if status:
                query = query.eq("status", status)
            response = query.execute()
        except APIError as exc:
            raise _translate(exc) from exc
        return [dict(row) for row in response.data or []]

    def resolve(
        self,
        conflict_id: str,
        *,
        status: str,
        resolved_by: str,
        note: str | None,
    ) -> None:
        try:
            self._write.table("knowledge_conflicts").update(
                {
                    "status": status,
                    "resolved_by": resolved_by,
                    "resolved_at": datetime.now(UTC).isoformat(),
                    "resolution_note": note,
                }
            ).eq("id", conflict_id).execute()
        except APIError as exc:
            raise _translate(exc) from exc

    def passages_for(self, workspace_id: str, provenance_ids: Sequence[str]) -> dict[str, str]:
        """Passage text keyed by provenance id, RLS-scoped to the caller."""
        if not provenance_ids:
            return {}
        try:
            response = self._read.rpc(
                "provenance_text_for_workspace",
                {"p_workspace_id": workspace_id, "p_provenance_ids": list(provenance_ids)},
            ).execute()
        except APIError as exc:
            raise _translate(exc) from exc
        return {str(row["provenance_id"]): str(row["content"]) for row in response.data or []}


class RepositoryWriteError(MnemosError):
    """A write the database refused for a reason the caller must see."""

    status_code = 502
    code = "repository_write_failed"
    default_message = "The record could not be stored."


def _write_failed(message: str) -> MnemosError:
    return RepositoryWriteError(message=message)


def _translate(exc: APIError) -> MnemosError:
    from app.repositories.supabase_repositories import _BaseSupabaseRepository

    return _BaseSupabaseRepository._translate(exc)


__all__ = [
    "SupabaseConflictRepository",
    "SupabaseCorrectionRepository",
    "SupabaseVerificationRepository",
    "VerificationMethod",
]
