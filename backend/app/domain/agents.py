"""Agent roles, capabilities and orchestration traces (Phase 3D).

An agent here is a *named role with a restricted capability set*, not an
autonomous process. Four roles cooperate on one question:

``researcher``  retrieve evidence, nothing else
``analyst``     turn evidence into a grounded answer, nothing else
``critic``      check the answer against the evidence, nothing else
``orchestrator`` decide the plan and own the trace, never the answer text

The separation is the point. An agent that could both write an answer and
approve it would be marking its own work, which is exactly what Phase 3C
exists to prevent. Capabilities are enforced by construction: each agent
receives only the services its capability set allows, so an attempt to call an
absent capability is an AttributeError at the seam, not a policy comment.

Traces are records of what happened. Every step in ``AgentStep`` is appended by
the code that performed the work, immediately after performing it — there is no
path that writes a step without doing it.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal, Protocol

AgentRoleName = Literal["orchestrator", "researcher", "analyst", "critic"]


class AgentCapability(StrEnum):
    """What an agent is allowed to do.

    Deliberately small. There is no ``execute_sql``, no ``write_file`` and no
    ``call_paid_api``: the system cannot be extended into an agent that does
    those things by configuration alone.
    """

    RETRIEVE = "retrieve"
    GENERATE = "generate"
    VERIFY = "verify"
    CRITIQUE = "critique"
    SYNTHESISE = "synthesise"


class RunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


class OrchestrationStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class AgentStep:
    """One capability invocation, appended after it completed."""

    capability: AgentCapability
    status: RunStatus
    detail: dict[str, Any] = field(default_factory=dict)
    latency_ms: int | None = None


@dataclass(frozen=True, slots=True)
class AgentSpec:
    """Static description of a role. Configuration cannot widen its capabilities."""

    role: AgentRoleName
    purpose: str
    capabilities: frozenset[AgentCapability]
    model_role: str | None

    @property
    def is_llm_driven(self) -> bool:
        return self.model_role is not None


RESEARCHER = AgentSpec(
    role="researcher",
    purpose="Find the workspace passages that bear on the question.",
    capabilities=frozenset({AgentCapability.RETRIEVE}),
    model_role=None,
)

ANALYST = AgentSpec(
    role="analyst",
    purpose="Write an answer that uses only the evidence it was given.",
    capabilities=frozenset({AgentCapability.GENERATE}),
    model_role="generation",
)

CRITIC = AgentSpec(
    role="critic",
    purpose="Check the analyst's claims against the same evidence.",
    capabilities=frozenset({AgentCapability.VERIFY, AgentCapability.CRITIQUE}),
    model_role="verification",
)

ORCHESTRATOR = AgentSpec(
    role="orchestrator",
    purpose="Choose the plan and record what the specialists did.",
    capabilities=frozenset({AgentCapability.SYNTHESISE}),
    model_role=None,
)

AGENTS: dict[AgentRoleName, AgentSpec] = {
    "orchestrator": ORCHESTRATOR,
    "researcher": RESEARCHER,
    "analyst": ANALYST,
    "critic": CRITIC,
}


def spec_for(role: AgentRoleName) -> AgentSpec:
    """Look up a role's declaration. Unknown roles are a programming error."""
    try:
        return AGENTS[role]
    except KeyError as exc:  # pragma: no cover - Literal type prevents this
        raise AgentSpecError(f"unknown agent role: {role}") from exc


class AgentSpecError(ValueError):
    """Raised when an agent is asked for a capability it does not have."""


def require_capability(spec: AgentSpec, capability: AgentCapability) -> None:
    """Guard used at the seam, so a missing capability fails loudly.

    The primary defence is that the agent is never constructed with a service it
    should not call. This is the belt to that braces: if wiring drifts, the call
    fails with a clear message instead of quietly succeeding.
    """
    if capability not in spec.capabilities:
        raise AgentSpecError(
            f"agent '{spec.role}' does not have the '{capability.value}' capability"
        )


@dataclass(slots=True)
class AgentRun:
    """Mutable record of one agent invocation, built as the work happens."""

    role: AgentRoleName
    status: RunStatus = RunStatus.RUNNING
    steps: list[AgentStep] = field(default_factory=list)
    input_summary: dict[str, Any] = field(default_factory=dict)
    output_summary: dict[str, Any] = field(default_factory=dict)
    error_code: str | None = None
    started_at: dt.datetime | None = None
    completed_at: dt.datetime | None = None

    @property
    def latency_ms(self) -> int | None:
        if self.started_at is None or self.completed_at is None:
            return None
        delta = self.completed_at - self.started_at
        return max(0, int(delta.total_seconds() * 1000))

    @property
    def step_count(self) -> int:
        return len(self.steps)

    def append(self, step: AgentStep) -> None:
        """Record a step that has already happened."""
        self.steps.append(step)

    def succeed(self, *, completed: dt.datetime) -> None:
        self.status = RunStatus.SUCCEEDED
        self.completed_at = completed

    def fail(self, *, error_code: str, completed: dt.datetime) -> None:
        self.status = RunStatus.FAILED
        self.error_code = error_code
        self.completed_at = completed

    def skip(self, *, reason: str, completed: dt.datetime) -> None:
        self.status = RunStatus.SKIPPED
        self.output_summary = {**self.output_summary, "skipped_reason": reason}
        self.completed_at = completed

    def as_record(self) -> dict[str, Any]:
        """Plain mapping for the repository. No prompt or document text."""
        return {
            "role": self.role,
            "status": self.status.value,
            "input_summary": self.input_summary,
            "output_summary": self.output_summary,
            "error_code": self.error_code,
            "step_count": self.step_count,
            "latency_ms": self.latency_ms,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }


@dataclass(slots=True)
class OrchestrationPlan:
    """The chosen plan, recorded before the work so deviations stay visible."""

    roles: tuple[AgentRoleName, ...]
    reason: str

    def as_record(self) -> list[str]:
        return list(self.roles)


@dataclass(slots=True)
class OrchestrationRun:
    """One orchestrated question and the agents that served it."""

    question: str
    plan: OrchestrationPlan
    workspace_id: str
    conversation_id: str | None = None
    answer_id: str | None = None
    status: OrchestrationStatus = OrchestrationStatus.RUNNING
    runs: list[AgentRun] = field(default_factory=list)
    started_at: dt.datetime | None = None
    completed_at: dt.datetime | None = None
    total_tokens: int | None = None

    @property
    def total_latency_ms(self) -> int | None:
        if self.started_at is None or self.completed_at is None:
            return None
        return max(0, int((self.completed_at - self.started_at).total_seconds() * 1000))

    def run_for(self, role: AgentRoleName) -> AgentRun | None:
        for run in self.runs:
            if run.role == role:
                return run
        return None

    @property
    def degraded(self) -> bool:
        """True when a specialist failed or was skipped but an answer was produced.

        Degradation is reported rather than hidden: an answer that skipped the
        critic is a weaker answer, and the response says so.
        """
        return any(run.status in (RunStatus.FAILED, RunStatus.SKIPPED) for run in self.runs)

    @property
    def trace(self) -> list[dict[str, Any]]:
        """Ordered trace for the API response."""
        return [
            {
                "role": run.role,
                "status": run.status.value,
                "latency_ms": run.latency_ms,
                "step_count": run.step_count,
                "steps": [
                    {
                        "capability": step.capability.value,
                        "status": step.status.value,
                        "detail": step.detail,
                        "latency_ms": step.latency_ms,
                    }
                    for step in run.steps
                ],
                "error_code": run.error_code,
                "output_summary": run.output_summary,
            }
            for run in self.runs
        ]


class TraceStore(Protocol):
    """Persistence seam for orchestration traces."""

    def start_orchestration(self, record: dict[str, Any]) -> str: ...

    def finish_orchestration(self, orchestration_id: str, record: dict[str, Any]) -> None: ...

    def start_agent_run(
        self, orchestration_id: str, workspace_id: str, record: dict[str, Any]
    ) -> str: ...

    def finish_agent_run(self, agent_run_id: str, record: dict[str, Any]) -> None: ...

    def append_step(self, agent_run_id: str, workspace_id: str, step: dict[str, Any]) -> None: ...

    def trace(self, orchestration_id: str) -> list[dict[str, Any]]: ...
