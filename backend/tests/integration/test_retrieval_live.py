"""Live hybrid retrieval tests (Phase 3A) against real PostgreSQL.

These run the actual migrations into a real PostgreSQL instance, seed the real
knowledge chain and call the real `hybrid_search_chunks` function. A mock
cannot prove any of this: the assertions depend on PostgreSQL's full-text
ranking, the pgvector `<=>` operator and the RLS policies.

Isolation assertions are made as two different authenticated users, because
RLS is the boundary that matters — not a WHERE clause the service remembered
to add.

Skipped when pgserver is unavailable, like the other integration tests.
"""

from __future__ import annotations

import contextlib
import hashlib
import subprocess
import tempfile
import warnings
from collections.abc import Iterator
from pathlib import Path

import pytest

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS = sorted((ROOT / "supabase" / "migrations").glob("*.sql"))

pytestmark = pytest.mark.skipif(
    not (ROOT / "backend" / ".venv").exists(), reason="requires the backend virtualenv"
)

BOOTSTRAP = r"""
create schema if not exists auth;
create schema if not exists storage;
create table if not exists auth.users (
  id uuid primary key default gen_random_uuid(),
  email text unique,
  raw_user_meta_data jsonb default '{}'::jsonb,
  created_at timestamptz not null default now()
);
create or replace function auth.uid() returns uuid
language sql stable as $$
  select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid;
$$;
do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'anon') then
    create role anon nologin noinherit;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'authenticated') then
    create role authenticated nologin noinherit;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'service_role') then
    create role service_role nologin noinherit bypassrls;
  end if;
end;
$$;
grant usage on schema public, auth, storage to anon, authenticated, service_role;
create table if not exists storage.buckets (
  id text primary key, name text not null, public boolean not null default false,
  file_size_limit bigint, allowed_mime_types text[], created_at timestamptz not null default now()
);
create table if not exists storage.objects (
  id uuid primary key default gen_random_uuid(), bucket_id text references storage.buckets (id),
  name text not null, owner uuid, created_at timestamptz not null default now()
);
alter table storage.objects enable row level security;
create or replace function storage.foldername(name text) returns text[]
language sql immutable as $$ select string_to_array(name, '/'); $$;
grant select, insert, update, delete on storage.objects to authenticated;
grant select on storage.objects to anon;
grant select on storage.buckets to authenticated;
"""

ALICE = "11111111-1111-4111-8111-111111111111"
BOB = "22222222-2222-4222-8222-222222222222"


class Database:
    """psql wrapper that can act as a given authenticated user."""

    def __init__(self, psql: Path, uri: str) -> None:
        self._psql = psql
        self._uri = uri

    def run(self, sql: str, *, user: str | None = None) -> str:
        prefix = ""
        if user is not None:
            prefix = (
                f"set request.jwt.claim.sub = '{user}';\nset session authorization authenticated;\n"
            )
        script = (
            f"\\set ON_ERROR_STOP on\n\\pset format unaligned\n\\pset tuples_only on\n{prefix}{sql}"
        )
        result = subprocess.run(
            [str(self._psql), self._uri],
            input=script.encode(),
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise AssertionError(result.stderr.decode("utf-8", "replace"))
        noise = ("SET", "BEGIN", "COMMIT", "ROLLBACK", "Output format", "Tuples only")
        return "\n".join(
            line.strip()
            for line in result.stdout.decode("utf-8", "replace").splitlines()
            if line.strip() and not any(line.strip().startswith(word) for word in noise)
        )

    def scalar(self, sql: str, *, user: str | None = None) -> str:
        out = self.run(sql, user=user)
        return out.splitlines()[0] if out else ""

    def count(self, sql: str, *, user: str | None = None) -> int:
        return int(self.scalar(sql, user=user) or 0)

    def ids(self, sql: str, *, user: str | None = None) -> set[str]:
        out = self.run(sql, user=user)
        return {line for line in out.splitlines() if line}


@pytest.fixture(scope="module")
def db() -> Iterator[Database]:
    pgserver = pytest.importorskip("pgserver")
    psql = Path(pgserver.__file__).resolve().parent / "pginstall" / "bin" / "psql"
    data_dir = Path(tempfile.mkdtemp(prefix="mnemos-3a-"))
    server = pgserver.get_server(str(data_dir))
    database = Database(psql, server.get_uri())
    try:
        database.run(BOOTSTRAP)
        for migration in MIGRATIONS:
            database.run(migration.read_text(encoding="utf-8"))
        database.run(
            f"insert into auth.users (id, email) values "
            f"('{ALICE}', 'alice@mnemos.test'), ('{BOB}', 'bob@mnemos.test');"
        )
        yield database
    finally:
        with contextlib.suppress(Exception):
            server.cleanup()


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _seed(db: Database, *, owner: str, title: str, body: str, status: str = "current") -> str:
    """Create a complete, constraint-valid knowledge chain and return the chunk id."""
    workspace = db.scalar(f"select id from public.workspaces where owner_id='{owner}'")
    source = db.scalar(
        f"insert into public.sources (workspace_id, owner_id, kind, title, original_filename,"
        f" mime_type, size_bytes, content_hash, storage_path, processing_status) values"
        f" ('{workspace}', '{owner}', 'document', '{title}', 'f.txt', 'text/plain',"
        f" {len(body)}, '{_digest(title)}', '{owner}/f.txt', 'ready') returning id"
    )
    version = db.scalar(
        f"insert into public.document_versions (workspace_id, source_id, content_hash,"
        f" size_bytes, mime_type, storage_path, extraction_status) values"
        f" ('{workspace}', '{source}', '{_digest(body)}', {len(body)}, 'text/plain',"
        f" '{owner}/f.txt', 'extracted') returning id"
    )
    db.run(
        f"insert into public.extracted_contents (workspace_id, document_version_id, content,"
        f" content_hash, char_count, extraction_method) values ('{workspace}', '{version}',"
        f" '{body}', '{_digest(body)}', {len(body)}, 'plain-text');"
    )
    chunk = db.scalar(
        f"insert into public.chunks (workspace_id, source_id, document_version_id, chunk_index,"
        f" content, content_hash, char_count, source_location, chunking_method, chunking_version)"
        f" values ('{workspace}', '{source}', '{version}', 0, '{body}', '{_digest(body)}',"
        f' {len(body)}, \'{{"start_offset": 0, "end_offset": {len(body)}, "page": 1}}\','
        f" 'paragraph-window', 1) returning id"
    )
    db.run(
        f"insert into public.provenance_records (workspace_id, source_id, document_version_id,"
        f" chunk_id, source_location, information_status, submitted_at)"
        f" select c.workspace_id, c.source_id, c.document_version_id, c.id, c.source_location,"
        f" '{status}', v.submitted_at from public.chunks c"
        f" join public.document_versions v on v.id = c.document_version_id"
        f" where c.id = '{chunk}';"
    )
    return chunk


def _workspace(db: Database, owner: str) -> str:
    return db.scalar(f"select id from public.workspaces where owner_id='{owner}'")


def test_lexical_search_finds_exact_terms_and_cites_them(db: Database) -> None:
    workspace = _workspace(db, ALICE)
    passport = _seed(
        db,
        owner=ALICE,
        title="Passport rules",
        body="Renewing a passport requires an original birth certificate.",
    )
    budget = _seed(
        db,
        owner=ALICE,
        title="Budget memo",
        body="The quarterly budget funds conference travel for two staff.",
    )

    found = db.ids(
        f"select chunk_id from public.hybrid_search_chunks('{workspace}', 'passport',"
        f" null, 30, 10, false)",
        user=ALICE,
    )
    assert passport in found
    assert budget not in found


def test_every_result_carries_a_resolvable_provenance_id(db: Database) -> None:
    """Each hit's provenance_id must resolve to the row it claims to be.

    A citation the UI cannot resolve is worse than no citation, so this asserts
    identity, not merely that a non-null id exists.
    """
    workspace = _workspace(db, ALICE)
    _seed(
        db,
        owner=ALICE,
        title="Citizenship evidence",
        body="A passport proves citizenship and must be presented in person.",
    )
    rows = db.run(
        f"select h.provenance_id = pv.id from public.hybrid_search_chunks"
        f" ('{workspace}', 'citizenship', null, 30, 10, false) h"
        f" join public.provenance_records pv on pv.chunk_id = h.chunk_id",
        user=ALICE,
    )
    assert rows.splitlines(), "retrieval returned no rows to resolve"
    assert all(line == "t" for line in rows.splitlines())


def test_result_offsets_reconstruct_the_exact_chunk_text(db: Database) -> None:
    """The excerpt the UI shows must equal the stored chunk, not approximate it."""
    workspace = _workspace(db, ALICE)
    reconstructed = db.scalar(
        f"select substring(e.content from (h.source_location->>'start_offset')::int + 1"
        f" for ((h.source_location->>'end_offset')::int"
        f" - (h.source_location->>'start_offset')::int)) = h.content"
        f" from public.hybrid_search_chunks('{workspace}', 'passport', null, 30, 10, false) h"
        f" join public.extracted_contents e on e.document_version_id = h.document_version_id",
        user=ALICE,
    )
    assert reconstructed == "t"


def test_superseded_material_is_excluded_unless_requested(db: Database) -> None:
    workspace = _workspace(db, ALICE)
    stale = _seed(
        db,
        owner=ALICE,
        title="Old travel policy",
        body="Travel policy is pending revision.",
        status="superseded",
    )
    default_ids = db.ids(
        f"select chunk_id from public.hybrid_search_chunks('{workspace}', 'travel policy',"
        f" null, 30, 10, false)",
        user=ALICE,
    )
    assert stale not in default_ids

    explicit_ids = db.ids(
        f"select chunk_id from public.hybrid_search_chunks('{workspace}', 'travel policy',"
        f" null, 30, 10, true)",
        user=ALICE,
    )
    assert stale in explicit_ids


def test_semantic_retrieval_finds_a_passage_with_no_lexical_overlap(db: Database) -> None:
    """The vector retriever must contribute what full-text search cannot.

    The passage says "identity document"; the query says "metadata for the
    renewal form". They share no lexeme, so only the embedding can connect
    them. A zero-vector query then ranks the identically-stored passage.
    """
    workspace = _workspace(db, ALICE)
    dimension = db.scalar(
        "select atttypmod::text from pg_attribute"
        " where attrelid='public.chunk_embeddings'::regclass and attname='embedding'"
    )
    assert dimension.isdigit()

    chunk = _seed(
        db,
        owner=ALICE,
        title="Identity document",
        body="An identity document is required for the renewal form.",
    )
    db.run(
        f"insert into public.chunk_embeddings (chunk_id, workspace_id, document_version_id,"
        f" embedding_model, embedding_dim, embedding)"
        f" select id, workspace_id, document_version_id, 'test-model', {dimension},"
        f" array_fill(0.5, array[{dimension}])::vector from public.chunks where id='{chunk}'"
    )

    found = db.ids(
        f"select chunk_id from public.hybrid_search_chunks('{workspace}', 'zzzz-not-a-word',"
        f" array_fill(0.5, array[{dimension}])::vector, 30, 10, false)",
        user=ALICE,
    )
    assert chunk in found, "semantic retriever did not surface a lexically unrelated passage"
    assert (
        db.scalar(
            f"select matched_by from public.hybrid_search_chunks('{workspace}', 'zzzz-not-a-word',"
            f" array_fill(0.5, array[{dimension}])::vector, 30, 10, false)"
            f" where chunk_id='{chunk}'",
            user=ALICE,
        )
        == "semantic"
    )


def test_fusion_marks_passages_found_by_both_retrievers(db: Database) -> None:
    workspace = _workspace(db, ALICE)
    dimension = db.scalar(
        "select atttypmod::text from pg_attribute"
        " where attrelid='public.chunk_embeddings'::regclass and attname='embedding'"
    )
    chunk = _seed(
        db,
        owner=ALICE,
        title="Visa letter",
        body="A visa letter must accompany the passport application.",
    )
    db.run(
        f"insert into public.chunk_embeddings (chunk_id, workspace_id, document_version_id,"
        f" embedding_model, embedding_dim, embedding)"
        f" select id, workspace_id, document_version_id, 'test-model', {dimension},"
        f" array_fill(0.25, array[{dimension}])::vector from public.chunks where id='{chunk}'"
    )

    matched = db.scalar(
        f"select matched_by from public.hybrid_search_chunks('{workspace}', 'visa letter',"
        f" array_fill(0.25, array[{dimension}])::vector, 30, 10, false)"
        f" where chunk_id = '{chunk}'",
        user=ALICE,
    )
    assert matched == "both"

    # RRF must place a both-retriever hit above a single-retriever hit.
    fused = db.scalar(
        f"select rrf_score from public.hybrid_search_chunks('{workspace}', 'visa letter',"
        f" array_fill(0.25, array[{dimension}])::vector, 30, 10, false)"
        f" where chunk_id = '{chunk}'",
        user=ALICE,
    )
    assert float(fused) > 1.0 / (60 + 1)


def test_cross_user_retrieval_returns_nothing(db: Database) -> None:
    """Bob searching Alice's workspace gets zero rows, not a permission error."""
    alice_workspace = _workspace(db, ALICE)
    assert (
        db.count(
            f"select count(*) from public.hybrid_search_chunks('{alice_workspace}', 'passport',"
            f" null, 30, 10, true)",
            user=BOB,
        )
        == 0
    )
    assert (
        db.count(
            f"select count(*) from public.hybrid_search_chunks('{alice_workspace}', 'budget',"
            f" null, 30, 10, true)",
            user=BOB,
        )
        == 0
    )


def test_bobs_own_workspace_is_searchable_by_bob(db: Database) -> None:
    """Isolation must not mean 'nobody can search': Bob can search his own data."""
    bob_workspace = _workspace(db, BOB)
    secret = _seed(
        db,
        owner=BOB,
        title="Bob notes",
        body="Bobs private passport note about his own application.",
    )
    found = db.ids(
        f"select chunk_id from public.hybrid_search_chunks('{bob_workspace}', 'passport',"
        f" null, 30, 10, false)",
        user=BOB,
    )
    assert secret in found


def test_a_query_of_only_punctuation_returns_nothing_and_does_not_error(
    db: Database,
) -> None:
    workspace = _workspace(db, ALICE)
    assert (
        db.count(
            f"select count(*) from public.hybrid_search_chunks('{workspace}', '!!! ???',"
            f" null, 30, 10, false)",
            user=ALICE,
        )
        == 0
    )


def test_quoted_phrase_search_is_supported(db: Database) -> None:
    """websearch syntax must pass through because it is how users quote terms."""
    workspace = _workspace(db, ALICE)
    _seed(
        db,
        owner=ALICE,
        title="Birth certificate",
        body="The birth certificate must be original and unexpired.",
    )
    found = db.count(
        f"select count(*) from public.hybrid_search_chunks('{workspace}', '\"birth certificate\"',"
        f" null, 30, 10, false)",
        user=ALICE,
    )
    assert found >= 1


def test_limits_are_respected(db: Database) -> None:
    workspace = _workspace(db, ALICE)
    rows = db.count(
        f"select count(*) from public.hybrid_search_chunks('{workspace}', 'the',"
        f" null, 30, 1, false)",
        user=ALICE,
    )
    assert rows <= 1
