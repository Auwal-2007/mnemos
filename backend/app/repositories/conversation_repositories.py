"""Conversation, answer and execution persistence (Phase 3B).

Two clients, deliberately separated:

* **read client** — the caller's token-bound client. Listing conversations,
  reading messages and reading answers all run under RLS as the caller, so the
  database decides what is visible.
* **write client** — the service-role client. messages, answers, claims,
  claim_citations and execution_records are not writable by users by design;
  a client that could insert an answer could fabricate one. Every write path
  here therefore takes an already-authorized caller from the service layer.

No SQL is assembled anywhere: only named table operations and RPCs.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime
from typing import Any, cast

from postgrest.exceptions import APIError
from supabase import Client

from app.core.errors import MnemosError
from app.domain.conversation import (
    AgentRole,
    Claim,
    ClaimSupport,
    Conversation,
    ExecutionRecord,
    ExecutionStatus,
    GeneratedAnswer,
    Message,
    MessageRole,
)

logger = logging.getLogger("mnemos.repositories.conversation")

#: Used when a query has an empty id list: PostgREST's `in.()` needs at least
#: one value, and this id cannot match anything.
_NIL_UUID = "00000000-0000-0000-0000-000000000000"


def _conversation(row: dict[str, Any]) -> Conversation:
    from app.repositories.supabase_repositories import _parse_datetime

    role = row.get("agent_role")
    return Conversation(
        id=str(row["id"]),
        workspace_id=str(row["workspace_id"]),
        owner_id=str(row["owner_id"]),
        title=str(row["title"]),
        agent_role=AgentRole(role) if role else None,
        is_archived=bool(row["is_archived"]),
        created_at=_parse_datetime(row.get("created_at")),
        updated_at=_parse_datetime(row.get("updated_at")),
    )


def _message(row: dict[str, Any]) -> Message:
    from app.repositories.supabase_repositories import _parse_datetime

    return Message(
        id=str(row["id"]),
        conversation_id=str(row["conversation_id"]),
        workspace_id=str(row["workspace_id"]),
        role=MessageRole(row["role"]),
        content=str(row["content"]),
        sequence_number=int(row["sequence_number"]),
        execution_id=cast("str | None", row.get("execution_id")),
        created_at=_parse_datetime(row.get("created_at")),
    )


def fingerprint(*parts: str) -> str:
    """Stable sha256 of the inputs, for correlation without storing content."""
    digest = hashlib.sha256()
    for part in parts:
        digest.update(part.encode("utf-8"))
        digest.update(b"\x00")
    return digest.hexdigest()


class SupabaseConversationRepository:
    """Conversations and messages. Reads as the caller, writes as the server."""

    def __init__(self, read_client: Client, write_client: Client) -> None:
        self._read = read_client
        self._write = write_client

    # --- conversations ----------------------------------------------------

    def list_for_workspace(
        self, workspace_id: str, *, limit: int = 50, offset: int = 0
    ) -> list[Conversation]:
        try:
            response = (
                self._read.table("conversations")
                .select("*")
                .eq("workspace_id", workspace_id)
                .eq("is_archived", False)
                .order("updated_at", desc=True)
                .range(offset, offset + limit - 1)
                .execute()
            )
        except APIError as exc:
            raise _translate(exc) from exc
        return [_conversation(cast("dict[str, Any]", row)) for row in response.data or []]

    def get(self, conversation_id: str) -> Conversation | None:
        try:
            response = (
                self._read.table("conversations")
                .select("*")
                .eq("id", conversation_id)
                .maybe_single()
                .execute()
            )
        except APIError as exc:
            raise _translate(exc) from exc
        if not response or not response.data:
            return None
        return _conversation(cast("dict[str, Any]", response.data))

    def create(
        self,
        *,
        workspace_id: str,
        owner_id: str,
        title: str,
        agent_role: AgentRole | None = None,
    ) -> Conversation:
        payload: dict[str, Any] = {
            "workspace_id": workspace_id,
            "owner_id": owner_id,
            "title": title[:200],
        }
        if agent_role is not None:
            payload["agent_role"] = agent_role.value
        try:
            response = self._write.table("conversations").insert(payload).execute()
        except APIError as exc:
            raise _translate(exc) from exc
        rows = response.data or []
        if not rows:
            raise _translate_error_message("The conversation could not be created.")
        return _conversation(cast("dict[str, Any]", rows[0]))

    def touch(self, conversation_id: str) -> None:
        """Advance updated_at so listing stays in recency order."""
        try:
            self._write.table("conversations").update(
                {"updated_at": datetime.now(UTC).isoformat()}
            ).eq("id", conversation_id).execute()
        except APIError as exc:
            raise _translate(exc) from exc

    # --- messages ---------------------------------------------------------

    def list_messages(self, conversation_id: str) -> list[Message]:
        try:
            response = (
                self._read.table("messages")
                .select("*")
                .eq("conversation_id", conversation_id)
                .order("sequence_number", desc=False)
                .execute()
            )
        except APIError as exc:
            raise _translate(exc) from exc
        return [_message(cast("dict[str, Any]", row)) for row in response.data or []]

    def next_sequence_number(self, conversation_id: str) -> int:
        messages = self.list_messages(conversation_id)
        return (max((message.sequence_number for message in messages), default=-1)) + 1

    def append_message(
        self,
        *,
        conversation_id: str,
        workspace_id: str,
        role: MessageRole,
        content: str,
        sequence_number: int,
        execution_id: str | None = None,
    ) -> Message:
        payload: dict[str, Any] = {
            "conversation_id": conversation_id,
            "workspace_id": workspace_id,
            "role": role.value,
            "content": content,
            "sequence_number": sequence_number,
        }
        if execution_id is not None:
            payload["execution_id"] = execution_id
        try:
            response = self._write.table("messages").insert(payload).execute()
        except APIError as exc:
            raise _translate(exc) from exc
        rows = response.data or []
        if not rows:
            raise _translate_error_message("The message could not be stored.")
        return _message(cast("dict[str, Any]", rows[0]))


class SupabaseAnswerRepository:
    """Answers, claims, citations and execution records (write client only)."""

    def __init__(self, read_client: Client, write_client: Client) -> None:
        self._read = read_client
        self._write = write_client

    def record_execution(self, record: ExecutionRecord) -> ExecutionRecord:
        payload: dict[str, Any] = {
            "workspace_id": record.workspace_id,
            "conversation_id": record.conversation_id,
            "agent_role": record.agent_role.value,
            "purpose": record.purpose,
            "model_id": record.model_id,
            "provider": record.provider,
            "status": record.status.value,
            "attempt_count": record.attempt_count,
            "metadata": record.metadata,
        }
        if record.latency_ms is not None:
            payload["latency_ms"] = record.latency_ms
        if record.prompt_tokens is not None:
            payload["prompt_tokens"] = record.prompt_tokens
        if record.completion_tokens is not None:
            payload["completion_tokens"] = record.completion_tokens
        if record.total_tokens is not None:
            payload["total_tokens"] = record.total_tokens
        if record.error_code is not None:
            payload["error_code"] = record.error_code
        try:
            response = self._write.table("execution_records").insert(payload).execute()
        except APIError as exc:
            raise _translate(exc) from exc
        rows = response.data or []
        if not rows:
            raise _translate_error_message("The execution record could not be stored.")
        row = cast("dict[str, Any]", rows[0])
        return ExecutionRecord(
            id=str(row["id"]),
            workspace_id=record.workspace_id,
            conversation_id=record.conversation_id,
            agent_role=record.agent_role,
            purpose=record.purpose,
            model_id=str(row["model_id"]),
            status=ExecutionStatus(str(row["status"])),
            provider=str(row["provider"]),
            latency_ms=record.latency_ms,
            prompt_tokens=record.prompt_tokens,
            completion_tokens=record.completion_tokens,
            total_tokens=record.total_tokens,
            attempt_count=record.attempt_count,
            error_code=record.error_code,
            metadata=record.metadata,
        )

    def save_answer(
        self,
        *,
        workspace_id: str,
        conversation_id: str,
        message_id: str | None,
        execution_id: str | None,
        answer: GeneratedAnswer,
    ) -> str:
        """Persist an answer with its claims and citations, in order.

        message_id may be None while the answer is being built; the caller
        attaches the assistant message afterwards. The schema requires it, so
        the conversation service always creates the message first.
        """
        if message_id is None:
            raise _translate_error_message("An answer requires the message it belongs to.")

        payload: dict[str, Any] = {
            "message_id": message_id,
            "workspace_id": workspace_id,
            "conversation_id": conversation_id,
            "status": answer.status.value,
            "content": answer.content,
            "evidence_considered": answer.evidence_considered,
            "evidence_cited": answer.evidence_cited,
        }
        if answer.abstention_reason is not None:
            payload["abstention_reason"] = answer.abstention_reason
        if execution_id is not None:
            payload["execution_id"] = execution_id
        try:
            response = self._write.table("answers").insert(payload).execute()
        except APIError as exc:
            raise _translate(exc) from exc
        rows = response.data or []
        if not rows:
            raise _translate_error_message("The answer could not be stored.")
        answer_id = str(cast("dict[str, Any]", rows[0])["id"])

        if answer.claims:
            claim_rows = [
                {
                    "answer_id": answer_id,
                    "workspace_id": workspace_id,
                    "claim_index": claim.index,
                    "text": claim.text,
                }
                for claim in answer.claims
            ]
            try:
                claim_response = self._write.table("claims").insert(claim_rows).execute()
            except APIError as exc:
                raise _translate(exc) from exc
            stored_claims = {
                int(row["claim_index"]): str(row["id"]) for row in claim_response.data or []
            }

            citation_rows = [
                {
                    "claim_id": stored_claims[claim.index],
                    "provenance_id": citation.provenance_id,
                    "workspace_id": workspace_id,
                    "quoted_text": citation.quoted_text,
                    "relevance": citation.relevance,
                }
                for claim in answer.claims
                if claim.index in stored_claims
                for citation in claim.citations
            ]
            if citation_rows:
                try:
                    self._write.table("claim_citations").insert(citation_rows).execute()
                except APIError as exc:
                    raise _translate(exc) from exc

        return answer_id

    def get_answer(self, answer_id: str) -> dict[str, Any] | None:
        try:
            response = (
                self._read.table("answers").select("*").eq("id", answer_id).maybe_single().execute()
            )
        except APIError as exc:
            raise _translate(exc) from exc
        if not response or not response.data:
            return None
        return cast("dict[str, Any]", response.data)

    def list_claims(self, answer_id: str) -> list[Claim]:
        try:
            claim_response = (
                self._read.table("claims")
                .select("*")
                .eq("answer_id", answer_id)
                .order("claim_index", desc=False)
                .execute()
            )
            citation_response = (
                self._read.table("claim_citations")
                .select("claim_id,provenance_id,quoted_text,relevance")
                .in_(
                    "claim_id",
                    [str(row["id"]) for row in claim_response.data or []] or [_NIL_UUID],
                )
                .execute()
            )
        except APIError as exc:
            raise _translate(exc) from exc

        by_claim: dict[str, list[dict[str, Any]]] = {}
        for row in citation_response.data or []:
            by_claim.setdefault(str(row["claim_id"]), []).append(cast("dict[str, Any]", row))

        from app.domain.conversation import CitationDraft

        claims: list[Claim] = []
        for row in claim_response.data or []:
            record = cast("dict[str, Any]", row)
            claim_id = str(record["id"])
            claims.append(
                Claim(
                    id=claim_id,
                    answer_id=answer_id,
                    claim_index=int(record["claim_index"]),
                    text=str(record["text"]),
                    support=ClaimSupport(str(record["support"])),
                    verification_note=cast("str | None", record.get("verification_note")),
                    citations=[
                        CitationDraft(
                            provenance_id=str(citation["provenance_id"]),
                            quoted_text=cast("str | None", citation.get("quoted_text")),
                            relevance=cast("float | None", citation.get("relevance")),
                        )
                        for citation in by_claim.get(claim_id, [])
                    ],
                )
            )
        return claims


def _translate_error_message(message: str) -> MnemosError:
    from app.core.errors import MnemosError as BaseError

    class _RepositoryWriteError(BaseError):
        status_code = 502
        code = "repository_write_failed"
        default_message = message

    return _RepositoryWriteError()


def _translate(exc: APIError) -> MnemosError:
    from app.repositories.supabase_repositories import _BaseSupabaseRepository

    return _BaseSupabaseRepository._translate(exc)
