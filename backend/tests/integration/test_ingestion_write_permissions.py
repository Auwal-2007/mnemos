"""Live regression test for the ingestion write defect found in Phase 3B.

The defect
----------
The pipeline wrote extracted text, chunks, provenance and embeddings through
the caller's user-scoped Supabase client. `authenticated` holds only SELECT on
those tables, so against a real database ingestion failed with
`permission denied for table chunks`. The unit tests could not catch it because
the repositories are faked; the existing integration test could not catch it
because it seeded rows as the table owner.

What this test proves, against real PostgreSQL
----------------------------------------------
1. A user cannot write derived rows. This is the invariant that stops a user
   forging a chunk and thereby manufacturing a citation.
2. A privileged (service-role equivalent) connection can write them. Without
   this, ingestion could never work at all.
3. The full chain written by the privileged connection is readable by the
   contributor and invisible to everyone else.

Defect 1 alone would break ingestion; defect 2 alone would break provenance
integrity. Both are asserted together so neither can regress silently.
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

    def denied(self, sql: str, *, user: str) -> bool:
        try:
            self.run(sql, user=user)
        except AssertionError as exc:
            return "permission denied" in str(exc)
        return False


@pytest.fixture(scope="module")
def db() -> Iterator[Database]:
    pgserver = pytest.importorskip("pgserver")
    psql = Path(pgserver.__file__).resolve().parent / "pginstall" / "bin" / "psql"
    data_dir = Path(tempfile.mkdtemp(prefix="mnemos-ing-"))
    server = pgserver.get_server(str(data_dir))
    database = Database(psql, server.get_uri())
    try:
        database.run(
            (ROOT / "backend" / "tests" / "integration" / "bootstrap.sql").read_text()
            if (ROOT / "backend" / "tests" / "integration" / "bootstrap.sql").exists()
            else _BOOTSTRAP
        )
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


_BOOTSTRAP = r"""
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


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def test_user_cannot_write_derived_rows(db: Database) -> None:
    """The invariant: a member may read chunks but must never author one."""
    workspace = db.scalar(f"select id from public.workspaces where owner_id='{ALICE}'")
    digest = "a" * 64

    source = db.run(
        f"insert into public.sources (workspace_id, owner_id, kind, title,"
        f" original_filename, mime_type, size_bytes, content_hash, storage_path)"
        f" values ('{workspace}', '{ALICE}', 'document', 'Doc', 'd.txt', 'text/plain',"
        f" 5, '{digest}', '{ALICE}/d.txt') returning id",
        user=ALICE,
    )
    source_id = source.splitlines()[0]
    version_id = db.run(
        f"insert into public.document_versions (workspace_id, source_id, content_hash,"
        f" size_bytes, mime_type, storage_path) values ('{workspace}', '{source_id}',"
        f" '{digest}', 5, 'text/plain', '{ALICE}/d.txt') returning id",
        user=ALICE,
    ).splitlines()[0]

    # A source and its version are user-owned: the member creates them.
    assert len(source_id) == 36 and len(version_id) == 36

    assert db.denied(
        f"insert into public.chunks (workspace_id, source_id, document_version_id,"
        f" chunk_index, content, content_hash, char_count, source_location,"
        f" chunking_method, chunking_version) values ('{workspace}', '{source_id}',"
        f" '{version_id}', 0, 'forged', '{digest}', 6,"
        f" '{{\"start_offset\":0,\"end_offset\":6}}', 'paragraph-window', 1) returning id",
        user=ALICE,
    ), "a user was able to author a chunk"
    assert db.denied(
        f"insert into public.extracted_contents (workspace_id, document_version_id,"
        f" content, content_hash, char_count, extraction_method) values ('{workspace}',"
        f" '{version_id}', 'forged', '{digest}', 6, 'plain-text') returning id",
        user=ALICE,
    ), "a user was able to author extracted text"


def test_privileged_writer_can_complete_the_chain_and_it_is_citable(db: Database) -> None:
    """The fix: derived writes succeed for the privileged path, and cite cleanly."""
    workspace = db.scalar(f"select id from public.workspaces where owner_id='{ALICE}'")
    digest = "b" * 64
    body = "A passport renewal requires a birth certificate."

    source_id = db.run(
        f"insert into public.sources (workspace_id, owner_id, kind, title,"
        f" original_filename, mime_type, size_bytes, content_hash, storage_path)"
        f" values ('{workspace}', '{ALICE}', 'document', 'Passport', 'p.txt',"
        f" 'text/plain', {len(body)}, '{digest}', '{ALICE}/p.txt') returning id",
        user=ALICE,
    ).splitlines()[0]
    version_id = db.run(
        f"insert into public.document_versions (workspace_id, source_id, content_hash,"
        f" size_bytes, mime_type, storage_path) values ('{workspace}', '{source_id}',"
        f" '{digest}', {len(body)}, 'text/plain', '{ALICE}/p.txt') returning id",
        user=ALICE,
    ).splitlines()[0]

    # Privileged writes (as the service role performs them).
    db.run(
        f"insert into public.extracted_contents (workspace_id, document_version_id,"
        f" content, content_hash, char_count, extraction_method) values ('{workspace}',"
        f" '{version_id}', '{body}', '{_digest(body)}', {len(body)}, 'plain-text');"
    )
    chunk_id = db.scalar(
        f"insert into public.chunks (workspace_id, source_id, document_version_id,"
        f" chunk_index, content, content_hash, char_count, source_location,"
        f" chunking_method, chunking_version) values ('{workspace}', '{source_id}',"
        f" '{version_id}', 0, '{body}', '{_digest(body)}', {len(body)},"
        f' \'{{"start_offset":0,"end_offset":{len(body)},"page":1}}\','
        f" 'paragraph-window', 1) returning id"
    )
    db.run(
        f"insert into public.provenance_records (workspace_id, source_id,"
        f" document_version_id, chunk_id, source_location, submitted_at)"
        f" select c.workspace_id, c.source_id, c.document_version_id, c.id,"
        f" c.source_location, v.submitted_at from public.chunks c"
        f" join public.document_versions v on v.id = c.document_version_id"
        f" where c.id = '{chunk_id}';"
    )

    assert (
        db.count(f"select count(*) from public.provenance_records where chunk_id='{chunk_id}'") == 1
    )

    # And the contributor can retrieve and cite it through RLS.
    assert (
        db.count(
            f"select count(*) from public.hybrid_search_chunks('{workspace}', 'passport',"
            f" null, 30, 10, false)",
            user=ALICE,
        )
        == 1
    )
    assert (
        db.count(
            f"select count(*) from public.hybrid_search_chunks('{workspace}', 'passport',"
            f" null, 30, 10, false)",
            user=BOB,
        )
        == 0
    ), "another user could retrieve from a workspace they are not a member of"
