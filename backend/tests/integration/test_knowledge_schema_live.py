"""End-to-end database tests for the knowledge schema (Phase 2A/2B).

Unlike the unit tests, these run the actual migrations into a real PostgreSQL
instance and exercise the same SQL the repositories issue. They are skipped
when pgserver is not installed, so the normal unit run stays fast.

What this proves that a mock cannot:

* a full ingestion chain (source → version → extraction → page → chunk →
  provenance) is accepted by the real constraints;
* a citation resolves to the exact source, version and page;
* a second version leaves the first version's chunks intact and resolvable;
* deleting a source removes the whole tree and leaves no orphans.

Row-level security is covered exhaustively by `scripts/verify-migrations.py`;
this file covers data shape and cascade behaviour through repository-shaped
SQL.
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

USER = "11111111-1111-4111-8111-111111111111"


class Database:
    """Thin psql wrapper: one process per statement, ON_ERROR_STOP always on."""

    def __init__(self, psql: Path, uri: str) -> None:
        self._psql = psql
        self._uri = uri

    def run(self, sql: str) -> str:
        script = f"\\set ON_ERROR_STOP on\n\\pset format unaligned\n\\pset tuples_only on\n{sql}"
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

    def scalar(self, sql: str) -> str:
        out = self.run(sql)
        return out.splitlines()[0] if out else ""


@pytest.fixture(scope="module")
def db() -> Iterator[Database]:
    pgserver = pytest.importorskip("pgserver")
    psql = Path(pgserver.__file__).resolve().parent / "pginstall" / "bin" / "psql"
    data_dir = Path(tempfile.mkdtemp(prefix="mnemos-it-"))
    server = pgserver.get_server(str(data_dir))
    database = Database(psql, server.get_uri())
    try:
        database.run(BOOTSTRAP)
        for migration in MIGRATIONS:
            database.run(migration.read_text(encoding="utf-8"))
        database.run(f"insert into auth.users (id, email) values ('{USER}', 'a@mnemos.test');")
        yield database
    finally:
        with contextlib.suppress(Exception):
            server.cleanup()


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _create_source(db: Database) -> tuple[str, str]:
    workspace = db.scalar(f"select id from public.workspaces where owner_id='{USER}'")
    source = db.scalar(
        f"insert into public.sources (workspace_id, owner_id, kind, title, original_filename,"
        f" mime_type, size_bytes, content_hash, storage_path) values"
        f" ('{workspace}', '{USER}', 'document', 'Report', 'report.pdf', 'application/pdf',"
        f" 100, '{_digest('Report')}', '{USER}/report.pdf') returning id"
    )
    version = db.scalar(
        f"insert into public.document_versions (workspace_id, source_id, content_hash,"
        f" size_bytes, mime_type, storage_path, extraction_status, extraction_method)"
        f" values ('{workspace}', '{source}', '{_digest('Report')}', 100, 'application/pdf',"
        f" '{USER}/report.pdf', 'extracted', 'pdf') returning id"
    )
    return source, version


def test_full_chain_resolves_to_exact_page(db: Database) -> None:
    source, version = _create_source(db)
    workspace = db.scalar(f"select workspace_id from public.sources where id='{source}'")

    text = "Page one text.\nPage two text."
    page_one_end = len("Page one text.")
    db.run(
        f"insert into public.extracted_contents (workspace_id, document_version_id, content,"
        f" content_hash, char_count, extraction_method, page_count) values"
        f" ('{workspace}', '{version}', '{text}', '{_digest(text)}', {len(text)}, 'pdf', 2);"
    )
    db.run(
        f"insert into public.extracted_pages (workspace_id, document_version_id, page_number,"
        f" start_offset, end_offset) values"
        f" ('{workspace}', '{version}', 1, 0, {page_one_end}),"
        f" ('{workspace}', '{version}', 2, {page_one_end + 1}, {len(text)});"
    )
    chunk_text = "Page two text."
    start = page_one_end + 1
    db.run(
        f"insert into public.chunks (workspace_id, source_id, document_version_id, chunk_index,"
        f" content, content_hash, char_count, source_location, chunking_method, chunking_version)"
        f" values ('{workspace}', '{source}', '{version}', 0, '{chunk_text}',"
        f" '{_digest(chunk_text)}', {len(chunk_text)},"
        f' \'{{"start_offset":{start},"end_offset":{start + len(chunk_text)},"page":2}}\','
        f" 'paragraph-window', 1);"
    )

    resolved = db.scalar(
        f"insert into public.provenance_records (workspace_id, source_id, document_version_id,"
        f" chunk_id, source_location, submitted_at)"
        f" select c.workspace_id, c.source_id, c.document_version_id, c.id, c.source_location,"
        f"        v.submitted_at"
        f"   from public.chunks c"
        f"   join public.document_versions v on v.id = c.document_version_id"
        f"  where c.document_version_id = '{version}'"
        f" returning id"
    )
    assert len(resolved) == 36

    page = db.scalar(
        f"select p.source_location->>'page' from public.provenance_records p"
        f" join public.chunks c on c.id = p.chunk_id where c.document_version_id='{version}'"
    )
    assert page == "2"

    # The reconstructed excerpt must equal the stored chunk text exactly.
    excerpt = db.scalar(
        f"select substring(e.content from (p.source_location->>'start_offset')::int + 1 for "
        f"  ((p.source_location->>'end_offset')::int"
        f"   - (p.source_location->>'start_offset')::int))"
        f"  from public.provenance_records p"
        f"  join public.chunks c on c.id = p.chunk_id"
        f"  join public.extracted_contents e on e.document_version_id = p.document_version_id"
        f" where p.document_version_id='{version}'"
    )
    assert excerpt == chunk_text


def test_second_version_preserves_first_version_chunks(db: Database) -> None:
    source, version_one = _create_source(db)
    workspace = db.scalar(f"select workspace_id from public.sources where id='{source}'")
    db.run(
        f"insert into public.chunks (workspace_id, source_id, document_version_id, chunk_index,"
        f" content, content_hash, char_count, source_location, chunking_method, chunking_version)"
        f" values ('{workspace}', '{source}', '{version_one}', 0, 'old text', '{_digest('old')}',"
        f" 8, '{{\"start_offset\":0,\"end_offset\":8}}', 'paragraph-window', 1);"
    )
    db.run(f"update public.document_versions set is_current = false where id='{version_one}'")
    version_two = db.scalar(
        f"insert into public.document_versions (workspace_id, source_id, content_hash,"
        f" size_bytes, mime_type, storage_path)"
        f" values ('{workspace}', '{source}', '{_digest('new')}', 50, 'application/pdf',"
        f" '{USER}/report-v2.pdf') returning id || '/' || version_number"
    )
    assert version_two.endswith("/2")

    old_chunks = db.scalar(
        f"select count(*) from public.chunks where document_version_id='{version_one}'"
    )
    assert old_chunks == "1"
    current = db.scalar(
        f"select id from public.document_versions where source_id='{source}' and is_current"
    )
    assert current == version_two.split("/")[0]


def test_deleting_source_leaves_no_orphans(db: Database) -> None:
    source, version = _create_source(db)
    workspace = db.scalar(f"select workspace_id from public.sources where id='{source}'")
    db.run(
        f"insert into public.extracted_contents (workspace_id, document_version_id, content,"
        f" content_hash, char_count, extraction_method, page_count)"
        f" values ('{workspace}', '{version}', 'body', '{_digest('body')}', 4, 'pdf', 1);"
    )
    db.run(
        f"insert into public.chunks (workspace_id, source_id, document_version_id, chunk_index,"
        f" content, content_hash, char_count, source_location, chunking_method, chunking_version)"
        f" values ('{workspace}', '{source}', '{version}', 0, 'body', '{_digest('body')}', 4,"
        f" '{{\"start_offset\":0,\"end_offset\":4}}', 'paragraph-window', 1);"
    )
    db.run(
        f"insert into public.provenance_records (workspace_id, source_id, document_version_id,"
        f" chunk_id, source_location, submitted_at)"
        f" select c.workspace_id, c.source_id, c.document_version_id, c.id, c.source_location,"
        f"        v.submitted_at"
        f"   from public.chunks c join public.document_versions v on v.id = c.document_version_id"
        f"  where c.source_id = '{source}';"
    )

    db.run(f"delete from public.sources where id='{source}';")

    counts = db.scalar(
        f"select (select count(*) from public.document_versions where source_id='{source}')::text"
        f" || '/' || (select count(*) from public.extracted_contents"
        f"            where document_version_id='{version}')::text"
        f" || '/' || (select count(*) from public.chunks where source_id='{source}')::text"
        f" || '/' || (select count(*) from public.provenance_records"
        f"            where source_id='{source}')::text"
    )
    assert counts == "0/0/0/0"
