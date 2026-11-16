"""Multi-agent orchestration (Phase 3D).

Four roles cooperate on one question:

    orchestrator → choose the plan, record what actually happened
    researcher   → the evidence that retrieval selected
    analyst      → write a grounded answer from that evidence only
    critic       → check the analyst's claims against the same evidence

Three rules make this an orchestration of agents rather than one service call
wearing four labels:

1. **Capability isolation.** Each role declares what it may do, and the run
   asserts the capability before doing it. The critic cannot write or amend the
   answer; the analyst cannot retrieve fresh evidence of its own after the fact.
2. **Trace fidelity.** A step row is written after the work it describes has
   completed, and only from the code path that did the work. A trace therefore
   cannot contain work that did not happen.
3. **Honest degradation.** If the critic fails, the answer is returned and
   marked degraded with the reason. If the analyst fails, no answer is invented.
   Skipped is never recorded as succeeded.

Why the plan is fixed in advance
    Because otherwise the trace would be a description rather than a control. The
    only branch is whether a critic runs, and that follows configuration, not a
    model's opinion about which agents it would like.
"""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass
from typing import Any

from app.core.errors import ForbiddenError, MnemosError, NotFoundError, ValidationError
from app.domain.agents import (
    AgentCapability,
    AgentRoleName,
    AgentRun,
    AgentStep,
    OrchestrationPlan,
    OrchestrationRun,
    OrchestrationStatus,
    RunStatus,
    TraceStore,
    require_capability,
    spec_for,
)
from app.domain.conversation import AnswerOutcome, AnswerStatus, ExecutionRecord
from app.domain.models import WorkspaceRole
from app.domain.retrieval import RetrievedPassage
from app.domain.verification import AnswerVerification, VerificationMethod
from app.services.conversation_service import AskResult, ConversationService
from app.services.generation import GenerationOptions, GenerationOutcome, GenerationService
from app.services.verification import PassageText, VerificationService

logger = logging.getLogger("mnemos.orchestration")


class OrchestrationFailedError(MnemosError):
    """The orchestration could not produce an answer."""


@dataclass(frozen=True, slots=True)
class OrchestrationResult:
    """The answer plus how it was produced."""

    outcome: AnswerOutcome
    execution: ExecutionRecord
    run: OrchestrationRun
    verification: AnswerVerification | None
    conversation_id: str
    model_reported: str | None = None

    @property
    def degraded(self) -> bool:
        """True when this answer is weaker than the full pipeline would produce.

        Two distinct causes, both reported:

        * a specialist failed or was skipped (``run.degraded``);
        * the answer asserts claims that nobody checked. That second case matters
          because the plan omits the critic deliberately when no verification
          model is configured — and an unchecked answer reported as undegraded
          would read as a verified one.
        """
        if self.run.degraded:
            return True
        return self.outcome.status is AnswerStatus.ANSWERED and self.verification is None

    @property
    def verification_skipped_reason(self) -> str | None:
        for run in self.run.runs:
            if run.role == "critic" and run.status is RunStatus.SKIPPED:
                reason = run.output_summary.get("skipped_reason")
                return str(reason) if reason is not None else None
        if self.outcome.status is AnswerStatus.ANSWERED and self.verification is None:
            # No critic ran at all: the plan says why.
            return self.run.plan.reason
        return None


class _Recorder:
    """Writes trace rows and keeps the ids the domain objects do not carry.

    Scoped to one orchestration. Keeping the ids here rather than on the domain
    dataclasses keeps the domain free of storage concerns, and scoping it to one
    run means two concurrent questions cannot see each other's ids.
    """

    def __init__(self, *, traces: TraceStore, orchestration_id: str, workspace_id: str) -> None:
        self._traces = traces
        self._orchestration_id = orchestration_id
        self._workspace_id = workspace_id
        self._run_ids: dict[int, str] = {}

    def begin(self, run: AgentRun) -> None:
        run_id = self._traces.start_agent_run(
            self._orchestration_id,
            self._workspace_id,
            {**run.as_record(), "status": RunStatus.RUNNING.value},
        )
        self._run_ids[id(run)] = run_id

    def finish(self, run: AgentRun) -> None:
        """Persist the steps in order, then the run's final state."""
        run_id = self._run_ids.get(id(run))
        if run_id is None:
            logger.warning("finishing an agent run that was never started: %s", run.role)
            return
        for index, step in enumerate(run.steps):
            self._traces.append_step(
                run_id,
                self._workspace_id,
                {
                    "step_index": index,
                    "capability": step.capability.value,
                    "status": step.status.value,
                    "detail": step.detail,
                    "latency_ms": step.latency_ms,
                },
            )
        self._traces.finish_agent_run(run_id, run.as_record())


class OrchestrationService:
    """Runs the plan over real services and records the trace."""

    def __init__(
        self,
        *,
        workspaces: Any,
        conversations: ConversationService,
        generation: GenerationService,
        verification: VerificationService,
        traces: TraceStore,
        verifier_available: bool,
    ) -> None:
        self._workspaces = workspaces
        self._conversations = conversations
        self._generation = generation
        self._verification = verification
        self._traces = traces
        self._verifier_available = verifier_available

    # --- planning ---------------------------------------------------------

    def plan(self, *, verify: bool = True) -> OrchestrationPlan:
        """Choose the roles for this question."""
        roles: list[AgentRoleName] = ["orchestrator", "researcher", "analyst"]
        reason = "Retrieve evidence, then answer from it."
        if not verify:
            reason += " Verification was not requested."
        elif self._verifier_available:
            roles.append("critic")
            reason += " Verify the answer because a verification model is configured."
        else:
            reason += (
                " Verification is skipped: no verification model is configured, and"
                " running the critic without one would record a check that did not happen."
            )
        return OrchestrationPlan(roles=tuple(roles), reason=reason)

    # --- execution --------------------------------------------------------

    async def ask(
        self,
        *,
        workspace_id: str,
        user_id: str,
        question: str,
        conversation_id: str | None = None,
        options: GenerationOptions | None = None,
        verify: bool = True,
        method: VerificationMethod = VerificationMethod.LEXICAL_OVERLAP,
    ) -> OrchestrationResult:
        """Run the orchestration for one question."""
        self._require_member(workspace_id, user_id)
        cleaned = question.strip()
        if not cleaned:
            raise ValidationError(message="A question is required.")

        plan = self.plan(verify=verify)
        started = dt.datetime.now(dt.UTC)
        orchestration = OrchestrationRun(
            question=cleaned,
            plan=plan,
            workspace_id=workspace_id,
            conversation_id=conversation_id,
            started_at=started,
        )
        orchestration_id = self._traces.start_orchestration(
            {
                "workspace_id": workspace_id,
                "conversation_id": conversation_id,
                "question": cleaned,
                "plan": plan.as_record(),
                "status": OrchestrationStatus.RUNNING.value,
                "started_at": started,
                "metadata": {"plan_reason": plan.reason},
            }
        )
        recorder = _Recorder(
            traces=self._traces,
            orchestration_id=orchestration_id,
            workspace_id=workspace_id,
        )

        try:
            result = await self._execute_conversation(
                orchestration=orchestration,
                recorder=recorder,
                workspace_id=workspace_id,
                user_id=user_id,
                question=cleaned,
                conversation_id=conversation_id,
                options=options,
                method=method,
            )
        except MnemosError as exc:
            finished = dt.datetime.now(dt.UTC)
            orchestration.status = OrchestrationStatus.FAILED
            orchestration.completed_at = finished
            self._traces.finish_orchestration(
                orchestration_id,
                {
                    "status": OrchestrationStatus.FAILED.value,
                    "completed_at": finished,
                    "total_latency_ms": orchestration.total_latency_ms,
                    "total_tokens": orchestration.total_tokens,
                    "answer_id": None,
                },
            )
            logger.warning("Orchestration failed: %s", exc.message)
            raise

        finished = dt.datetime.now(dt.UTC)
        orchestration.status = OrchestrationStatus.SUCCEEDED
        orchestration.completed_at = finished
        self._traces.finish_orchestration(
            orchestration_id,
            {
                "status": OrchestrationStatus.SUCCEEDED.value,
                "completed_at": finished,
                "total_latency_ms": orchestration.total_latency_ms,
                "total_tokens": orchestration.total_tokens,
                "answer_id": result.outcome.answer_id,
            },
        )
        return result

    async def _execute_conversation(
        self,
        *,
        orchestration: OrchestrationRun,
        recorder: _Recorder,
        workspace_id: str,
        user_id: str,
        question: str,
        conversation_id: str | None,
        options: GenerationOptions | None,
        method: VerificationMethod,
    ) -> OrchestrationResult:
        # The orchestrator opens the trace and states the plan it will follow.
        orchestrator = self._start_run(
            role="orchestrator",
            orchestration=orchestration,
            recorder=recorder,
            input_summary={"plan": list(orchestration.plan.roles)},
        )
        require_capability(spec_for("orchestrator"), AgentCapability.SYNTHESISE)

        asked = await self._run_analyst(
            orchestration=orchestration,
            recorder=recorder,
            workspace_id=workspace_id,
            user_id=user_id,
            question=question,
            conversation_id=conversation_id,
            options=options,
        )
        generation = GenerationOutcome(outcome=asked.answer, execution=asked.execution)

        evidence = self._evidence_from(generation.outcome.passages)
        verification: AnswerVerification | None = None
        if "critic" in orchestration.plan.roles:
            verification = await self._run_critic(
                orchestration=orchestration,
                recorder=recorder,
                workspace_id=workspace_id,
                user_id=user_id,
                generation=generation,
                evidence=evidence,
                method=method,
            )

        # The orchestrator's own step closes the trace with what happened.
        finished = dt.datetime.now(dt.UTC)
        orchestrator.append(
            AgentStep(
                capability=AgentCapability.SYNTHESISE,
                status=RunStatus.SUCCEEDED,
                detail={
                    "roles_run": [run.role for run in orchestration.runs],
                    "degraded": orchestration.degraded,
                },
            )
        )
        orchestrator.output_summary = {
            "degraded": orchestration.degraded,
            "answer_status": generation.outcome.status.value,
        }
        orchestrator.succeed(completed=finished)
        recorder.finish(orchestrator)

        tokens = generation.execution.total_tokens
        orchestration.total_tokens = tokens if isinstance(tokens, int) else None

        return OrchestrationResult(
            outcome=generation.outcome,
            execution=generation.execution,
            run=orchestration,
            verification=verification,
            conversation_id=asked.conversation_id,
        )

    async def _run_analyst(
        self,
        *,
        orchestration: OrchestrationRun,
        recorder: _Recorder,
        workspace_id: str,
        user_id: str,
        question: str,
        conversation_id: str | None,
        options: GenerationOptions | None,
    ) -> AskResult:
        """Researcher + analyst: one grounded question through the conversation layer.

        Retrieval happens inside the generation service. Recording it as the
        researcher step here — rather than retrieving a second time — means the
        evidence in the trace is exactly the evidence the analyst saw. Two
        retrievals would risk recording one set and answering from another.
        """
        researcher = self._start_run(
            role="researcher",
            orchestration=orchestration,
            recorder=recorder,
            input_summary={"question_chars": len(question)},
        )
        require_capability(spec_for("researcher"), AgentCapability.RETRIEVE)
        analyst = self._start_run(
            role="analyst",
            orchestration=orchestration,
            recorder=recorder,
            input_summary={"question_chars": len(question)},
        )
        require_capability(spec_for("analyst"), AgentCapability.GENERATE)

        try:
            asked = await self._conversations.ask(
                workspace_id=workspace_id,
                user_id=user_id,
                question=question,
                conversation_id=conversation_id,
                options=options,
            )
        except MnemosError as exc:
            # Both roles were in flight when generation failed. Record both as
            # failed rather than leaving them "running" for ever.
            finished = dt.datetime.now(dt.UTC)
            for run in (researcher, analyst):
                run.fail(error_code=type(exc).__name__, completed=finished)
                recorder.finish(run)
            raise

        finished = dt.datetime.now(dt.UTC)

        consulted = asked.answer.evidence_considered
        researcher.output_summary = {"passages": consulted}
        researcher.append(
            AgentStep(
                capability=AgentCapability.RETRIEVE,
                status=RunStatus.SUCCEEDED if consulted else RunStatus.SKIPPED,
                detail={"passages": consulted, "cited": asked.answer.evidence_cited},
            )
        )
        if consulted:
            researcher.succeed(completed=finished)
        else:
            researcher.skip(reason="No passage matched the question.", completed=finished)
        recorder.finish(researcher)

        analyst.output_summary = {
            "answer_status": asked.answer.status.value,
            "claims": len(asked.answer.claims),
            "citations": len(asked.answer.citations_by_claim),
        }
        analyst.append(
            AgentStep(
                capability=AgentCapability.GENERATE,
                status=RunStatus.SUCCEEDED,
                detail={
                    "answer_status": asked.answer.status.value,
                    "claims": len(asked.answer.claims),
                },
            )
        )
        analyst.succeed(completed=finished)
        recorder.finish(analyst)
        return asked

    async def _run_critic(
        self,
        *,
        orchestration: OrchestrationRun,
        recorder: _Recorder,
        workspace_id: str,
        user_id: str,
        generation: GenerationOutcome,
        evidence: dict[str, PassageText],
        method: VerificationMethod,
    ) -> AnswerVerification | None:
        """The critic: check the answer, never change it."""
        critic = self._start_run(
            role="critic",
            orchestration=orchestration,
            recorder=recorder,
            input_summary={
                "claims": len(generation.outcome.claims),
                "method": method.value,
            },
        )
        require_capability(spec_for("critic"), AgentCapability.VERIFY)

        if generation.outcome.status is not AnswerStatus.ANSWERED:
            critic.skip(
                reason="Nothing was asserted, so there is nothing to verify.",
                completed=dt.datetime.now(dt.UTC),
            )
            recorder.finish(critic)
            return None

        if not evidence:
            # The answer asserted claims but no cited passage text was available.
            # Reporting "verified" here would be a lie, and reporting success with
            # zero checks would be worse.
            critic.append(
                AgentStep(
                    capability=AgentCapability.VERIFY,
                    status=RunStatus.FAILED,
                    detail={"reason": "no cited passage text could be read"},
                )
            )
            critic.fail(error_code="EvidenceUnavailable", completed=dt.datetime.now(dt.UTC))
            recorder.finish(critic)
            return None

        try:
            verification = await self._verification.verify_answer(
                workspace_id=workspace_id,
                user_id=user_id,
                answer_id=generation.outcome.answer_id,
                evidence=evidence,
                method=method,
            )
        except MnemosError as exc:
            critic.append(
                AgentStep(
                    capability=AgentCapability.VERIFY,
                    status=RunStatus.FAILED,
                    detail={"error": type(exc).__name__},
                )
            )
            critic.fail(error_code=type(exc).__name__, completed=dt.datetime.now(dt.UTC))
            recorder.finish(critic)
            logger.warning(
                "Critic could not verify answer %s: %s", generation.outcome.answer_id, exc
            )
            return None

        critic.append(
            AgentStep(
                capability=AgentCapability.VERIFY,
                status=RunStatus.SUCCEEDED,
                detail={
                    "supported": verification.supported,
                    "unsupported": verification.unsupported,
                    "unverified": verification.unverified,
                    "contradicted": verification.contradicted,
                    "reliability": verification.reliability,
                },
            )
        )
        critic.output_summary = {
            "supported": verification.supported,
            "unsupported": verification.unsupported,
            "unverified": verification.unverified,
            "contradicted": verification.contradicted,
            "reliability": verification.reliability,
        }
        critic.succeed(completed=dt.datetime.now(dt.UTC))
        recorder.finish(critic)
        return verification

    # --- trace plumbing ---------------------------------------------------

    @staticmethod
    def _start_run(
        *,
        role: AgentRoleName,
        orchestration: OrchestrationRun,
        recorder: _Recorder,
        input_summary: dict[str, Any],
    ) -> AgentRun:
        run = AgentRun(
            role=role,
            input_summary=input_summary,
            started_at=dt.datetime.now(dt.UTC),
        )
        recorder.begin(run)
        orchestration.runs.append(run)
        return run

    # --- evidence ---------------------------------------------------------

    @staticmethod
    def _evidence_from(passages: list[RetrievedPassage]) -> dict[str, PassageText]:
        """The passage text the model actually saw, keyed by provenance id.

        Taking this from the retrieval result rather than from the model's own
        quotations is deliberate: a model that quotes badly must not be graded
        against its own bad quotation.
        """
        return {
            passage.provenance_id: PassageText(
                provenance_id=passage.provenance_id,
                chunk_id=passage.chunk_id,
                text=passage.content,
            )
            for passage in passages
        }

    # --- authorization ----------------------------------------------------

    def _require_member(self, workspace_id: str, user_id: str) -> None:
        workspace = self._workspaces.get(workspace_id)
        if workspace is None:
            raise NotFoundError(message="Workspace not found.")
        roles = {
            member.role
            for member in self._workspaces.list_members(workspace_id)
            if member.user_id == user_id
        }
        if not roles & {WorkspaceRole.OWNER, WorkspaceRole.EDITOR, WorkspaceRole.VIEWER}:
            raise ForbiddenError(message="You do not have access to this workspace.")


__all__ = ["OrchestrationFailedError", "OrchestrationResult", "OrchestrationService"]
