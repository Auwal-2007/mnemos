"""Seed the evaluation corpus into real tables (Phase 4A).

Everything is written through the same table chain the product uses:
``sources`` → ``document_versions`` → ``extracted_contents`` → ``chunks`` →
``provenance_records``. Chunks are produced by the real
:func:`app.services.chunking.chunk_text`, so the evaluation measures the
chunker that ships, not a simplified stand-in.

The seeding deliberately bypasses the upload/extraction HTTP path: that path
needs object storage and a request context, neither of which adds anything to a
retrieval measurement. What matters is that the rows the retrieval function
reads are the rows the product would have written.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from app.evaluation.dataset import EvalDataset
from app.services.chunking import ChunkingConfig, chunk_text

#: Fixed identities so a seeded run is reproducible and traces are comparable.
EVAL_USER_ID = "00000000-0000-4000-8000-00000000e1e1"
EVAL_USER_EMAIL = "eval@mnemos.test"
EVAL_WORKSPACE_SLUG = "mnemos-evaluation"


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


@dataclass(slots=True)
class SeededCorpus:
    """Identifiers created by seeding, needed to query and to report."""

    workspace_id: str
    user_id: str
    source_ids: dict[str, str] = field(default_factory=dict)
    chunk_counts: dict[str, int] = field(default_factory=dict)

    @property
    def total_chunks(self) -> int:
        return sum(self.chunk_counts.values())


def ensure_user(db: Any) -> str:
    """Create the evaluation user if absent, and return its id."""
    existing = db.one("select id from auth.users where id = %s::uuid", (EVAL_USER_ID,))
    if existing:
        return str(existing["id"])
    db.execute(
        "insert into auth.users (id, email) values (%s::uuid, %s);",
        (EVAL_USER_ID, EVAL_USER_EMAIL),
    )
    return EVAL_USER_ID


def ensure_workspace(db: Any, user_id: str) -> str:
    """Create the evaluation workspace if absent, with its owner membership.

    The workspace row alone is not enough: every read path goes through a
    membership check, and a workspace without a membership row would make the
    system look broken for a reason that has nothing to do with retrieval.
    """
    existing = db.one("select id from public.workspaces where slug = %s", (EVAL_WORKSPACE_SLUG,))
    if existing:
        return str(existing["id"])

    # The `workspaces_add_owner_membership` trigger writes the owner's
    # membership row, so inserting it here as well would create a duplicate and
    # silently inflate any membership count. Trust the trigger.
    return str(
        db.scalar(
            "insert into public.workspaces (name, slug, owner_id)"
            " values (%s, %s, %s::uuid) returning id;",
            ("MNEMOS Evaluation", EVAL_WORKSPACE_SLUG, user_id),
        )
    )


def seed_document(
    db: Any,
    *,
    workspace_id: str,
    user_id: str,
    title: str,
    body: str,
    information_status: str,
    config: ChunkingConfig | None = None,
) -> tuple[str, int]:
    """Write one document's full chain and return ``(source_id, chunk_count)``.

    Existing sources with the same title are removed first so the seeder is
    idempotent — a re-run must not double the corpus, because doubled passages
    would inflate every recall number for reasons that have nothing to do with
    quality.
    """
    db.execute(
        "delete from public.sources where workspace_id = %s::uuid and title = %s;",
        (workspace_id, title),
    )

    config = config or ChunkingConfig()
    drafts = chunk_text(body, config=config)
    if not drafts:
        return "", 0

    storage_path = f"{user_id}/{_digest(title)[:16]}.txt"
    source_id = str(
        db.scalar(
            "insert into public.sources (workspace_id, owner_id, kind, title,"
            " original_filename, mime_type, size_bytes, content_hash, storage_path,"
            " processing_status) values (%s::uuid, %s::uuid, 'document', %s, %s,"
            " 'text/plain', %s, %s, %s, 'ready') returning id;",
            (
                workspace_id,
                user_id,
                title,
                f"{_digest(title)[:12]}.txt",
                len(body),
                _digest(title),
                storage_path,
            ),
        )
    )
    version_id = str(
        db.scalar(
            "insert into public.document_versions (workspace_id, source_id, version_number,"
            " content_hash, size_bytes, mime_type, storage_path, extraction_status,"
            " submitted_by)"
            " values (%s::uuid, %s::uuid, 1, %s, %s, 'text/plain', %s, 'extracted',"
            " %s::uuid) returning id;",
            (
                workspace_id,
                source_id,
                _digest(body),
                len(body),
                storage_path,
                user_id,
            ),
        )
    )
    db.execute(
        "insert into public.extracted_contents (workspace_id, document_version_id,"
        " content, content_hash, char_count, extraction_method)"
        " values (%s::uuid, %s::uuid, %s, %s, %s, 'plain-text');",
        (workspace_id, version_id, body, _digest(body), len(body)),
    )

    for draft in drafts:
        location = draft.source_location
        db.execute(
            "insert into public.chunks (workspace_id, source_id, document_version_id,"
            " chunk_index, content, content_hash, char_count, source_location,"
            " chunking_method, chunking_version)"
            " values (%s::uuid, %s::uuid, %s::uuid, %s, %s, %s, %s, %s::jsonb, %s, %s);",
            (
                workspace_id,
                source_id,
                version_id,
                draft.chunk_index,
                draft.content,
                draft.content_hash,
                len(draft.content),
                _jsonb(
                    {
                        "start_offset": location.start_offset,
                        "end_offset": location.end_offset,
                        "page": location.page,
                    }
                ),
                config.method,
                config.version,
            ),
        )

    # Provenance is written from the chunks themselves, so an unprovable chunk
    # cannot exist — the same invariant the product maintains.
    db.execute(
        "insert into public.provenance_records (workspace_id, source_id,"
        " document_version_id, chunk_id, source_location, information_status,"
        " submitted_at)"
        " select c.workspace_id, c.source_id, c.document_version_id, c.id,"
        " c.source_location, %s, v.submitted_at"
        " from public.chunks c"
        " join public.document_versions v on v.id = c.document_version_id"
        " where c.source_id = %s::uuid;",
        (information_status, source_id),
    )
    return source_id, len(drafts)


def _jsonb(payload: dict[str, Any]) -> str:
    import json

    return json.dumps(payload)


def seed_dataset(db: Any, dataset: EvalDataset) -> SeededCorpus:
    """Seed every document in ``dataset`` and return the identifiers."""
    user_id = ensure_user(db)
    workspace_id = ensure_workspace(db, user_id)
    seeded = SeededCorpus(workspace_id=workspace_id, user_id=user_id)
    for document in dataset.documents:
        source_id, chunks = seed_document(
            db,
            workspace_id=workspace_id,
            user_id=user_id,
            title=document.title,
            body=document.content,
            information_status=document.information_status,
        )
        if source_id:
            seeded.source_ids[document.title] = source_id
            seeded.chunk_counts[document.title] = chunks
    return seeded


__all__ = [
    "EVAL_USER_EMAIL",
    "EVAL_USER_ID",
    "EVAL_WORKSPACE_SLUG",
    "SeededCorpus",
    "ensure_user",
    "ensure_workspace",
    "seed_dataset",
    "seed_document",
]
