"""Live correction lifecycle tests (Phase 3C) against real PostgreSQL.

The correction flow is the one place in the system where stored knowledge is
changed, so its guarantees deserve verification against the real database
rather than a fake:

* the original passage survives with its original text;
* a new revision is created, current, and linked in both directions;
* the corrected text becomes retrievable evidence and the old text stops being
  offered as current;
* separation of duties holds in the database, not only in the service.
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

ALICE = "11111111-1111-4111-8111-111111111111"
BOB = "22222222-2222-4222-8222-222222222222"

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
alter default privileges in schema public grant all on tables to service_role;
alter default privileges in schema public grant all on sequences to service_role;
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


class Database:
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
            [str(self._psql), self._uri], input=script.encode(), capture_output=True, check=False
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


@pytest.fixture(scope="module")
def db() -> Iterator[Database]:
    pgserver = pytest.importorskip("pgserver")
    psql = Path(pgserver.__file__).resolve().parent / "pginstall" / "bin" / "psql"
    data_dir = Path(tempfile.mkdtemp(prefix="mnemos-3c-"))
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


def _seed_passage(db: Database, body: str, *, title: str = "Policy") -> tuple[str, str, str]:
    """Create source → version → chunk → provenance. Returns (source, version, provenance)."""
    workspace = db.scalar(f"select id from public.workspaces where owner_id='{ALICE}'")
    digest = _digest(title)
    source = db.scalar(
        f"insert into public.sources (workspace_id, owner_id, kind, title, original_filename,"
        f" mime_type, size_bytes, content_hash, storage_path, processing_status) values"
        f" ('{workspace}', '{ALICE}', 'document', '{title}', 'p.txt', 'text/plain',"
        f" {len(body)}, '{digest}', '{ALICE}/p.txt', 'ready') returning id"
    )
    version = db.scalar(
        f"insert into public.document_versions (workspace_id, source_id, content_hash,"
        f" size_bytes, mime_type, storage_path, extraction_status) values ('{workspace}',"
        f" '{source}', '{digest}', {len(body)}, 'text/plain', '{ALICE}/p.txt', 'extracted')"
        f" returning id"
    )
    chunk = db.scalar(
        f"insert into public.chunks (workspace_id, source_id, document_version_id, chunk_index,"
        f" content, content_hash, char_count, source_location, chunking_method, chunking_version)"
        f" values ('{workspace}', '{source}', '{version}', 0, '{body}', '{_digest(body)}',"
        f' {len(body)}, \'{{"start_offset":0,"end_offset":{len(body)},"page":1}}\','
        f" 'paragraph-window', 1) returning id"
    )
    provenance = db.scalar(
        f"insert into public.provenance_records (workspace_id, source_id, document_version_id,"
        f" chunk_id, source_location, submitted_at) select c.workspace_id, c.source_id,"
        f" c.document_version_id, c.id, c.source_location, v.submitted_at from public.chunks c"
        f" join public.document_versions v on v.id = c.document_version_id"
        f" where c.id = '{chunk}' returning id"
    )
    return source, version, provenance


def test_correction_preserves_history_and_becomes_current_evidence(db: Database) -> None:
    workspace = db.scalar(f"select id from public.workspaces where owner_id='{ALICE}'")
    # A second contributor is needed as reviewer: separation of duties forbids
    # self-approval. Membership is granted here explicitly and removed by the
    # isolation test, so neither test depends on ordering.
    db.run(
        f"insert into public.workspace_members (workspace_id, user_id, role)"
        f" values ('{workspace}', '{BOB}', 'editor')"
        f" on conflict (workspace_id, user_id) do update set role='editor';"
    )
    original_text = "A passport must be valid for six months."
    _source, _version, provenance = _seed_passage(db, original_text)

    correction = db.run(
        f"insert into public.knowledge_corrections (workspace_id, provenance_id,"
        f" corrected_text, rationale, proposed_by, status, reviewed_by, reviewed_at)"
        f" values ('{workspace}', '{provenance}', 'A passport must be valid for three months.',"
        f" 'Policy changed.', '{ALICE}', 'approved', '{BOB}', now()) returning id",
        user=ALICE,
    ).splitlines()[0]

    revision = db.scalar(f"select public.apply_knowledge_correction('{correction}', '{BOB}')")
    assert len(revision) == 36

    # History intact.
    assert (
        db.scalar(
            f"select c.content from public.provenance_records p join public.chunks c"
            f" on c.id = p.chunk_id where p.id = '{provenance}'"
        )
        == original_text
    )
    assert (
        db.scalar(
            f"select information_status::text || ':' || superseded_by::text"
            f" from public.provenance_records where id = '{provenance}'"
        )
        == f"superseded:{revision}"
    )
    # Revision current and linked back.
    assert (
        db.scalar(
            f"select information_status::text || ':' || revision_of::text"
            f" from public.provenance_records where id = '{revision}'"
        )
        == f"current:{provenance}"
    )

    # The correction is now the retrievable answer to this question.
    found = db.run(
        f"select chunk_id from public.hybrid_search_chunks('{workspace}',"
        f" 'passport valid months', null, 30, 10, false)",
        user=ALICE,
    )
    revision_chunk = db.scalar(
        f"select chunk_id from public.provenance_records where id='{revision}'"
    )
    assert revision_chunk in found.splitlines()

    # And the superseded passage is not offered by default.
    default_rows = db.run(
        f"select provenance_id from public.hybrid_search_chunks('{workspace}',"
        f" 'passport valid months', null, 30, 10, false)",
        user=ALICE,
    )
    assert provenance not in default_rows.splitlines()


def test_self_approval_is_refused_by_the_database(db: Database) -> None:
    workspace = db.scalar(f"select id from public.workspaces where owner_id='{ALICE}'")
    _s, _v, provenance = _seed_passage(db, "Travel insurance covers delays.", title="Insurance")
    correction = db.run(
        f"insert into public.knowledge_corrections (workspace_id, provenance_id,"
        f" corrected_text, proposed_by) values ('{workspace}', '{provenance}',"
        f" 'Travel insurance covers cancellations.', '{ALICE}') returning id",
        user=ALICE,
    ).splitlines()[0]

    with pytest.raises(AssertionError) as excinfo:
        db.run(
            f"update public.knowledge_corrections set status='approved', reviewed_by="
            f"'{ALICE}', reviewed_at=now() where id='{correction}' returning id",
            user=ALICE,
        )
    assert "cannot be approved" in str(excinfo.value)


def test_a_non_member_cannot_read_or_apply_a_correction(db: Database) -> None:
    workspace = db.scalar(f"select id from public.workspaces where owner_id='{ALICE}'")
    # Earlier tests may have added Bob as an editor to exercise review; remove
    # that here so this test asserts true non-membership rather than relying on
    # test ordering.
    db.run(
        f"delete from public.workspace_members where workspace_id='{workspace}' and user_id='{BOB}'"
    )
    _s, _v, provenance = _seed_passage(db, "Visa applications need a photo.", title="Visa")
    correction = db.scalar(
        f"insert into public.knowledge_corrections (workspace_id, provenance_id,"
        f" corrected_text, proposed_by, status, reviewed_by, reviewed_at) values"
        f" ('{workspace}', '{provenance}', 'Visa applications need two photos.',"
        f" '{ALICE}', 'approved', '{ALICE}', now()) returning id"
    )
    assert (
        db.count(
            f"select count(*) from public.knowledge_corrections where id='{correction}'",
            user=BOB,
        )
        == 0
    )
    with pytest.raises(AssertionError):
        db.run(f"select public.apply_knowledge_correction('{correction}', '{BOB}')", user=BOB)


def test_verification_verdict_is_visible_only_within_the_workspace(db: Database) -> None:
    workspace = db.scalar(f"select id from public.workspaces where owner_id='{ALICE}'")
    conversation = db.scalar(
        f"insert into public.conversations (workspace_id, owner_id, title)"
        f" values ('{workspace}', '{ALICE}', 'V') returning id"
    )
    message = db.scalar(
        f"insert into public.messages (conversation_id, workspace_id, role, content,"
        f" sequence_number) values ('{conversation}', '{workspace}', 'user', 'q', 0)"
        f" returning id"
    )
    answer = db.scalar(
        f"insert into public.answers (message_id, workspace_id, conversation_id, status,"
        f" content, evidence_considered, evidence_cited) values ('{message}', '{workspace}',"
        f" '{conversation}', 'answered', 'x', 1, 1) returning id"
    )
    db.run(
        f"delete from public.workspace_members where workspace_id='{workspace}' and user_id='{BOB}'"
    )
    claim = db.scalar(
        f"insert into public.claims (answer_id, workspace_id, claim_index, text)"
        f" values ('{answer}', '{workspace}', 0, 'A claim.') returning id"
    )
    db.run(
        f"insert into public.claim_verifications (claim_id, workspace_id, verdict, method,"
        f" confidence, explanation) values ('{claim}', '{workspace}', 'supported',"
        f" 'lexical_overlap', 0.9, 'Matches.');"
    )
    assert (
        db.count(
            f"select count(*) from public.claim_verifications where claim_id='{claim}'",
            user=ALICE,
        )
        == 1
    )
    assert (
        db.count(
            f"select count(*) from public.claim_verifications where claim_id='{claim}'",
            user=BOB,
        )
        == 0
    )
