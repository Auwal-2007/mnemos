"""Conversation orchestration (Phase 3B).

Owns the *sequence* of a question, which is where several failure modes live if
it is not explicit:

1. authorize the caller against the workspace;
2. store the user's message **before** calling a model, so a provider failure
   still leaves a faithful transcript;
3. retrieve and generate;
4. store the assistant message and attach the answer to it;
5. on failure, still record the assistant message as an error so the
   conversation cannot look like the question was never asked.

Rule 2 matters for honesty: a transcript that only contains questions that
happened to succeed would misrepresent what the user did. Rule 5 is the same
principle for failures.

Direct specialist chat reuses this exact path with a non-null `agent_role`, so
there is one implementation of "ask a grounded question" rather than two.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

from app.core.errors import ForbiddenError, MnemosError, NotFoundError
from app.domain.conversation import (
    AgentRole,
    AnswerOutcome,
    AnswerStatus,
    Conversation,
    ExecutionRecord,
    Message,
    MessageRole,
)
from app.domain.models import WorkspaceRole
from app.repositories.base import WorkspaceRepository
from app.services.generation import GenerationOptions, GenerationService

logger = logging.getLogger("mnemos.conversations")

#: Title used when the first question is used as the conversation title.
TITLE_MAX_CHARS = 80


class ConversationRepository(Protocol):
    """What the service needs from conversation persistence."""

    def list_for_workspace(
        self, workspace_id: str, *, limit: int = 50, offset: int = 0
    ) -> list[Conversation]: ...

    def get(self, conversation_id: str) -> Conversation | None: ...

    def create(
        self,
        *,
        workspace_id: str,
        owner_id: str,
        title: str,
        agent_role: AgentRole | None = None,
    ) -> Conversation: ...

    def touch(self, conversation_id: str) -> None: ...

    def list_messages(self, conversation_id: str) -> list[Message]: ...

    def next_sequence_number(self, conversation_id: str) -> int: ...

    def append_message(
        self,
        *,
        conversation_id: str,
        workspace_id: str,
        role: MessageRole,
        content: str,
        sequence_number: int,
        execution_id: str | None = None,
    ) -> Message: ...


@dataclass(frozen=True, slots=True)
class AskResult:
    """Everything the API needs to render one question and its answer."""

    conversation_id: str
    question_message: Message
    answer_message: Message
    answer: AnswerOutcome
    execution: ExecutionRecord


class ConversationService:
    """Create conversations, list them, and ask grounded questions."""

    def __init__(
        self,
        *,
        workspaces: WorkspaceRepository,
        conversations: ConversationRepository,
        generation: GenerationService,
    ) -> None:
        self._workspaces = workspaces
        self._conversations = conversations
        self._generation = generation

    # --- conversations ----------------------------------------------------

    def list_conversations(
        self, workspace_id: str, user_id: str, *, limit: int = 50, offset: int = 0
    ) -> list[Conversation]:
        self.require_member(workspace_id, user_id)
        return self._conversations.list_for_workspace(workspace_id, limit=limit, offset=offset)

    def create_conversation(
        self,
        *,
        workspace_id: str,
        user_id: str,
        title: str,
        agent_role: AgentRole | None = None,
    ) -> Conversation:
        self.require_member(workspace_id, user_id)
        cleaned = title.strip() or "New conversation"
        return self._conversations.create(
            workspace_id=workspace_id,
            owner_id=user_id,
            title=cleaned[:TITLE_MAX_CHARS],
            agent_role=agent_role,
        )

    def get_conversation(self, conversation_id: str, user_id: str) -> Conversation:
        conversation = self._conversations.get(conversation_id)
        if conversation is None:
            raise NotFoundError(message="Conversation not found.")
        self.require_member(conversation.workspace_id, user_id)
        return conversation

    def list_messages(self, conversation_id: str, user_id: str) -> list[Message]:
        conversation = self.get_conversation(conversation_id, user_id)
        return self._conversations.list_messages(conversation.id)

    # --- asking -----------------------------------------------------------

    async def ask(
        self,
        *,
        workspace_id: str,
        user_id: str,
        question: str,
        conversation_id: str | None = None,
        agent_role: AgentRole | None = None,
        options: GenerationOptions | None = None,
    ) -> AskResult:
        """Ask a grounded question, creating the conversation if needed.

        The user's message is committed before generation starts, so a failed
        model call cannot erase the fact that the question was asked.
        """
        self.require_member(workspace_id, user_id)
        cleaned = question.strip()
        if not cleaned:
            raise MnemosError(message="A question is required.")

        conversation = self._resolve_conversation(
            workspace_id=workspace_id,
            user_id=user_id,
            conversation_id=conversation_id,
            question=cleaned,
            agent_role=agent_role,
        )

        question_message = self._conversations.append_message(
            conversation_id=conversation.id,
            workspace_id=workspace_id,
            role=MessageRole.USER,
            content=cleaned,
            sequence_number=self._conversations.next_sequence_number(conversation.id),
        )

        try:
            outcome = await self._generation.answer_question(
                workspace_id=workspace_id,
                user_id=user_id,
                question=cleaned,
                conversation_id=conversation.id,
                options=options,
            )
        except MnemosError:
            # Record the failed attempt in the transcript, then re-raise so the
            # API returns the typed error rather than a fake answer.
            self._conversations.append_message(
                conversation_id=conversation.id,
                workspace_id=workspace_id,
                role=MessageRole.ASSISTANT,
                content=(
                    "The answer could not be generated. No answer was produced and "
                    "nothing has been cited."
                ),
                sequence_number=self._conversations.next_sequence_number(conversation.id),
            )
            self._conversations.touch(conversation.id)
            raise

        answer_message = self._conversations.append_message(
            conversation_id=conversation.id,
            workspace_id=workspace_id,
            role=MessageRole.ASSISTANT,
            content=outcome.outcome.content,
            sequence_number=self._conversations.next_sequence_number(conversation.id),
            execution_id=outcome.execution.id or None,
        )
        self._conversations.touch(conversation.id)
        logger.info(
            "Question answered (status=%s claims=%s)",
            outcome.outcome.status.value,
            len(outcome.outcome.claims),
        )
        return AskResult(
            conversation_id=conversation.id,
            question_message=question_message,
            answer_message=answer_message,
            answer=outcome.outcome,
            execution=outcome.execution,
        )

    # --- authorization ----------------------------------------------------

    def require_member(self, workspace_id: str, user_id: str) -> None:
        """Membership check before any read or write.

        RLS also enforces this; the explicit check turns a confusing empty
        result into a truthful 403 and keeps the rule in one named place.
        """
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

    # --- internals --------------------------------------------------------

    def _resolve_conversation(
        self,
        *,
        workspace_id: str,
        user_id: str,
        conversation_id: str | None,
        question: str,
        agent_role: AgentRole | None,
    ) -> Conversation:
        if conversation_id is None:
            title = question[:TITLE_MAX_CHARS]
            return self._conversations.create(
                workspace_id=workspace_id,
                owner_id=user_id,
                title=title,
                agent_role=agent_role,
            )
        conversation = self._conversations.get(conversation_id)
        if conversation is None:
            raise NotFoundError(message="Conversation not found.")
        if conversation.workspace_id != workspace_id:
            # A conversation belongs to exactly one workspace; mixing them would
            # let an answer cite evidence the caller did not ask within.
            raise NotFoundError(message="Conversation not found.")
        return conversation


__all__ = ["AnswerStatus", "AskResult", "ConversationRepository", "ConversationService"]
