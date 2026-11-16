"""Supabase persistence for orchestration traces (Phase 3D).

Reads use the caller's client so RLS decides what a member may see. Writes use
the server-side client because `authenticated` deliberately has no INSERT grant
on the trace tables: a trace a client can write is not evidence.

Every method here corresponds to a row that the orchestration service writes
immediately after the work it describes. Nothing is batched, so a process that
dies mid-run leaves a trace showing exactly how far it got.
"""

from __future__ import annotations

import logging
from typing import Any, cast

from postgrest.exceptions import APIError

from app.core.errors import ConfigurationError, MnemosError

logger = logging.getLogger("mnemos.repositories.agents")

_NIL_UUID = "00000000-0000-0000-0000-000000000000"


class TraceWriteError(MnemosError):
    """A trace row could not be written."""

    status_code = 500
    code = "trace_write_failed"


def _write_failed(exc: APIError) -> MnemosError:
    message = str(exc.message or "unknown error")
    logger.error("Trace write failed: %s", message)
    if "permission denied" in message.lower():
        return TraceWriteError(
            message=(
                "The trace could not be recorded because the server lacks write "
                "access to the trace tables. Run the agent migration."
            )
        )
    if "connection" in message.lower() or "timeout" in message.lower():
        return ConfigurationError(message="The database is temporarily unavailable.")
    return TraceWriteError(message=f"The trace could not be recorded: {message}")


class SupabaseTraceRepository:
    """Implements ``app.domain.agents.TraceStore``."""

    def __init__(self, read_client: Any, write_client: Any) -> None:
        self._read = read_client
        self._write = write_client

    # --- orchestration ----------------------------------------------------

    def start_orchestration(self, record: dict[str, Any]) -> str:
        payload = {
            **record,
            "conversation_id": record.get("conversation_id") or None,
            "plan": list(record.get("plan") or []),
        }
        try:
            response = self._write.table("orchestration_runs").insert(payload).execute()
        except APIError as exc:
            raise _write_failed(exc) from exc
        rows = cast("list[dict[str, Any]]", response.data or [])
        if not rows:
            raise TraceWriteError(message="The orchestration run was not created.")
        return str(rows[0]["id"])

    def finish_orchestration(self, orchestration_id: str, record: dict[str, Any]) -> None:
        payload = {
            "status": record["status"],
            "completed_at": record.get("completed_at"),
            "total_latency_ms": record.get("total_latency_ms"),
            "total_tokens": record.get("total_tokens"),
            "answer_id": record.get("answer_id") or None,
        }
        try:
            self._write.table("orchestration_runs").update(payload).eq(
                "id", orchestration_id
            ).execute()
        except APIError as exc:
            # A trace that cannot be completed must not fail the user's answer;
            # it is logged loudly instead, because silence would be dishonest.
            logger.error("Could not finalise orchestration %s: %s", orchestration_id, exc.message)

    # --- agent runs -------------------------------------------------------

    def start_agent_run(
        self, orchestration_id: str, workspace_id: str, record: dict[str, Any]
    ) -> str:
        payload = {
            "orchestration_id": orchestration_id or None,
            "workspace_id": workspace_id,
            "role": record["role"],
            "status": record.get("status", "running"),
            "input_summary": record.get("input_summary") or {},
            "started_at": record.get("started_at"),
        }
        try:
            response = self._write.table("agent_runs").insert(payload).execute()
        except APIError as exc:
            raise _write_failed(exc) from exc
        rows = cast("list[dict[str, Any]]", response.data or [])
        if not rows:
            raise TraceWriteError(message="The agent run was not created.")
        return str(rows[0]["id"])

    def finish_agent_run(self, agent_run_id: str, record: dict[str, Any]) -> None:
        payload = {
            "status": record["status"],
            "output_summary": record.get("output_summary") or {},
            "error_code": record.get("error_code"),
            "step_count": record.get("step_count", 0),
            "latency_ms": record.get("latency_ms"),
            "completed_at": record.get("completed_at"),
        }
        try:
            self._write.table("agent_runs").update(payload).eq("id", agent_run_id).execute()
        except APIError as exc:
            logger.error("Could not finalise agent run %s: %s", agent_run_id, exc.message)

    def append_step(self, agent_run_id: str, workspace_id: str, step: dict[str, Any]) -> None:
        payload = {
            "agent_run_id": agent_run_id,
            "workspace_id": workspace_id,
            "step_index": step["step_index"],
            "capability": step["capability"],
            "status": step["status"],
            "detail": step.get("detail") or {},
            "latency_ms": step.get("latency_ms"),
        }
        try:
            self._write.table("agent_steps").insert(payload).execute()
        except APIError as exc:
            logger.error(
                "Could not record step %s of run %s: %s",
                step["step_index"],
                agent_run_id,
                exc.message,
            )

    # --- reads ------------------------------------------------------------

    def trace(self, orchestration_id: str) -> list[dict[str, Any]]:
        """Flattened trace as the caller. RLS scopes it to their workspaces."""
        try:
            response = self._read.rpc(
                "orchestration_trace", {"p_orchestration_id": orchestration_id}
            ).execute()
        except APIError as exc:
            raise _write_failed(exc) from exc
        return cast("list[dict[str, Any]]", response.data or [])

    def get_orchestration(self, orchestration_id: str) -> dict[str, Any] | None:
        try:
            response = (
                self._read.table("orchestration_runs")
                .select("*")
                .eq("id", orchestration_id)
                .maybe_single()
                .execute()
            )
        except APIError as exc:
            raise _write_failed(exc) from exc
        if not response or not response.data:
            return None
        return cast("dict[str, Any]", response.data)

    def list_orchestrations(self, workspace_id: str, *, limit: int = 20) -> list[dict[str, Any]]:
        try:
            response = (
                self._read.table("orchestration_runs")
                .select("*")
                .eq("workspace_id", workspace_id)
                .order("started_at", desc=True)
                .limit(limit)
                .execute()
            )
        except APIError as exc:
            raise _write_failed(exc) from exc
        return cast("list[dict[str, Any]]", response.data or [])
