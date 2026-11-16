"""Orchestration tests (Phase 3D).

The properties worth protecting are about honesty of the trace, not about
whether four objects were constructed:

* a step is never recorded for work that did not happen;
* a skipped critic is recorded as skipped, with a reason, and the answer is
  marked degraded;
* a failed analyst produces no answer and no invented trace;
* capability isolation actually stops an agent doing another's job;
* an agent that is given a fake recorder cannot smuggle extra steps in.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field
from typing import Any

import pytest

from app.core.errors import ForbiddenError, NotFoundError, ValidationError
from app.domain.agents import (
    AGENTS,
    AgentCapability,
    AgentRun,
    AgentSpecError,
    OrchestrationStatus,
    RunStatus,
    require_capability,
    spec_for,
)
from app.domain.conversation import (
    AgentRole,
    AnswerOutcome,
    AnswerStatus,
    ClaimDraft,
    ExecutionRecord,
    ExecutionStatus,
)
from app.domain.models import Workspace, WorkspaceMember, WorkspaceRole
from app.domain.retrieval import (
    InformationStatus,
    RetrievalSource,
    RetrievedPassage,
    SourceKind,
)
from app.domain.verification import (
    AnswerVerification,
    ClaimVerdict,
    VerificationMethod,
)
from app.services.conversation_service import AskResult
from app.services.generation import GenerationFailedError
from app.services.orchestration import OrchestrationService

WS = "33333333-3333-4333-8333-333333333333"
USER = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"
STAMP = dt.datetime(2026, 11, 15, tzinfo=dt.UTC)


# --- fakes ---------------------------------------------------------------


class FakeWorkspaces:
    def __init__(self, members: list[WorkspaceMember] | None = None) -> None:
        self.members = members if members is not None else [member()]

    def get(self, workspace_id: str) -> Workspace | None:
        return Workspace(
            id=workspace_id,
            owner_id=USER,
            name="R",
            slug="r",
            description=None,
            created_at=STAMP,
            updated_at=STAMP,
        )

    def list_members(self, workspace_id: str) -> list[WorkspaceMember]:
        return self.members


def member(user_id: str = USER, role: WorkspaceRole = WorkspaceRole.OWNER) -> WorkspaceMember:
    return WorkspaceMember(workspace_id=WS, user_id=user_id, role=role, created_at=STAMP)


def passage(
    provenance_id: str = "prov-a", content: str = "A passport is required."
) -> RetrievedPassage:
    return RetrievedPassage(
        chunk_id="chunk-a",
        provenance_id=provenance_id,
        source_id="source-a",
        document_version_id="version-a",
        workspace_id=WS,
        source_title="Policy",
        source_kind=SourceKind.DOCUMENT,
        version_number=1,
        version_is_current=True,
        information_status=InformationStatus.CURRENT,
        chunk_index=0,
        content=content,
        char_count=len(content),
        source_location={"page": 1, "start_offset": 0, "end_offset": len(content)},
        lexical_rank=1,
        semantic_rank=None,
        lexical_score=0.9,
        semantic_similarity=None,
        fused_score=0.9,
        matched_by=RetrievalSource.LEXICAL,
    )


def execution(*, tokens: int = 42) -> ExecutionRecord:
    return ExecutionRecord(
        id="exec-1",
        workspace_id=WS,
        conversation_id="conv-1",
        agent_role=AgentRole.ORCHESTRATOR,
        purpose="answer",
        model_id="fake/model",
        status=ExecutionStatus.SUCCEEDED,
        latency_ms=120,
        prompt_tokens=tokens - 10,
        completion_tokens=10,
        total_tokens=tokens,
    )


def answer_outcome(
    *,
    status: AnswerStatus = AnswerStatus.ANSWERED,
    claims: int = 2,
    evidence_considered: int = 1,
) -> AnswerOutcome:
    passages = [passage()] if evidence_considered else []
    return AnswerOutcome(
        answer_id="answer-1",
        status=status,
        content="A passport is required." if status is AnswerStatus.ANSWERED else "I cannot say.",
        abstention_reason=None if status is AnswerStatus.ANSWERED else "No evidence.",
        claims=[
            ClaimDraft(index=index, text=f"Claim {index}.", citations=[])
            for index in range(claims if status is AnswerStatus.ANSWERED else 0)
        ],
        evidence_considered=evidence_considered,
        evidence_cited=evidence_considered,
        citations_by_claim=(
            {0: ["prov-a"]} if status is AnswerStatus.ANSWERED and evidence_considered else {}
        ),
        passages=passages,
        execution=execution(),
    )


class FakeConversations:
    def __init__(
        self,
        *,
        status: AnswerStatus = AnswerStatus.ANSWERED,
        claims: int = 2,
        evidence_considered: int = 1,
        error: Exception | None = None,
    ) -> None:
        self.status = status
        self.claims = claims
        self.evidence_considered = evidence_considered
        self.error = error
        self.calls = 0

    async def ask(self, **kwargs: Any) -> AskResult:
        self.calls += 1
        if self.error is not None:
            raise self.error
        outcome = answer_outcome(
            status=self.status, claims=self.claims, evidence_considered=self.evidence_considered
        )
        return AskResult(
            conversation_id="conv-1",
            question_message=_message("user", kwargs["question"]),
            answer_message=_message("assistant", outcome.content),
            answer=outcome,
            execution=outcome.execution or execution(),
        )


def _message(role: str, content: str) -> Any:
    from app.domain.conversation import Message, MessageRole

    return Message(
        id=f"msg-{role}",
        conversation_id="conv-1",
        workspace_id=WS,
        role=MessageRole(role),
        content=content,
        sequence_number=0,
        execution_id=None,
        created_at=STAMP,
    )


class FakeVerification:
    def __init__(self, *, supported: int = 2, error: Exception | None = None) -> None:
        self.supported = supported
        self.error = error
        self.calls = 0

    async def verify_answer(self, **kwargs: Any) -> AnswerVerification:
        self.calls += 1
        if self.error is not None:
            raise self.error
        verdicts = [
            ClaimVerdict(
                claim_id=f"claim-{index}",
                verdict="supported",
                method=VerificationMethod.LEXICAL_OVERLAP,
                confidence=0.9,
                explanation="Matches.",
                supporting_chunk_ids=["chunk-a"],
                contradicted_by_chunk_ids=[],
            )
            for index in range(self.supported)
        ]
        return AnswerVerification(
            answer_id=kwargs["answer_id"],
            verifications=verdicts,
            method=VerificationMethod.LEXICAL_OVERLAP,
            supported=self.supported,
            unsupported=0,
            unverified=0,
            contradicted=0,
        )


@dataclass
class FakeTraceStore:
    """Records every trace call so the test can assert what was written."""

    orchestrations: list[dict[str, Any]] = field(default_factory=list)
    finished: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    runs: list[tuple[str, str, dict[str, Any]]] = field(default_factory=list)
    finished_runs: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    steps: list[tuple[str, str, dict[str, Any]]] = field(default_factory=list)
    fail_start: bool = False

    def start_orchestration(self, record: dict[str, Any]) -> str:
        if self.fail_start:
            raise AssertionError("trace store should not be written")
        self.orchestrations.append(record)
        return "orch-1"

    def finish_orchestration(self, orchestration_id: str, record: dict[str, Any]) -> None:
        self.finished.append((orchestration_id, record))

    def start_agent_run(
        self, orchestration_id: str, workspace_id: str, record: dict[str, Any]
    ) -> str:
        self.runs.append((orchestration_id, workspace_id, record))
        return f"run-{len(self.runs)}"

    def finish_agent_run(self, agent_run_id: str, record: dict[str, Any]) -> None:
        self.finished_runs.append((agent_run_id, record))

    def append_step(self, agent_run_id: str, workspace_id: str, step: dict[str, Any]) -> None:
        self.steps.append((agent_run_id, workspace_id, step))

    def trace(self, orchestration_id: str) -> list[dict[str, Any]]:
        return []


def service(
    *,
    conversations: FakeConversations | None = None,
    verification: FakeVerification | None = None,
    traces: FakeTraceStore | None = None,
    verifier_available: bool = True,
    members: list[WorkspaceMember] | None = None,
) -> tuple[OrchestrationService, FakeTraceStore, FakeConversations, FakeVerification]:
    store = traces if traces is not None else FakeTraceStore()
    convo = conversations if conversations is not None else FakeConversations()
    checker = verification if verification is not None else FakeVerification()
    svc = OrchestrationService(
        workspaces=FakeWorkspaces(members),
        conversations=convo,  # type: ignore[arg-type]
        generation=None,  # type: ignore[arg-type]
        verification=checker,  # type: ignore[arg-type]
        traces=store,
        verifier_available=verifier_available,
    )
    return svc, store, convo, checker


def role_of(record: dict[str, Any]) -> str:
    return str(record["role"])


# --- capability isolation ------------------------------------------------


def test_researcher_cannot_generate() -> None:
    with pytest.raises(AgentSpecError):
        require_capability(spec_for("researcher"), AgentCapability.GENERATE)


def test_analyst_cannot_verify() -> None:
    """An agent that can grade its own answer is not a check."""
    with pytest.raises(AgentSpecError):
        require_capability(spec_for("analyst"), AgentCapability.VERIFY)


def test_critic_cannot_generate_or_retrieve() -> None:
    critic = spec_for("critic")
    assert AgentCapability.GENERATE not in critic.capabilities
    assert AgentCapability.RETRIEVE not in critic.capabilities


def test_every_agent_role_is_declared() -> None:
    assert set(AGENTS) == {"orchestrator", "researcher", "analyst", "critic"}


def test_agent_specs_are_immutable() -> None:
    with pytest.raises(AttributeError):
        spec_for("analyst").purpose = "changed"  # type: ignore[misc]


# --- planning ------------------------------------------------------------


def test_plan_includes_a_critic_when_a_verification_model_exists() -> None:
    svc, _, _, _ = service(verifier_available=True)
    plan = svc.plan()
    assert "critic" in plan.roles
    assert "verif" in plan.reason.lower()


def test_plan_omits_the_critic_and_says_why_when_unavailable() -> None:
    svc, _, _, _ = service(verifier_available=False)
    plan = svc.plan()
    assert "critic" not in plan.roles
    assert "skipped" in plan.reason.lower()


def test_plan_can_be_told_not_to_verify() -> None:
    svc, _, _, _ = service(verifier_available=True)
    plan = svc.plan(verify=False)
    assert "critic" not in plan.roles


# --- happy path ----------------------------------------------------------


async def test_orchestration_records_the_plan_before_the_work() -> None:
    svc, traces, _, _ = service()
    await svc.ask(workspace_id=WS, user_id=USER, question="Do I need a passport?")
    assert traces.orchestrations[0]["plan"] == ["orchestrator", "researcher", "analyst", "critic"]
    assert traces.orchestrations[0]["status"] == "running"


async def test_every_agent_run_is_started_and_finished() -> None:
    svc, traces, _, _ = service()
    await svc.ask(workspace_id=WS, user_id=USER, question="Do I need a passport?")
    started = [role_of(record) for _, _, record in traces.runs]
    assert started == ["orchestrator", "researcher", "analyst", "critic"]
    assert len(traces.finished_runs) == 4
    for _, record in traces.finished_runs:
        assert record["status"] == "succeeded"
        assert record["completed_at"] is not None


async def test_a_step_is_recorded_for_each_successful_capability() -> None:
    svc, traces, _, _ = service()
    await svc.ask(workspace_id=WS, user_id=USER, question="Do I need a passport?")
    # Steps are written as each run finishes, so the orchestrator's own step
    # comes last: it closes the trace with what the specialists actually did.
    capabilities = [step["capability"] for _, _, step in traces.steps]
    assert capabilities == ["retrieve", "generate", "verify", "synthesise"]


async def test_steps_are_written_after_their_work_completed() -> None:
    """A step recorded before the work would be a prediction, not evidence."""
    svc, traces, conversations, _ = service()
    await svc.ask(workspace_id=WS, user_id=USER, question="Do I need a passport?")
    assert conversations.calls == 1
    # The generate step exists, so the generation must have happened first.
    assert any(step["capability"] == "generate" for _, _, step in traces.steps)


async def test_the_answer_records_the_conversation_it_belongs_to() -> None:
    svc, _, _, _ = service()
    result = await svc.ask(workspace_id=WS, user_id=USER, question="q")
    assert result.conversation_id == "conv-1"


async def test_the_critic_verifies_the_answer_the_analyst_produced() -> None:
    svc, _, _, checker = service()
    result = await svc.ask(workspace_id=WS, user_id=USER, question="q")
    assert checker.calls == 1
    assert result.verification is not None
    assert result.verification.supported == 2
    assert result.degraded is False


async def test_token_usage_is_aggregated_from_the_execution_record() -> None:
    svc, traces, _, _ = service()
    await svc.ask(workspace_id=WS, user_id=USER, question="q")
    assert traces.finished[0][1]["total_tokens"] == 42


# --- degradation ---------------------------------------------------------


async def test_a_skipped_critic_marks_the_answer_degraded() -> None:
    svc, traces, _, checker = service(verifier_available=False)
    result = await svc.ask(workspace_id=WS, user_id=USER, question="q")
    assert checker.calls == 0
    assert result.degraded is True
    assert result.verification is None
    critic = [r for _, _, r in traces.runs if r["role"] == "critic"]
    assert critic == [], "a critic that did not run must not appear as a run"
    reason = (result.verification_skipped_reason or "").lower()
    assert "skipped" in reason or "not requested" in reason


async def test_an_abstention_skips_the_critic_with_a_reason() -> None:
    svc, _traces, _, checker = service()
    await svc.ask(workspace_id=WS, user_id=USER, question="q")
    # Normal path first: the critic ran.
    assert checker.calls == 1
    svc2, traces2, _, checker2 = service(
        conversations=FakeConversations(
            status=AnswerStatus.INSUFFICIENT_EVIDENCE, claims=0, evidence_considered=0
        )
    )
    result2 = await svc2.ask(workspace_id=WS, user_id=USER, question="q")
    assert checker2.calls == 0
    critic_run = [r for _, _, r in traces2.runs if r["role"] == "critic"]
    assert len(critic_run) == 1
    finished_critic = [r for _, r in traces2.finished_runs if r["role"] == "critic"]
    assert finished_critic, "the critic run must be recorded"
    assert finished_critic[0]["status"] == "skipped"
    assert "nothing to verify" in finished_critic[0]["output_summary"]["skipped_reason"].lower()
    assert result2.verification is None


async def test_a_failed_critic_does_not_destroy_the_answer() -> None:
    """Losing the check degrades the answer; it does not void it."""
    from app.core.errors import MnemosError

    svc, traces, _, _ = service(
        verification=FakeVerification(error=MnemosError(message="verifier down"))
    )
    result = await svc.ask(workspace_id=WS, user_id=USER, question="q")
    assert result.outcome.status is AnswerStatus.ANSWERED
    assert result.degraded is True
    assert result.verification is None
    critic = [r for _, r in traces.finished_runs if r["role"] == "critic"]
    assert critic[0]["status"] == "failed"
    assert critic[0]["error_code"] == "MnemosError"


async def test_a_critic_without_evidence_text_fails_rather_than_passing() -> None:
    """An answer with claims but no readable passage cannot be called verified."""
    svc, traces, _, _ = service(conversations=FakeConversations(claims=2, evidence_considered=0))
    result = await svc.ask(workspace_id=WS, user_id=USER, question="q")
    assert result.verification is None
    critic = [r for _, r in traces.finished_runs if r["role"] == "critic"]
    assert critic[0]["status"] in {"failed", "skipped"}
    assert critic[0]["status"] != "succeeded"


async def test_a_failed_analyst_produces_no_answer_and_a_failed_trace() -> None:
    svc, traces, _, _ = service(
        conversations=FakeConversations(error=GenerationFailedError(message="model down"))
    )
    with pytest.raises(GenerationFailedError):
        await svc.ask(workspace_id=WS, user_id=USER, question="q")
    assert traces.finished[0][1]["status"] == "failed"
    assert traces.finished[0][1]["answer_id"] is None
    failed_roles = {r["role"] for _, r in traces.finished_runs if r["status"] == "failed"}
    assert failed_roles == {"researcher", "analyst"}
    # Nothing may be recorded as succeeded when the run failed.
    assert not any(step["status"] == "succeeded" for _, _, step in traces.steps)


# --- authorization -------------------------------------------------------


async def test_a_non_member_cannot_orchestrate() -> None:
    svc, _, _, _ = service(members=[member(OTHER)])
    with pytest.raises(ForbiddenError):
        await svc.ask(workspace_id=WS, user_id=USER, question="q")


async def test_a_missing_workspace_is_not_found() -> None:
    svc = OrchestrationService(
        workspaces=FakeWorkspaces([]),
        conversations=FakeConversations(),  # type: ignore[arg-type]
        generation=None,  # type: ignore[arg-type]
        verification=FakeVerification(),  # type: ignore[arg-type]
        traces=FakeTraceStore(),
        verifier_available=True,
    )
    svc._workspaces.get = lambda workspace_id: None  # type: ignore[method-assign]
    with pytest.raises(NotFoundError):
        await svc.ask(workspace_id=WS, user_id=USER, question="q")


async def test_an_empty_question_is_rejected_before_any_trace_is_written() -> None:
    svc, traces, conversations, _ = service()
    with pytest.raises(ValidationError):
        await svc.ask(workspace_id=WS, user_id=USER, question="   ")
    assert traces.orchestrations == []
    assert conversations.calls == 0


# --- trace content -------------------------------------------------------


async def test_the_trace_carries_results_not_document_text() -> None:
    """A trace is metadata. Storing passage text in it would duplicate the corpus."""
    svc, traces, _, _ = service()
    await svc.ask(workspace_id=WS, user_id=USER, question="Do I need a passport?")
    serialized = json.dumps(
        {
            "runs": [record for _, _, record in traces.runs],
            "steps": [step for _, _, step in traces.steps],
            "finished": [record for _, record in traces.finished],
        },
        default=str,
    )
    assert "A passport is required." not in serialized
    assert "Do I need a passport?" not in serialized


async def test_the_orchestration_metadata_records_why_the_plan_was_chosen() -> None:
    svc, traces, _, _ = service(verifier_available=False)
    await svc.ask(workspace_id=WS, user_id=USER, question="q")
    assert "skipped" in traces.orchestrations[0]["metadata"]["plan_reason"].lower()


async def test_run_latency_is_measured_not_guessed() -> None:
    run = AgentRun(
        role="analyst",
        started_at=dt.datetime(2026, 11, 15, 10, 0, 0, tzinfo=dt.UTC),
        completed_at=dt.datetime(2026, 11, 15, 10, 0, 0, 250000, tzinfo=dt.UTC),
    )
    assert run.latency_ms == 250


async def test_an_unfinished_run_reports_no_latency() -> None:
    run = AgentRun(role="analyst", started_at=STAMP)
    assert run.latency_ms is None


async def test_orchestration_status_is_succeeded_only_when_the_whole_run_completed() -> None:
    svc, traces, _, _ = service()
    await svc.ask(workspace_id=WS, user_id=USER, question="q")
    assert traces.finished[0][1]["status"] == OrchestrationStatus.SUCCEEDED.value


def test_run_status_distinguishes_skipped_from_failed() -> None:
    """Skipped means "not attempted"; failed means "attempted and did not work"."""
    assert RunStatus.SKIPPED != RunStatus.FAILED
    run = AgentRun(role="critic")
    run.skip(reason="no verifier", completed=STAMP)
    assert run.status is RunStatus.SKIPPED
    assert run.output_summary["skipped_reason"] == "no verifier"
