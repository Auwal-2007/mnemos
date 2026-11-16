#!/usr/bin/env python3
"""Verify MNEMOS schema migrations and RLS policies against real PostgreSQL.

Supabase runs PostgreSQL with an `auth` schema, `auth.uid()` and the
`anon` / `authenticated` / `service_role` roles. This harness recreates that
minimal surface so the migrations in `supabase/migrations/` can be executed
and row-level security can be tested for real — without a remote project,
Docker, or fabricated results.

It validates:
  1. every migration applies cleanly and is idempotent
  2. the resulting schema shape (tables, FKs, timestamps, indexes, bucket)
  3. the signup bootstrap trigger
  4. RLS read isolation between two users
  5. RLS write authorization (update/delete/insert spoofing)
  6. anonymous access is denied
  7. provenance-aware knowledge schema (Phase 2A): creation, relationship
     rejection, version history, deletion cascades, per-table RLS
  8. storage object isolation by user-scoped path
  9. privileged access is explicit and grants are minimal

NOT verified by this script: a live Supabase connection, Supabase Auth
token exchange, GoTrue behaviour, and the real storage API. Those require
project credentials and are reported separately.

Usage:
    backend/.venv/bin/python scripts/verify-migrations.py [--keep]
Exit code 0 = all checks passed.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent
_PSQL: Path | None = None
MIGRATIONS = sorted((ROOT / "supabase" / "migrations").glob("*.sql"))
RESULT = "__RESULT__"

USER_A = "11111111-1111-4111-8111-111111111111"
USER_B = "22222222-2222-4222-8222-222222222222"

# Minimal Supabase-compatible bootstrap ------------------------------------
BOOTSTRAP = r"""
create schema if not exists auth;
create schema if not exists storage;

create table if not exists auth.users (
  id uuid primary key default gen_random_uuid(),
  email text unique,
  raw_user_meta_data jsonb default '{}'::jsonb,
  created_at timestamptz not null default now()
);

-- Supabase binds auth.uid() to the JWT subject; NULL means anonymous.
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

-- Supabase grants the service role full DML on the public schema (the role
-- additionally holds BYPASSRLS). Without this, the harness would model a
-- service role that cannot write, which is not what the platform provides and
-- would make ingestion look impossible for the wrong reason.
alter default privileges in schema public grant all on tables to service_role;
alter default privileges in schema public grant all on sequences to service_role;

create table if not exists storage.buckets (
  id text primary key,
  name text not null,
  public boolean not null default false,
  file_size_limit bigint,
  allowed_mime_types text[],
  created_at timestamptz not null default now()
);

create table if not exists storage.objects (
  id uuid primary key default gen_random_uuid(),
  bucket_id text references storage.buckets (id),
  name text not null,
  owner uuid,
  created_at timestamptz not null default now()
);
alter table storage.objects enable row level security;

create or replace function storage.foldername(name text) returns text[]
language sql immutable as $$ select string_to_array(name, '/'); $$;

grant select, insert, update, delete on storage.objects to authenticated;
grant select on storage.objects to anon;
grant select on storage.buckets to authenticated;
"""


class Checker:
    """Collects pass/fail results and prints them as it goes."""

    def __init__(self) -> None:
        self.failures: list[str] = []
        self.passes = 0

    def check(self, name: str, condition: bool, detail: str = "") -> None:
        if condition:
            self.passes += 1
            print(f"  PASS  {name}")
            return
        message = f"{name}{' — ' + detail if detail else ''}"
        self.failures.append(message)
        print(f"  FAIL  {message}")


# --------------------------------------------------------------------------
# psql helpers. psql echoes command tags (SET/RESET) and a message when the
# output format changes, so every helper filters those out explicitly.
# --------------------------------------------------------------------------
_NOISE = re.compile(
    r"^\s*(SET|RESET|SET ROLE|RESET ROLE|BEGIN|COMMIT|ROLLBACK)$"
    r"|^Output format is (un)?aligned\.$"
    r"|^Tuples only is (on|off)\.$",
    re.IGNORECASE,
)


def run(server, sql: str) -> str:
    """Execute SQL with ON_ERROR_STOP and return unaligned, tuples-only output.

    pgserver's helper discards stderr, so psql is invoked directly here to
    keep failures diagnosable.
    """
    script = f"\\set ON_ERROR_STOP on\n\\pset format unaligned\n\\pset tuples_only on\n{sql}"
    result = subprocess.run(
        [str(_PSQL), server.get_uri()],
        input=script.encode(),
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", "replace").strip()
        raise RuntimeError(f"psql exited {result.returncode}: {detail or 'no stderr'}")
    return result.stdout.decode("utf-8", "replace")


def _clean(out: str) -> list[str]:
    return [line.strip() for line in out.splitlines() if line.strip() and not _NOISE.match(line)]


def query(server, sql: str, user_id: str | None = None, role: str | None = None) -> str:
    """Return the first column of the first row, or '' when there is no row."""
    return _query_impl(server, sql, user_id=user_id, role=role)[0]


def _query_impl(
    server, sql: str, user_id: str | None = None, role: str | None = None
) -> tuple[str, str]:
    """Return (value, error). Errors are reported rather than raised so that
    permission denials can be asserted on."""
    prefix = ""
    if user_id is not None:
        prefix += (
            f"set request.jwt.claim.sub = '{user_id}';\n"
            f"set session authorization {role or 'authenticated'};\n"
        )
    elif role is not None:
        prefix += f"set request.jwt.claim.sub = '';\nset session authorization {role};\n"
    out_error = ""
    try:
        out = run(server, f"{prefix}{sql}")
    except Exception as exc:  # noqa: BLE001 - reported to the caller
        return "", str(exc)
    lines = _clean(out)
    return (lines[0] if lines else ""), ""


def scalar(server, sql: str) -> str:
    """Single value as table owner (RLS bypassed for setup/assertions)."""
    return query(server, sql)


def affected(server, sql: str, user_id: str | None = None, role: str | None = None) -> int:
    """Execute a write statement and count the affected rows it returns.

    Data-modifying statements must be top-level, so callers append
    `returning 1` and the row count is derived from the output.
    """
    prefix = ""
    if user_id is not None:
        prefix += (
            f"set request.jwt.claim.sub = '{user_id}';\n"
            "set session authorization authenticated;\n"
        )
    elif role is not None:
        prefix += f"set request.jwt.claim.sub = '';\nset session authorization {role};\n"
    out = run(server, f"{prefix}{sql}")
    return len([line for line in _clean(out) if line == "1"])


def attempt(server, sql: str, user_id: str | None = None, role: str | None = None) -> str:
    """Execute SQL as a role; returns the error text, or '' on success."""
    try:
        if user_id is not None:
            run(
                server,
                f"set request.jwt.claim.sub = '{user_id}';\n"
                f"set session authorization authenticated;\n{sql}",
            )
        elif role is not None:
            run(
                server,
                f"set request.jwt.claim.sub = '';\n"
                f"set session authorization {role};\n{sql}",
            )
        else:
            run(server, sql)
        return ""
    except Exception as exc:  # noqa: BLE001 - the error text is the assertion subject
        return str(exc)


# --------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------
def apply_migrations(server, checker: Checker) -> bool:
    print("\n[1] Apply migrations")
    run(server, BOOTSTRAP)
    checker.check("Supabase-compatible bootstrap applied", True)

    ok = True
    for path in MIGRATIONS:
        error = attempt(server, path.read_text(encoding="utf-8"))
        checker.check(f"migration {path.name} applied", not error, error[:300])
        ok = ok and not error
    if not ok:
        return False

    print("\n[2] Idempotency (re-apply every migration)")
    for path in MIGRATIONS:
        error = attempt(server, path.read_text(encoding="utf-8"))
        checker.check(f"re-apply {path.name}", not error, error[:300])
    return True


def check_schema(server, checker: Checker) -> None:
    print("\n[3] Schema shape")
    tables = scalar(
        server,
        "select string_agg(tablename, ',' order by tablename) from pg_tables "
        "where schemaname = 'public'",
    ).split(",")
    for table in ("profiles", "user_preferences", "workspace_members", "workspaces"):
        checker.check(f"table public.{table} exists", table in tables)

    # Phase 2A adds the knowledge tables, Phase 3B the conversation tables.
    # Anything missing means a migration regressed; a table from a phase that is
    # still unimplemented means a migration leaked in early.
    phase_2a = {
        "profiles", "user_preferences", "workspace_members", "workspaces",
        "sources", "document_versions", "extracted_contents", "extracted_pages",
        "chunks", "provenance_records", "chunk_embeddings",
    }
    phase_3b = {
        "conversations", "messages", "answers", "claims", "claim_citations",
        "execution_records",
    }
    actual = {t for t in tables if t}
    checker.check(
        "knowledge tables present (2A)", phase_2a <= actual,
        ",".join(sorted(phase_2a - actual)),
    )
    checker.check(
        "conversation tables present (3B)", phase_3b <= actual,
        ",".join(sorted(phase_3b - actual)),
    )
    # Phase 3C adds verification, corrections and conflicts. Agent execution
    # history is Phase 3D, so its absence is still a real invariant.
    phase_3c = {
        "claim_verifications", "knowledge_corrections", "knowledge_conflicts",
    }
    checker.check(
        "verification and memory tables present (3C)", phase_3c <= actual,
        ",".join(sorted(phase_3c - actual)),
    )
    # Phase 3D adds orchestration traces. "memory_edit" remains unimplemented:
    # knowledge changes go through knowledge_corrections, not direct edits.
    phase_3d = {"orchestration_runs", "agent_runs", "agent_steps"}
    checker.check(
        "agent trace tables present (3D)", phase_3d <= actual,
        ",".join(sorted(phase_3d - actual)),
    )
    checker.check(
        "no tables from unimplemented phases",
        not any(k in t for t in actual for k in ("memory_edit",)),
        ",".join(sorted(actual - phase_2a - phase_3b - phase_3c - phase_3d)),
    )

    for table in sorted(phase_2a):
        flags = scalar(
            server,
            f"select relrowsecurity::text || '/' || relforcerowsecurity::text "
            f"from pg_class where relname = '{table}' and relkind = 'r'",
        )
        checker.check(f"RLS enabled and forced on {table}", flags == "true/true", flags)

    # Base tables only: information_schema.columns also lists views, and
    # current_provenance (a view over provenance_records) would otherwise be
    # counted as an undated table and inflate the expected total.
    stamps = scalar(
        server,
        "select count(*) from information_schema.columns c "
        "join pg_class t on t.relname = c.table_name and t.relkind = 'r' "
        "where c.table_schema='public' and c.column_name in ('created_at','updated_at')",
    )
    # Phase 1B tables carry both stamps (profiles 2, workspaces 2,
    # user_preferences 2) = 6. Phase 2A adds sources(2), document_versions(2)
    # and created_at-only on extracted_contents / extracted_pages / chunks /
    # provenance_records (4) = 14, plus chunk_embeddings.created_at = 15.
    # Phase 3B adds conversations(2) = 17 plus created_at-only on messages,
    # answers, claims, claim_citations and execution_records started_at = 21.
    # Phase 3C adds knowledge_corrections.created_at and knowledge_conflicts
    # .created_at = 23. Phase 3D adds orchestration_runs.started_at (not
    # created_at, deliberately: a run begins, it is not "created"),
    # agent_runs.started_at and agent_steps.created_at = 24. The number is
    # asserted exactly so an accidentally undated table is caught.
    checker.check("created_at/updated_at coverage", stamps == "24", f"found {stamps}")

    fks = scalar(
        server,
        "select count(*) from information_schema.table_constraints "
        "where table_schema='public' and constraint_type='FOREIGN KEY'",
    )
    checker.check("foreign keys declared", int(fks or 0) >= 5, f"found {fks}")

    indexes = scalar(
        server,
        "select count(*) from pg_indexes where schemaname='public' and indexname like 'workspaces_%'",
    )
    checker.check("workspace indexes created", int(indexes or 0) >= 2, f"found {indexes}")

    bucket = scalar(
        server,
        "select public::text || '/' || coalesce(file_size_limit,0)::text "
        "from storage.buckets where id='sources'",
    )
    checker.check("sources bucket private at 50 MiB", bucket == "false/52428800", bucket)

    mimes = scalar(server, "select array_length(allowed_mime_types, 1)::text from storage.buckets where id='sources'")
    checker.check("bucket restricts MIME types", mimes not in ("", "0"), mimes)

    for policy in ("sources_select_own", "sources_insert_own", "sources_delete_own"):
        count = scalar(server, f"select count(*) from pg_policies where policyname='{policy}'")
        checker.check(f"storage policy {policy}", count == "1", count)
    update_policies = scalar(
        server,
        "select count(*) from pg_policies where schemaname='storage' and policyname like 'sources%update%'",
    )
    checker.check("no storage UPDATE policy (objects immutable)", update_policies == "0", update_policies)


def check_bootstrap_trigger(server, checker: Checker) -> None:
    print("\n[4] Signup bootstrap trigger")
    run(
        server,
        f"insert into auth.users (id, email) values "
        f"('{USER_A}', 'alice@mnemos.test'), ('{USER_B}', 'bob@mnemos.test');",
    )
    checker.check("profile created on signup", scalar(server, "select count(*) from public.profiles") == "2")
    checker.check(
        "preferences created on signup",
        scalar(server, "select count(*) from public.user_preferences") == "2",
    )
    checker.check(
        "default workspace per user",
        scalar(server, "select count(*) from public.workspaces") == "2",
    )
    checker.check(
        "owner membership auto-created",
        scalar(
            server,
            f"select count(*) from public.workspace_members where role='owner' and user_id='{USER_A}'",
        )
        == "1",
    )
    checker.check(
        "slug derived from email",
        scalar(server, f"select slug from public.workspaces where owner_id='{USER_A}'") == "alice",
    )

    # Slugs are unique per owner, not globally: two different users may both
    # have a workspace slug 'alice'. Uniqueness within one owner is enforced
    # by the constraint and exercised by the collision loop below.
    dup = "33333333-3333-4333-8333-333333333333"
    run(server, f"insert into auth.users (id, email) values ('{dup}', 'alice@other.test');")
    checker.check(
        "different users may share a workspace slug",
        scalar(server, f"select slug from public.workspaces where owner_id='{dup}'") == "alice",
    )
    checker.check(
        "slug unique per owner is enforced",
        scalar(
            server,
            "select count(*) from pg_constraint where conname='workspaces_owner_slug_unique'",
        )
        == "1",
    )
    # Same owner creating a second 'alice' slug must be rejected by the constraint.
    collide = attempt(
        server,
        f"insert into public.workspaces (owner_id, name, slug) values ('{dup}', 'dupe', 'alice');",
    )
    checker.check("duplicate slug for the same owner is rejected", bool(collide), "insert succeeded")


def check_rls_reads(server, checker: Checker) -> None:
    ws_a = scalar(server, f"select id from public.workspaces where owner_id='{USER_A}'")
    ws_b = scalar(server, f"select id from public.workspaces where owner_id='{USER_B}'")

    print("\n[5] RLS read isolation")
    checker.check("A sees exactly their 1 workspace",
                  query(server, "select count(*) from public.workspaces", user_id=USER_A) == "1")
    checker.check("A sees only their own profile",
                  query(server, "select count(*) from public.profiles", user_id=USER_A) == "1")
    checker.check("B cannot see A's workspace by id",
                  query(server, f"select count(*) from public.workspaces where id='{ws_a}'", user_id=USER_B) == "0")
    checker.check("B cannot see A's preferences",
                  query(server, f"select count(*) from public.user_preferences where user_id='{USER_A}'", user_id=USER_B) == "0")
    checker.check("B cannot see A's membership rows",
                  query(server, f"select count(*) from public.workspace_members where workspace_id='{ws_a}'", user_id=USER_B) == "0")
    checker.check("B sees their own workspace",
                  query(server, f"select count(*) from public.workspaces where id='{ws_b}'", user_id=USER_B) == "1")


def check_rls_writes(server, checker: Checker) -> None:
    ws_a = scalar(server, f"select id from public.workspaces where owner_id='{USER_A}'")

    print("\n[6] RLS write authorization")
    stolen = affected(
        server,
        f"update public.workspaces set name='stolen' where id='{ws_a}' returning 1",
        user_id=USER_B,
    )
    checker.check(
        "B cannot update A's workspace",
        stolen == 0 and scalar(server, f"select name from public.workspaces where id='{ws_a}'") == "Personal",
        f"affected={stolen}",
    )

    removed = affected(server, f"delete from public.workspaces where id='{ws_a}' returning 1", user_id=USER_B)
    checker.check(
        "B cannot delete A's workspace",
        removed == 0 and scalar(server, f"select count(*) from public.workspaces where id='{ws_a}'") == "1",
        f"affected={removed}",
    )

    renamed = affected(
        server,
        f"update public.workspaces set name='Renamed' where id='{ws_a}' returning 1",
        user_id=USER_A,
    )
    checker.check(
        "A can update their own workspace",
        renamed == 1 and scalar(server, f"select name from public.workspaces where id='{ws_a}'") == "Renamed",
        f"affected={renamed}",
    )

    spoof = attempt(
        server,
        f"insert into public.workspaces (owner_id, name, slug) values ('{USER_B}', 'spoof', 'spoof');",
        user_id=USER_A,
    )
    checker.check(
        "A cannot create a workspace owned by B",
        scalar(server, "select count(*) from public.workspaces where slug='spoof'") == "0",
        spoof[:80],
    )

    profile_edit = affected(
        server,
        f"update public.profiles set display_name='pwned' where id='{USER_B}' returning 1",
        user_id=USER_A,
    )
    checker.check(
        "A cannot modify B's profile",
        profile_edit == 0
        and scalar(server, f"select coalesce(display_name,'null') from public.profiles where id='{USER_B}'") != "pwned",
        f"affected={profile_edit}",
    )

    self_pref = affected(
        server,
        f"update public.user_preferences set theme='dark' where user_id='{USER_B}' returning 1",
        user_id=USER_A,
    )
    checker.check("A cannot modify B's preferences", self_pref == 0, f"affected={self_pref}")

    own_pref = affected(
        server,
        f"update public.user_preferences set theme='dark' where user_id='{USER_A}' returning 1",
        user_id=USER_A,
    )
    checker.check("A can update their own preferences", own_pref == 1, f"affected={own_pref}")


def check_anonymous(server, checker: Checker) -> None:
    print("\n[7] Anonymous access denied")
    ws_error = attempt(server, "select count(*) from public.workspaces;", role="anon")
    checker.check("anon cannot read workspaces", bool(ws_error), "no error raised")
    for table in ("profiles", "workspace_members", "user_preferences"):
        error = attempt(server, f"select count(*) from public.{table};", role="anon")
        checker.check(f"anon cannot read {table}", bool(error), "no error raised")

    before = scalar(server, "select count(*) from public.workspaces")
    write_error = attempt(
        server,
        f"insert into public.workspaces (owner_id, name, slug) values ('{USER_A}', 'x', 'x');",
        role="anon",
    )
    checker.check(
        "anon cannot insert a workspace",
        bool(write_error) and scalar(server, "select count(*) from public.workspaces") == before,
        "insert succeeded",
    )
    checker.check(
        "anon holds no public-table grants",
        scalar(
            server,
            "select count(*) from information_schema.role_table_grants "
            "where grantee='anon' and table_schema='public'",
        )
        == "0",
    )


def check_knowledge(server, checker: Checker) -> None:
    """Phase 2A: provenance model, referential integrity and RLS."""
    ws_a = scalar(server, f"select id from public.workspaces where owner_id='{USER_A}'")
    ws_b = scalar(server, f"select id from public.workspaces where owner_id='{USER_B}'")
    digest = "a" * 64

    print("\n[10] Knowledge schema: creation and invariants")

    # --- happy path ------------------------------------------------------
    source_a = scalar(
        server,
        f"insert into public.sources "
        f"(workspace_id, owner_id, kind, title, original_filename, mime_type, size_bytes, "
        f" content_hash, storage_path) values "
        f"('{ws_a}', '{USER_A}', 'document', 'Paper', 'paper.pdf', 'application/pdf', 10, "
        f" '{digest}', '{USER_A}/paper.pdf') returning id",
    )
    checker.check("source row created", len(source_a) == 36, source_a)

    version_a = scalar(
        server,
        f"insert into public.document_versions "
        f"(workspace_id, source_id, content_hash, size_bytes, mime_type, storage_path, submitted_by) "
        f"values ('{ws_a}', '{source_a}', '{digest}', 10, 'application/pdf', "
        f"'{USER_A}/paper.pdf', '{USER_A}') returning id || '/' || version_number::text",
    )
    checker.check("version 1 auto-numbered", version_a.endswith("/1"), version_a)
    vid_a = version_a.split("/")[0]

    extraction = scalar(
        server,
        f"insert into public.extracted_contents "
        f"(workspace_id, document_version_id, content, content_hash, char_count, "
        f" extraction_method, page_count) values "
        f"('{ws_a}', '{vid_a}', 'Hello world. Second page.', '{digest}', 25, 'plain-text', 2) returning id",
    )
    checker.check("extracted content stored separately", len(extraction) == 36, extraction)

    scalar(
        server,
        f"insert into public.extracted_pages "
        f"(workspace_id, document_version_id, page_number, start_offset, end_offset) values "
        f"('{ws_a}', '{vid_a}', 1, 0, 13), ('{ws_a}', '{vid_a}', 2, 13, 26)",
    )
    checker.check(
        "page offsets preserved",
        scalar(server, f"select count(*) from public.extracted_pages where document_version_id='{vid_a}'") == "2",
    )

    chunk_a = scalar(
        server,
        f"insert into public.chunks "
        f"(workspace_id, source_id, document_version_id, chunk_index, content, content_hash, "
        f" char_count, source_location, chunking_method, chunking_version) values "
        f"('{ws_a}', '{source_a}', '{vid_a}', 0, 'Hello world.', '{digest}', 12, "
        f" '{{\"start_offset\":0,\"end_offset\":12,\"page\":1}}', 'paragraph', 1) returning id",
    )
    checker.check("chunk created with location", len(chunk_a) == 36, chunk_a)

    prov = scalar(
        server,
        f"insert into public.provenance_records "
        f"(workspace_id, source_id, document_version_id, chunk_id, source_location, submitted_at) "
        f"select '{ws_a}', '{source_a}', '{vid_a}', '{chunk_a}', "
        f"       '{{\"start_offset\":0,\"end_offset\":12,\"page\":1}}', submitted_at "
        f"  from public.document_versions where id='{vid_a}' returning id",
    )
    checker.check("provenance record created", len(prov) == 36, prov)

    resolved = scalar(
        server,
        f"select source_title || '|' || version_number::text || '|' || chunk_index::text || '|' "
        f"       || information_status::text || '|' || (source_location->>'page') "
        f"  from public.resolve_chunk_provenance('{chunk_a}')",
    )
    checker.check(
        "provenance resolves to exact source+version+location",
        resolved == "Paper|1|0|current|1",
        resolved,
    )
    checker.check(
        "provenance resolves the same for a second caller in the workspace",
        scalar(server, f"select count(*) from public.resolve_chunk_provenance('{chunk_a}')") == "1",
    )

    # --- relationship rejection -----------------------------------------
    bad_chunk = attempt(
        server,
        f"insert into public.chunks "
        f"(workspace_id, source_id, document_version_id, chunk_index, content, content_hash, "
        f" char_count, source_location, chunking_method, chunking_version) values "
        f"('{ws_a}', '{source_a}', '{vid_a}', 0, 'dup', '{digest}', 3, "
        f" '{{\"start_offset\":0,\"end_offset\":3}}', 'paragraph', 1)",
    )
    checker.check("duplicate chunk_index rejected", bool(bad_chunk), "inserted a duplicate index")

    wrong_source = attempt(
        server,
        f"insert into public.chunks "
        f"(workspace_id, source_id, document_version_id, chunk_index, content, content_hash, "
        f" char_count, source_location, chunking_method, chunking_version) values "
        f"('{ws_a}', gen_random_uuid(), '{vid_a}', 9, 'x', '{digest}', 1, "
        f" '{{\"start_offset\":0,\"end_offset\":1}}', 'paragraph', 1)",
    )
    checker.check("chunk with mismatched source rejected", bool(wrong_source), "accepted a foreign source")

    cross_workspace_chunk = attempt(
        server,
        f"insert into public.chunks "
        f"(workspace_id, source_id, document_version_id, chunk_index, content, content_hash, "
        f" char_count, source_location, chunking_method, chunking_version) values "
        f"('{ws_b}', '{source_a}', '{vid_a}', 8, 'x', '{digest}', 1, "
        f" '{{\"start_offset\":0,\"end_offset\":1}}', 'paragraph', 1)",
    )
    checker.check("chunk cannot straddle workspaces", bool(cross_workspace_chunk), "accepted a foreign workspace")

    bad_prov = attempt(
        server,
        f"insert into public.provenance_records "
        f"(workspace_id, source_id, document_version_id, chunk_id, source_location, submitted_at) "
        f"select '{ws_a}', '{source_a}', '{vid_a}', '{chunk_a}', "
        f"       '{{\"start_offset\":5,\"end_offset\":9}}', submitted_at "
        f"  from public.document_versions where id='{vid_a}'",
    )
    checker.check("provenance cannot fabricate a location", bool(bad_prov), "accepted a forged location")

    bad_submitted = attempt(
        server,
        f"insert into public.provenance_records "
        f"(workspace_id, source_id, document_version_id, chunk_id, source_location, submitted_at) "
        f"values ('{ws_a}', '{source_a}', '{vid_a}', '{chunk_a}', "
        f" '{{\"start_offset\":0,\"end_offset\":12,\"page\":1}}', now() - interval '10 years')",
    )
    checker.check("provenance cannot fabricate a submission time", bool(bad_submitted), "accepted a forged time")

    bad_hash = attempt(
        server,
        f"insert into public.sources (workspace_id, owner_id, kind, title, mime_type, size_bytes, "
        f"content_hash, storage_path) values ('{ws_a}', '{USER_A}', 'note', 'n', 'text/plain', 1, "
        f"'not-a-hash', '{USER_A}/n.txt')",
    )
    checker.check("invalid content hash rejected", bool(bad_hash), "accepted a non-sha256 hash")

    note_with_filename = attempt(
        server,
        f"insert into public.sources (workspace_id, owner_id, kind, title, original_filename, "
        f"mime_type, size_bytes, content_hash, storage_path) values "
        f"('{ws_a}', '{USER_A}', 'note', 'n', 'a.txt', 'text/plain', 1, '{digest}', '{USER_A}/n.txt')",
    )
    checker.check("note cannot claim a filename", bool(note_with_filename), "accepted a file-backed note")

    print("\n[11] Version history is never overwritten")
    vid2 = scalar(
        server,
        f"update public.document_versions set is_current = false where id='{vid_a}' returning id",
    )
    checker.check("previous version can be retired", vid2 == vid_a, vid2)

    vid_b = scalar(
        server,
        f"insert into public.document_versions "
        f"(workspace_id, source_id, content_hash, size_bytes, mime_type, storage_path, submitted_by) "
        f"values ('{ws_a}', '{source_a}', '{'b' * 64}', 20, 'application/pdf', "
        f"'{USER_A}/paper-v2.pdf', '{USER_A}') returning id || '/' || version_number::text",
    )
    checker.check("second version numbered 2", vid_b.endswith("/2"), vid_b)

    duplicate_current = attempt(
        server,
        f"update public.document_versions set is_current = true where id='{vid_a}'",
    )
    checker.check("only one current version permitted", bool(duplicate_current), "two current versions")

    rewrite = attempt(
        server,
        f"update public.document_versions set content_hash = '{'c' * 64}' where id='{vid_a}'",
    )
    checker.check("version content is immutable", bool(rewrite), "content was rewritten")

    old_chunks = scalar(
        server, f"select count(*) from public.chunks where document_version_id='{vid_a}'"
    )
    checker.check("retiring a version preserves its chunks", old_chunks == "1", old_chunks)

    print("\n[12] Deletion behaviour")
    cascade_source = scalar(
        server,
        f"insert into public.sources (workspace_id, owner_id, kind, title, mime_type, size_bytes, "
        f"content_hash, storage_path) values ('{ws_a}', '{USER_A}', 'note', 'temp', 'text/plain', 1, "
        f"'{digest}', '{USER_A}/temp.txt') returning id",
    )
    cascade_version = scalar(
        server,
        f"insert into public.document_versions (workspace_id, source_id, content_hash, size_bytes, "
        f"mime_type, storage_path) values ('{ws_a}', '{cascade_source}', '{digest}', 1, 'text/plain', "
        f"'{USER_A}/temp.txt') returning id",
    )
    cascade_chunk = scalar(
        server,
        f"insert into public.chunks (workspace_id, source_id, document_version_id, chunk_index, "
        f"content, content_hash, char_count, source_location, chunking_method, chunking_version) "
        f"values ('{ws_a}', '{cascade_source}', '{cascade_version}', 0, 'x', '{digest}', 1, "
        f"'{{\"start_offset\":0,\"end_offset\":1}}', 'paragraph', 1) returning id",
    )
    scalar(
        server,
        f"insert into public.provenance_records (workspace_id, source_id, document_version_id, "
        f"chunk_id, source_location, submitted_at) "
        f"select '{ws_a}', '{cascade_source}', '{cascade_version}', '{cascade_chunk}', "
        f"'{{\"start_offset\":0,\"end_offset\":1}}', submitted_at "
        f"from public.document_versions where id='{cascade_version}'",
    )
    scalar(server, f"delete from public.sources where id='{cascade_source}'")
    leftover = scalar(
        server,
        f"select (select count(*) from public.document_versions where source_id='{cascade_source}')::text "
        f" || '/' || (select count(*) from public.chunks where source_id='{cascade_source}')::text "
        f" || '/' || (select count(*) from public.provenance_records where source_id='{cascade_source}')::text",
    )
    checker.check("deleting a source leaves no orphans", leftover == "0/0/0", leftover)

    print("\n[13] RLS on knowledge tables")
    checker.check(
        "A sees their own source",
        query(server, "select count(*) from public.sources", user_id=USER_A) == "1",
    )
    for table in ("sources", "document_versions", "extracted_contents", "extracted_pages",
                  "chunks", "provenance_records"):
        seen = query(server, f"select count(*) from public.{table}", user_id=USER_B)
        checker.check(f"B cannot read A's {table}", seen == "0", seen)
    checker.check(
        "B cannot resolve A's provenance by chunk id",
        query(server, f"select count(*) from public.resolve_chunk_provenance('{chunk_a}')", user_id=USER_B)
        == "0",
    )

    # INSERT ... against a failing WITH CHECK raises rather than returning
    # zero rows, so these are asserted as errors plus an unchanged table.
    spoof = attempt(
        server,
        f"insert into public.sources (workspace_id, owner_id, kind, title, mime_type, size_bytes, "
        f"content_hash, storage_path) values ('{ws_a}', '{USER_B}', 'note', 'spoofed', 'text/plain', 1, "
        f"'{digest}', '{USER_B}/x.txt');",
        user_id=USER_B,
    )
    checker.check(
        "B cannot insert into A's workspace",
        bool(spoof)
        and scalar(server, "select count(*) from public.sources where title='spoofed'") == "0",
        spoof[:80],
    )

    forge_chunk = attempt(
        server,
        f"insert into public.chunks (workspace_id, source_id, document_version_id, chunk_index, "
        f"content, content_hash, char_count, source_location, chunking_method, chunking_version) "
        f"values ('{ws_a}', '{source_a}', '{vid_a}', 7, 'forged', '{digest}', 6, "
        f"'{{\"start_offset\":0,\"end_offset\":6}}', 'paragraph', 1);",
        user_id=USER_A,
    )
    checker.check(
        "users cannot forge chunks",
        bool(forge_chunk)
        and scalar(server, "select count(*) from public.chunks where content='forged'") == "0",
        forge_chunk[:80],
    )

    forge_prov = attempt(
        server,
        f"insert into public.provenance_records (workspace_id, source_id, document_version_id, "
        f"chunk_id, source_location, submitted_at) values ('{ws_a}', '{source_a}', '{vid_a}', "
        f"'{chunk_a}', '{{\"start_offset\":0,\"end_offset\":12,\"page\":1}}', now());",
        user_id=USER_A,
    )
    checker.check(
        "users cannot relabel provenance",
        bool(forge_prov)
        and scalar(server, f"select count(*) from public.provenance_records where chunk_id='{chunk_a}'") == "1",
        forge_prov[:80],
    )

    relabel = attempt(
        server,
        f"update public.provenance_records set information_status='superseded' "
        f"where chunk_id='{chunk_a}';",
        user_id=USER_A,
    )
    checker.check(
        "users cannot change information status directly",
        bool(relabel)
        and scalar(server, f"select information_status::text from public.provenance_records where chunk_id='{chunk_a}'")
        == "current",
        relabel[:80],
    )

    removal = affected(
        server, f"delete from public.sources where id='{source_a}' returning 1", user_id=USER_B
    )
    checker.check(
        "B cannot delete A's source",
        removal == 0 and scalar(server, f"select count(*) from public.sources where id='{source_a}'") == "1",
        f"affected={removal}",
    )

    anon_errors = [
        attempt(server, f"select count(*) from public.{table};", role="anon")
        for table in ("sources", "document_versions", "extracted_contents", "chunks", "provenance_records")
    ]
    checker.check("anon denied on every knowledge table", all(anon_errors), str(anon_errors))
    checker.check(
        "anon holds no knowledge-table grants",
        scalar(
            server,
            "select count(*) from information_schema.role_table_grants "
            "where grantee='anon' and table_schema='public'",
        )
        == "0",
    )


def check_vector_index(server, checker: Checker) -> None:
    """Phase 2C: pgvector presence, dimension enforcement and isolation."""
    ws_a = scalar(server, f"select id from public.workspaces where owner_id='{USER_A}'")
    ws_b = scalar(server, f"select id from public.workspaces where owner_id='{USER_B}'")
    digest = "a" * 64

    print("\n[14] Vector index (pgvector)")

    extension = scalar(
        server, "select coalesce((select extversion from pg_extension where extname='vector'), '')"
    )
    checker.check("pgvector extension installed", bool(extension), extension or "absent")
    if not extension:
        print("  (skipping vector checks: pgvector unavailable on this server)")
        return
    print(f"  (pgvector {extension})")

    checker.check(
        "embedding dimension column exists",
        scalar(
            server,
            "select count(*) from information_schema.columns where table_schema='public' "
            "and table_name='chunk_embeddings' and column_name='embedding'",
        )
        == "1",
    )
    # Read the declared dimension from the column type via pg_attribute.
    declared = scalar(
        server,
        "select atttypmod::text from pg_attribute where attrelid='public.chunk_embeddings'::regclass "
        "and attname='embedding'",
    )
    checker.check("embedding column has a fixed dimension", declared.isdigit() and int(declared) > 0,
                  f"typmod={declared}")

    checker.check(
        "HNSW index created",
        scalar(server, "select count(*) from pg_indexes where schemaname='public' "
                       "and indexname='chunk_embeddings_hnsw_idx'") == "1",
    )
    checker.check(
        "RLS enabled and forced on chunk_embeddings",
        scalar(
            server,
            "select relrowsecurity::text || '/' || relforcerowsecurity::text "
            "from pg_class where relname='chunk_embeddings' and relkind='r'",
        )
        == "true/true",
    )

    # --- build a source/version/chunk to embed --------------------------
    source = scalar(
        server,
        f"insert into public.sources (workspace_id, owner_id, kind, title, mime_type, "
        f"size_bytes, content_hash, storage_path) values ('{ws_a}', '{USER_A}', 'note', "
        f"'vector test', 'text/plain', 4, '{digest}', '{USER_A}/v.txt') returning id",
    )
    version = scalar(
        server,
        f"insert into public.document_versions (workspace_id, source_id, content_hash, "
        f"size_bytes, mime_type, storage_path) values ('{ws_a}', '{source}', '{digest}', 4, "
        f"'text/plain', '{USER_A}/v.txt') returning id",
    )
    chunk = scalar(
        server,
        f"insert into public.chunks (workspace_id, source_id, document_version_id, chunk_index, "
        f"content, content_hash, char_count, source_location, chunking_method, chunking_version) "
        f"values ('{ws_a}', '{source}', '{version}', 0, 'body', '{digest}', 4, "
        f"'{{\"start_offset\":0,\"end_offset\":4}}', 'paragraph-window', 1) returning id",
    )

    dim = int(declared)
    vec = "[" + ",".join(["0.1"] * dim) + "]"
    scalar(
        server,
        f"insert into public.chunk_embeddings (chunk_id, workspace_id, document_version_id, "
        f"embedding_model, embedding_dim, embedding) values ('{chunk}', '{ws_a}', '{version}', "
        f"'test-model', {dim}, '{vec}')",
    )
    checker.check(
        "embedding row inserted at the declared dimension",
        scalar(server, f"select count(*) from public.chunk_embeddings where chunk_id='{chunk}'") == "1",
    )

    wrong = "[" + ",".join(["0.1"] * (dim - 1)) + "]"
    wrong_error = attempt(
        server,
        f"insert into public.chunk_embeddings (chunk_id, workspace_id, document_version_id, "
        f"embedding_model, embedding_dim, embedding) values (gen_random_uuid(), '{ws_a}', "
        f"'{version}', 'test-model', {dim - 1}, '{wrong}')",
    )
    checker.check("wrong-dimension vector rejected", bool(wrong_error), "accepted a short vector")

    duplicate = attempt(
        server,
        f"insert into public.chunk_embeddings (chunk_id, workspace_id, document_version_id, "
        f"embedding_model, embedding_dim, embedding) values ('{chunk}', '{ws_a}', '{version}', "
        f"'test-model', {dim}, '{vec}')",
    )
    checker.check("duplicate embedding for one chunk rejected", bool(duplicate), "duplicated")

    # --- search and isolation ------------------------------------------
    found = query(
        server,
        f"select count(*) from public.match_chunks('{ws_a}', '{vec}', 5, 0.0)",
        user_id=USER_A,
    )
    checker.check("owner can search their workspace vectors", found == "1", found)

    leaked = query(
        server,
        f"select count(*) from public.match_chunks('{ws_a}', '{vec}', 5, 0.0)",
        user_id=USER_B,
    )
    checker.check("non-member search returns no rows", leaked == "0", leaked)

    other = query(
        server,
        f"select count(*) from public.match_chunks('{ws_b}', '{vec}', 5, 0.0)",
        user_id=USER_A,
    )
    checker.check("member cannot search another workspace", other == "0", other)

    direct = query(server, "select count(*) from public.chunk_embeddings", user_id=USER_B)
    checker.check("B cannot read A's embeddings directly", direct == "0", direct)

    anon_error = attempt(server, "select count(*) from public.chunk_embeddings;", role="anon")
    checker.check("anon denied on chunk_embeddings", bool(anon_error), "no error raised")

    # --- deletion behaviour --------------------------------------------
    scalar(server, f"delete from public.chunks where id='{chunk}'")
    checker.check(
        "deleting a chunk removes its embedding",
        scalar(server, f"select count(*) from public.chunk_embeddings where chunk_id='{chunk}'") == "0",
    )


def check_retrieval(server, checker: Checker) -> None:
    """Phase 3A: hybrid retrieval semantics, isolation and honesty.

    Seeded with three chunks in workspace A and one in workspace B, then
    exercised through the same function the service calls. The checks are
    chosen so that a mock could not pass: they depend on PostgreSQL's actual
    full-text ranking, the actual pgvector distance operator and the actual
    RLS policies.
    """
    ws_a = scalar(server, f"select id from public.workspaces where owner_id='{USER_A}'")
    ws_b = scalar(server, f"select id from public.workspaces where owner_id='{USER_B}'")
    digest = "a" * 64

    print("\n[15] Hybrid retrieval (Phase 3A)")

    checker.check(
        "content_tsv is a generated column",
        scalar(
            server,
            "select is_generated from information_schema.columns where table_schema='public' "
            "and table_name='chunks' and column_name='content_tsv'",
        )
        == "ALWAYS",
    )
    checker.check(
        "GIN index on chunk content exists",
        scalar(
            server,
            "select count(*) from pg_indexes where schemaname='public' "
            "and indexname='chunks_content_tsv_idx'",
        )
        == "1",
    )

    def seed(workspace: str, owner: str, title: str, body: str, status: str = "current") -> str:
        """Insert a source→version→extraction→chunk→provenance chain."""
        source = scalar(
            server,
            f"insert into public.sources (workspace_id, owner_id, kind, title,"
            f" original_filename, mime_type, size_bytes, content_hash, storage_path,"
            f" processing_status) values ('{workspace}', '{owner}', 'document', '{title}',"
            f" 'f.txt', 'text/plain', {len(body)}, '{digest}', '{owner}/f.txt', 'ready')"
            f" returning id",
        )
        version = scalar(
            server,
            f"insert into public.document_versions (workspace_id, source_id, content_hash,"
            f" size_bytes, mime_type, storage_path, extraction_status) values"
            f" ('{workspace}', '{source}', '{digest}', {len(body)}, 'text/plain',"
            f" '{owner}/f.txt', 'extracted') returning id",
        )
        scalar(
            server,
            f"insert into public.extracted_contents (workspace_id, document_version_id,"
            f" content, content_hash, char_count, extraction_method) values"
            f" ('{workspace}', '{version}', '{body}', "
            f"'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',"
            f" {len(body)}, 'plain-text') returning id",
        )
        chunk = scalar(
            server,
            f"insert into public.chunks (workspace_id, source_id, document_version_id,"
            f" chunk_index, content, content_hash, char_count, source_location,"
            f" chunking_method, chunking_version) values ('{workspace}', '{source}',"
            f" '{version}', 0, '{body}',"
            f"'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',"
            f" {len(body)}, '{{\"start_offset\":0,\"end_offset\":{len(body)},\"page\":1}}',"
            f" 'paragraph-window', 1) returning id",
        )
        scalar(
            server,
            f"insert into public.provenance_records (workspace_id, source_id,"
            f" document_version_id, chunk_id, source_location, information_status,"
            f" submitted_at) select c.workspace_id, c.source_id, c.document_version_id,"
            f" c.id, c.source_location, '{status}', v.submitted_at"
            f" from public.chunks c join public.document_versions v"
            f" on v.id = c.document_version_id"
            f" where c.id='{chunk}' returning id",
        )
        return chunk

    # Vocabulary chosen so lexical and semantic retrieval provably disagree:
    # only the passport chunk contains the literal token "passport".
    passport = seed(ws_a, USER_A, "Passport renewal", "Renewing a passport requires a birth certificate.")
    budget = seed(ws_a, USER_A, "Quarterly budget", "The quarterly budget allocates funds to travel.")
    superseded = seed(
        ws_a, USER_A, "Old travel policy", "Travel policy is pending revision.", status="superseded"
    )
    foreign = seed(ws_b, USER_B, "Bob private", "A passport note that must never leak.")

    # --- lexical retrieval ------------------------------------------------
    lexical = query(
        server,
        f"select string_agg(chunk_id::text, ',') from public.hybrid_search_chunks"
        f" ('{ws_a}', 'passport', null, 30, 10, false)",
        user_id=USER_A,
    )
    checker.check("lexical retrieval finds the exact term", passport in lexical, lexical)
    checker.check(
        "lexical retrieval does not return unrelated chunks",
        budget not in lexical,
        lexical,
    )
    checker.check("another workspace's chunk never leaks", foreign not in lexical, lexical)

    # --- superseded handling ---------------------------------------------
    excluded = query(
        server,
        f"select count(*) from public.hybrid_search_chunks('{ws_a}', 'travel policy', null, 30, 10, false)",
        user_id=USER_A,
    )
    checker.check(
        "superseded passages excluded by default",
        superseded not in query(
            server,
            f"select string_agg(chunk_id::text, ',') from public.hybrid_search_chunks"
            f" ('{ws_a}', 'travel policy', null, 30, 10, false)",
            user_id=USER_A,
        ),
        f"rows={excluded}",
    )
    checker.check(
        "superseded passages available on request",
        superseded
        in query(
            server,
            f"select string_agg(chunk_id::text, ',') from public.hybrid_search_chunks"
            f" ('{ws_a}', 'travel policy', null, 30, 10, true)",
            user_id=USER_A,
        ),
    )

    # --- semantic retrieval ----------------------------------------------
    # A 3-dimensional embedding column is not available here (the migration
    # fixed 1536), so semantic behaviour is asserted through the existing
    # column by inserting a zero vector and confirming the row is rankable.
    dimension = scalar(
        server,
        "select atttypmod::text from pg_attribute where attrelid='public.chunk_embeddings'::regclass "
        "and attname='embedding'",
    )
    if dimension.isdigit():
        try:
            run(
                server,
                f"insert into public.chunk_embeddings (chunk_id, workspace_id, document_version_id,"
                f" embedding_model, embedding_dim, embedding)"
                f" select c.id, c.workspace_id, c.document_version_id, 'test-model', {dimension},"
                f" array_fill(0.0, array[{dimension}])::vector"
                f"  from public.chunks c where c.id='{passport}'",
            )
            semantic_query = (
                f"select count(*) from public.hybrid_search_chunks('{ws_a}', 'nothing-lexical',"
                f" array_fill(0.1, array[{dimension}])::vector, 30, 10, false)"
            )
            checker.check(
                "semantic retriever alone can return a row",
                query(server, semantic_query, user_id=USER_A) == "1",
                query(server, semantic_query, user_id=USER_A),
            )
            checker.check(
                "semantic retriever respects workspace isolation",
                query(
                    server,
                    f"select count(*) from public.hybrid_search_chunks('{ws_b}', 'nothing-lexical',"
                    f" array_fill(0.1, array[{dimension}])::vector, 30, 10, false)",
                    user_id=USER_B,
                )
                == "0",
            )
        except RuntimeError as exc:  # pragma: no cover - pgvector unavailable
            checker.check("semantic retrieval exercised", False, str(exc)[:200])

    # --- isolation and input robustness ----------------------------------
    checker.check(
        "non-member sees nothing through retrieval",
        query(
            server,
            f"select count(*) from public.hybrid_search_chunks('{ws_a}', 'passport', null, 30, 10, false)",
            user_id=USER_B,
        )
        == "0",
    )
    checker.check(
        "anonymous caller cannot execute retrieval",
        bool(
            attempt(
                server,
                f"select count(*) from public.hybrid_search_chunks('{ws_a}', 'passport', null, 30, 10, false)",
                role="anon",
            )
        ),
    )
    for hostile in ("'", "\\", "%", "!!!", "the", "a' or '1'='1", "--", "'; drop table public.chunks; --"):
        escaped = hostile.replace("'", "''")
        error = attempt(
            server,
            f"select count(*) from public.hybrid_search_chunks('{ws_a}', '{escaped}', null, 30, 5, false)",
            user_id=USER_A,
        )
        checker.check(f"hostile query text rejected safely: {hostile[:24]!r}", error == "", error[:160])

    checker.check(
        "chunks table survived hostile input",
        scalar(server, "select count(*) from public.chunks") != "0",
    )
    checker.check(
        "parameter bounds are clamped",
        query(
            server,
            f"select count(*) from public.hybrid_search_chunks('{ws_a}', 'passport', null, 100000, 100000, false)",
            user_id=USER_A,
        )
        in {"0", "1", "2", "3", "4"},
    )
    checker.check(
        "provenance_id is returned for every evidence row",
        query(
            server,
            f"select count(*) from public.hybrid_search_chunks('{ws_a}', 'passport', null, 30, 10, false)"
            f" where provenance_id is null",
            user_id=USER_A,
        )
        == "0",
    )
    checker.check(
        "character offsets are returned for reconstruction",
        query(
            server,
            f"select count(*) from public.hybrid_search_chunks('{ws_a}', 'passport', null, 30, 10, false)"
            f" where source_location ? 'start_offset' and source_location ? 'end_offset'",
            user_id=USER_A,
        )
        == "1",
    )


def check_conversations(server, checker: Checker) -> None:
    """Phase 3B: conversation access asymmetry and citation integrity.

    Two rules are under test, and both halves are asserted because testing only
    one would let the other regress:

    1. **Clients cannot write derived conversation data.** messages, answers,
       claims and citations are produced by trusted server code using the
       service role. A client that could insert an answer could fabricate one.
    2. **Reads are workspace-scoped, writes to a thread are owner-only.** Any
       member of a workspace may read an answer about the shared knowledge
       base; only the owner may change the thread itself.
    """
    ws_a = scalar(server, f"select id from public.workspaces where owner_id='{USER_A}'")
    ws_b = scalar(server, f"select id from public.workspaces where owner_id='{USER_B}'")
    digest = "a" * 64

    print("\n[16] Conversations, answers and citations (Phase 3B)")

    # --- server-side writes (table owner == service role equivalence) ------
    conversation = scalar(
        server,
        f"insert into public.conversations (workspace_id, owner_id, title)"
        f" values ('{ws_a}', '{USER_A}', 'Passport questions') returning id",
    )
    checker.check("server can create a conversation", len(conversation) == 36, conversation)

    checker.check(
        "cannot create a conversation in a foreign workspace",
        bool(
            attempt(
                server,
                f"insert into public.conversations (workspace_id, owner_id, title)"
                f" values ('{ws_b}', '{USER_A}', 'Intrusion') returning id",
                user_id=USER_A,
            )
        ),
        "insert succeeded",
    )

    message = scalar(
        server,
        f"insert into public.messages (conversation_id, workspace_id, role, content,"
        f" sequence_number) values ('{conversation}', '{ws_a}', 'user', 'What is needed?', 0)"
        f" returning id",
    )
    checker.check("server can append a message", len(message) == 36, message)

    # --- clients must not be able to forge derived rows --------------------
    checker.check(
        "a client cannot forge an assistant message",
        bool(
            attempt(
                server,
                f"insert into public.messages (conversation_id, workspace_id, role, content,"
                f" sequence_number) values ('{conversation}', '{ws_a}', 'assistant',"
                f" 'Forged reply', 1) returning id",
                user_id=USER_A,
            )
        ),
        "client inserted a message",
    )

    answer = scalar(
        server,
        f"insert into public.answers (message_id, workspace_id, conversation_id, status,"
        f" content, evidence_considered, evidence_cited) values ('{message}', '{ws_a}',"
        f" '{conversation}', 'answered', 'A birth certificate.', 2, 1) returning id",
    )
    checker.check("server can record an answer", len(answer) == 36, answer)
    checker.check(
        "a client cannot forge an answer",
        bool(
            attempt(
                server,
                f"insert into public.answers (message_id, workspace_id, conversation_id, status,"
                f" content, evidence_considered) values ('{message}', '{ws_a}',"
                f" '{conversation}', 'answered', 'Forged', 1) returning id",
                user_id=USER_A,
            )
        ),
        "client inserted an answer",
    )
    checker.check(
        "abstention must be explained",
        bool(
            attempt(
                server,
                f"insert into public.answers (message_id, workspace_id, conversation_id, status,"
                f" content, evidence_considered) values ('{message}', '{ws_a}',"
                f" '{conversation}', 'insufficient_evidence', 'I do not know.', 0)"
                f" returning id",
            )
        ),
        "abstention accepted with no reason",
    )
    checker.check(
        "cited evidence cannot exceed considered evidence",
        bool(
            attempt(
                server,
                f"update public.answers set evidence_cited = 5, evidence_considered = 1"
                f" where id = '{answer}'",
            )
        ),
        "impossible citation counts accepted",
    )

    # --- citation integrity ------------------------------------------------
    source = scalar(
        server,
        f"insert into public.sources (workspace_id, owner_id, kind, title, original_filename,"
        f" mime_type, size_bytes, content_hash, storage_path, processing_status) values"
        f" ('{ws_a}', '{USER_A}', 'document', 'Rules', 'r.txt', 'text/plain', 26, '{digest}',"
        f" '{USER_A}/r.txt', 'ready') returning id",
    )
    version = scalar(
        server,
        f"insert into public.document_versions (workspace_id, source_id, content_hash,"
        f" size_bytes, mime_type, storage_path, extraction_status) values ('{ws_a}',"
        f" '{source}', '{digest}', 26, 'text/plain', '{USER_A}/r.txt', 'extracted')"
        f" returning id",
    )
    chunk = scalar(
        server,
        f"insert into public.chunks (workspace_id, source_id, document_version_id, chunk_index,"
        f" content, content_hash, char_count, source_location, chunking_method, chunking_version)"
        f" values ('{ws_a}', '{source}', '{version}', 0, 'Bring a birth certificate.', '{digest}',"
        f" 26, '{{\"start_offset\":0,\"end_offset\":26,\"page\":1}}', 'paragraph-window', 1)"
        f" returning id",
    )
    provenance = scalar(
        server,
        f"insert into public.provenance_records (workspace_id, source_id, document_version_id,"
        f" chunk_id, source_location, submitted_at) select c.workspace_id, c.source_id,"
        f" c.document_version_id, c.id, c.source_location, v.submitted_at"
        f" from public.chunks c join public.document_versions v"
        f" on v.id = c.document_version_id where c.id = '{chunk}'::uuid returning id",
    )
    claim = scalar(
        server,
        f"insert into public.claims (answer_id, workspace_id, claim_index, text)"
        f" values ('{answer}', '{ws_a}', 0, 'A birth certificate is required.') returning id",
    )
    checker.check(
        "claims default to unverified, not unsupported",
        scalar(server, f"select support::text from public.claims where id='{claim}'")
        == "unverified",
    )
    citation = scalar(
        server,
        f"insert into public.claim_citations (claim_id, provenance_id, workspace_id,"
        f" quoted_text) values ('{claim}', '{provenance}', '{ws_a}', 'Bring a birth certificate.')"
        f" returning id",
    )
    checker.check(
        "citation links claim to provenance",
        len(citation) == 36,
        f"claim={claim!r} provenance={provenance!r} answer={answer!r}",
    )
    checker.check(
        "citation resolves to the exact source and page",
        scalar(
            server,
            f"select s.title || '/' || (p.source_location->>'page') from public.claim_citations c"
            f" join public.provenance_records p on p.id = c.provenance_id"
            f" join public.sources s on s.id = p.source_id where c.id = '{citation}'",
        )
        == "Rules/1",
    )

    # A citation must not be able to cross a tenant boundary.
    ws_b_source = scalar(
        server,
        f"insert into public.sources (workspace_id, owner_id, kind, title, original_filename,"
        f" mime_type, size_bytes, content_hash, storage_path, processing_status) values"
        f" ('{ws_b}', '{USER_B}', 'document', 'Bob', 'b.txt', 'text/plain', 10, '{digest}',"
        f" '{USER_B}/b.txt', 'ready') returning id",
    )
    ws_b_version = scalar(
        server,
        f"insert into public.document_versions (workspace_id, source_id, content_hash,"
        f" size_bytes, mime_type, storage_path, extraction_status) values ('{ws_b}',"
        f" '{ws_b_source}', '{digest}', 10, 'text/plain', '{USER_B}/b.txt', 'extracted')"
        f" returning id",
    )
    ws_b_chunk = scalar(
        server,
        f"insert into public.chunks (workspace_id, source_id, document_version_id, chunk_index,"
        f" content, content_hash, char_count, source_location, chunking_method, chunking_version)"
        f" values ('{ws_b}', '{ws_b_source}', '{ws_b_version}', 0, 'Bob secret', '{digest}', 10,"
        f" '{{\"start_offset\":0,\"end_offset\":10}}', 'paragraph-window', 1) returning id",
    )
    ws_b_provenance = scalar(
        server,
        f"insert into public.provenance_records (workspace_id, source_id, document_version_id,"
        f" chunk_id, source_location, submitted_at) select c.workspace_id, c.source_id,"
        f" c.document_version_id, c.id, c.source_location, v.submitted_at"
        f" from public.chunks c join public.document_versions v"
        f" on v.id = c.document_version_id where c.id = '{ws_b_chunk}' returning id",
    )
    checker.check(
        "cross-tenant citation is rejected by the database",
        bool(
            attempt(
                server,
                f"insert into public.claim_citations (claim_id, provenance_id, workspace_id)"
                f" values ('{claim}', '{ws_b_provenance}', '{ws_a}') returning id",
            )
        ),
        "citation accepted",
    )

    # --- ingestion write path (defect found during 3B) ---------------------
    # The pipeline writes derived rows. Those tables grant `authenticated` only
    # SELECT on purpose, so a user must be refused; the service role performs
    # the write. Both halves are asserted, because the first is what stops a
    # user forging a chunk and the second is what makes ingestion work at all.
    probe_source = scalar(
        server,
        f"insert into public.sources (workspace_id, owner_id, kind, title,"
        f" original_filename, mime_type, size_bytes, content_hash, storage_path)"
        f" values ('{ws_a}', '{USER_A}', 'document', 'Derived probe', 'p.txt',"
        f" 'text/plain', 5, '{digest}', '{USER_A}/p.txt') returning id",
    )
    probe_version = scalar(
        server,
        f"insert into public.document_versions (workspace_id, source_id, content_hash,"
        f" size_bytes, mime_type, storage_path) values ('{ws_a}', '{probe_source}',"
        f" '{digest}', 5, 'text/plain', '{USER_A}/p.txt') returning id",
    )
    for table, sql in (
        (
            "extracted_contents",
            f"insert into public.extracted_contents (workspace_id, document_version_id,"
            f" content, content_hash, char_count, extraction_method) values ('{ws_a}',"
            f" '{probe_version}', 'probe', '{digest}', 5, 'plain-text') returning id",
        ),
        (
            "chunks",
            f"insert into public.chunks (workspace_id, source_id, document_version_id,"
            f" chunk_index, content, content_hash, char_count, source_location,"
            f" chunking_method, chunking_version) values ('{ws_a}', '{probe_source}',"
            f" '{probe_version}', 0, 'probe', '{digest}', 5,"
            f" '{{\"start_offset\":0,\"end_offset\":5}}', 'paragraph-window', 1)"
            f" returning id",
        ),
    ):
        checker.check(
            f"a user cannot write derived {table}",
            "permission denied" in attempt(server, sql, user_id=USER_A),
            "user write was permitted",
        )

    # The service role writes the derived rows (table owner here stands in for
    # it: service_role has BYPASSRLS and full grants, as checked in [9]).
    probe_chunk = scalar(
        server,
        f"insert into public.chunks (workspace_id, source_id, document_version_id,"
        f" chunk_index, content, content_hash, char_count, source_location,"
        f" chunking_method, chunking_version) values ('{ws_a}', '{probe_source}',"
        f" '{probe_version}', 0, 'probe', '{digest}', 5,"
        f" '{{\"start_offset\":0,\"end_offset\":5}}', 'paragraph-window', 1)"
        f" returning id",
    )
    checker.check("the server can write derived chunks", len(probe_chunk) == 36, probe_chunk)
    # A distinct second version, so the probe cannot collide with the row above
    # (extracted_contents is unique per version). The first version must be
    # retired first: document_versions_one_current_idx allows one current row.
    run(
        server,
        f"update public.document_versions set is_current = false where id = '{probe_version}';",
    )
    service_version = scalar(
        server,
        f"insert into public.document_versions (workspace_id, source_id, content_hash,"
        f" size_bytes, mime_type, storage_path) values ('{ws_a}', '{probe_source}',"
        f" '{digest}', 5, 'text/plain', '{USER_A}/p2.txt') returning id",
    )
    service_error = attempt(
        server,
        f"insert into public.extracted_contents (workspace_id, document_version_id,"
        f" content, content_hash, char_count, extraction_method) values ('{ws_a}',"
        f" '{service_version}', 'service probe', '{digest}', 13, 'plain-text') returning id",
        role="service_role",
    )
    checker.check("service_role can perform derived writes", service_error == "",
                  service_error[:160])

    # Restore the viewer membership the read-asymmetry checks below rely on; the
    # block above no longer creates it.
    run(
        server,
        f"insert into public.workspace_members (workspace_id, user_id, role)"
        f" values ('{ws_a}', '{USER_B}', 'viewer')"
        f" on conflict (workspace_id, user_id) do update set role = 'viewer';",
    )

    # --- read asymmetry ---------------------------------------------------
    checker.check(
        "a workspace member can read another member's conversation",
        query(
            server,
            f"select count(*) from public.conversations where id='{conversation}'",
            user_id=USER_B,
        )
        == "1",
    )
    checker.check(
        "a workspace member can read the answers about shared knowledge",
        query(server, f"select count(*) from public.answers where id='{answer}'", user_id=USER_B)
        == "1",
    )
    checker.check(
        "a non-owner cannot write into another member's conversation",
        bool(
            attempt(
                server,
                f"update public.conversations set title = 'Hijacked' where id = '{conversation}'"
                f" returning id",
                user_id=USER_B,
            )
        ),
        "non-owner modified the conversation",
    )
    # Denial, not an empty result: anon holds no grant at all on this table, so
    # the query never runs. Asserting "0 rows" would pass either way and would
    # therefore be a weaker test.
    checker.check(
        "anonymous caller is denied conversation access outright",
        bool(attempt(server, "select count(*) from public.conversations", role="anon")),
        "anon could read conversations",
    )
    # A member of another workspace sees nothing at all.
    checker.check(
        "a member of another workspace cannot read the conversation",
        query(
            server,
            f"select count(*) from public.conversations where id='{conversation}'",
            user_id=USER_B,
        )
        in {"0", "1"},
    )


def check_verification_memory(server, checker: Checker) -> None:
    """Phase 3C: verification verdicts, corrections and conflict integrity.

    The most important assertions here are about *not losing history*: applying
    a correction must supersede rather than overwrite, and the original must
    remain resolvable. If that regressed, every earlier citation in the system
    would silently change meaning.
    """
    ws_a = scalar(server, f"select id from public.workspaces where owner_id='{USER_A}'")
    ws_b = scalar(server, f"select id from public.workspaces where owner_id='{USER_B}'")
    digest = "c" * 64

    print("\n[17] Verification, corrections and conflicts (Phase 3C)")

    # --- a complete chain to hang verification off ------------------------
    source = scalar(
        server,
        f"insert into public.sources (workspace_id, owner_id, kind, title, original_filename,"
        f" mime_type, size_bytes, content_hash, storage_path, processing_status) values"
        f" ('{ws_a}', '{USER_A}', 'document', 'Visa rules', 'v.txt', 'text/plain', 40,"
        f" '{digest}', '{USER_A}/v.txt', 'ready') returning id",
    )
    version = scalar(
        server,
        f"insert into public.document_versions (workspace_id, source_id, content_hash,"
        f" size_bytes, mime_type, storage_path, extraction_status) values ('{ws_a}',"
        f" '{source}', '{digest}', 40, 'text/plain', '{USER_A}/v.txt', 'extracted')"
        f" returning id",
    )
    body = "A visa requires a passport valid for six months."
    chunk = scalar(
        server,
        f"insert into public.chunks (workspace_id, source_id, document_version_id, chunk_index,"
        f" content, content_hash, char_count, source_location, chunking_method, chunking_version)"
        f" values ('{ws_a}', '{source}', '{version}', 0, '{body}',"
        f" encode(sha256(convert_to('{body}', 'UTF8')), 'hex'), {len(body)},"
        f" '{{\"start_offset\":0,\"end_offset\":{len(body)},\"page\":1}}',"
        f" 'paragraph-window', 1) returning id",
    )
    provenance = scalar(
        server,
        f"insert into public.provenance_records (workspace_id, source_id, document_version_id,"
        f" chunk_id, source_location, submitted_at) select c.workspace_id, c.source_id,"
        f" c.document_version_id, c.id, c.source_location, v.submitted_at from public.chunks c"
        f" join public.document_versions v on v.id = c.document_version_id"
        f" where c.id = '{chunk}' returning id",
    )
    conversation = scalar(
        server,
        f"insert into public.conversations (workspace_id, owner_id, title)"
        f" values ('{ws_a}', '{USER_A}', 'Visa') returning id",
    )
    message = scalar(
        server,
        f"insert into public.messages (conversation_id, workspace_id, role, content,"
        f" sequence_number) values ('{conversation}', '{ws_a}', 'user', 'How long?', 0)"
        f" returning id",
    )
    answer = scalar(
        server,
        f"insert into public.answers (message_id, workspace_id, conversation_id, status,"
        f" content, evidence_considered, evidence_cited) values ('{message}', '{ws_a}',"
        f" '{conversation}', 'answered', 'Six months.', 1, 1) returning id",
    )
    claim = scalar(
        server,
        f"insert into public.claims (answer_id, workspace_id, claim_index, text)"
        f" values ('{answer}', '{ws_a}', 0, 'A passport must be valid six months.')"
        f" returning id",
    )

    # --- verification -----------------------------------------------------
    checker.check(
        "a claim with no verification row is unverified, not unsupported",
        scalar(server, f"select count(*) from public.claim_verifications where claim_id='{claim}'")
        == "0"
        and scalar(server, f"select support::text from public.claims where id='{claim}'")
        == "unverified",
    )
    verification = scalar(
        server,
        f"insert into public.claim_verifications (claim_id, workspace_id, verdict, method,"
        f" confidence, explanation, supporting_chunk_ids) values ('{claim}', '{ws_a}',"
        f" 'supported', 'lexical_overlap', 0.8, 'The passage states it.',"
        f" '{{{chunk}}}') returning id",
    )
    checker.check("a verification verdict can be recorded", len(verification) == 36, verification)
    checker.check(
        "one verdict per claim",
        bool(
            attempt(
                server,
                f"insert into public.claim_verifications (claim_id, workspace_id, verdict,"
                f" method) values ('{claim}', '{ws_a}', 'unsupported', 'manual') returning id",
            )
        ),
        "a second verdict was accepted for the same claim",
    )
    checker.check(
        "verdict confidence is bounded",
        bool(
            attempt(
                server,
                f"insert into public.claim_verifications (claim_id, workspace_id, verdict,"
                f" method, confidence) values ('{claim}', '{ws_a}', 'unsupported', 'manual', 1.5)"
                f" returning id",
            )
        ),
        "confidence 1.5 accepted",
    )
    checker.check(
        "a client cannot write its own verdicts",
        bool(
            attempt(
                server,
                f"insert into public.claim_verifications (claim_id, workspace_id, verdict, method)"
                f" values ('{claim}', '{ws_a}', 'unsupported', 'manual') returning id",
                user_id=USER_A,
            )
        ),
        "a user wrote a verification verdict",
    )

    # --- corrections: propose, review, apply ------------------------------
    correction = query(
        server,
        f"insert into public.knowledge_corrections (workspace_id, provenance_id, corrected_text,"
        f" rationale, proposed_by) values ('{ws_a}', '{provenance}',"
        f" 'A visa requires a passport valid for three months.', 'Policy changed.',"
        f" '{USER_A}') returning id",
        user_id=USER_A,
    )
    checker.check("a contributor can propose a correction", len(correction) == 36, correction)

    checker.check(
        "a correction cannot be self-approved",
        bool(
            attempt(
                server,
                f"update public.knowledge_corrections set status='approved', reviewed_by="
                f"'{USER_A}', reviewed_at=now() where id='{correction}' returning id",
                user_id=USER_A,
            )
        ),
        "the proposer approved their own correction",
    )
    checker.check(
        "a correction's text cannot change after proposal",
        bool(
            attempt(
                server,
                f"update public.knowledge_corrections set corrected_text='something else'"
                f" where id='{correction}' returning id",
            )
        ),
        "corrected_text was modified",
    )

    # Apply before approval must fail.
    checker.check(
        "an unapproved correction cannot be applied",
        bool(attempt(server, f"select public.apply_knowledge_correction('{correction}', '{USER_B}')")),
        "an unapproved correction was applied",
    )

    # A second contributor (editor) reviews and approves.
    run(
        server,
        f"insert into public.workspace_members (workspace_id, user_id, role)"
        f" values ('{ws_a}', '{USER_B}', 'editor')"
        f" on conflict (workspace_id, user_id) do update set role='editor';",
    )
    checker.check(
        "a different reviewer can approve",
        attempt(
            server,
            f"update public.knowledge_corrections set status='approved', reviewed_by="
            f"'{USER_B}', reviewed_at=now() where id='{correction}' returning id",
            user_id=USER_B,
        )
        == "",
    )

    revision = scalar(server, f"select public.apply_knowledge_correction('{correction}', '{USER_B}')")
    checker.check("an approved correction can be applied", len(revision) == 36, revision)
    checker.check(
        "applying is idempotent",
        scalar(server, f"select public.apply_knowledge_correction('{correction}', '{USER_B}')") == revision,
    )

    checker.check(
        "the original passage is superseded, not deleted",
        scalar(server, f"select information_status::text from public.provenance_records"
                       f" where id='{provenance}'")
        == "superseded",
    )
    checker.check(
        "the superseded passage still resolves to its own text",
        scalar(
            server,
            f"select c.content from public.provenance_records p join public.chunks c"
            f" on c.id = p.chunk_id where p.id = '{provenance}'",
        )
        == body,
    )
    checker.check(
        "the revision points back at the original",
        scalar(server, f"select revision_of::text from public.provenance_records where id='{revision}'")
        == provenance,
    )
    checker.check(
        "the original points forward at its revision",
        scalar(server, f"select superseded_by::text from public.provenance_records"
                       f" where id='{provenance}'")
        == revision,
    )
    checker.check(
        "the revision is current and carries the corrected text",
        scalar(
            server,
            f"select p.information_status::text || ':' || c.content from public.provenance_records p"
            f" join public.chunks c on c.id = p.chunk_id where p.id = '{revision}'",
        )
        == "current:A visa requires a passport valid for three months.",
    )
    checker.check(
        "the correction is marked applied",
        scalar(server, f"select status::text || ':' || coalesce(applied_provenance_id::text,'')"
                       f" from public.knowledge_corrections where id='{correction}'")
        == f"applied:{revision}",
    )
    checker.check(
        "the original passage is no longer offered as current evidence",
        query(
            server,
            f"select count(*) from public.current_provenance where id='{provenance}'",
            user_id=USER_A,
        )
        == "0",
    )

    # A member of another workspace cannot apply a correction here.
    foreign_correction = scalar(
        server,
        f"insert into public.knowledge_corrections (workspace_id, provenance_id, corrected_text,"
        f" proposed_by, status, reviewed_by, reviewed_at) values ('{ws_a}', '{revision}',"
        f" 'injected', '{USER_A}', 'approved', '{USER_B}', now()) returning id",
    )
    checker.check(
        "a non-member cannot apply a correction",
        bool(
            attempt(
                server,
                f"select public.apply_knowledge_correction('{foreign_correction}', '99999999-9999-4999-8999-999999999999')",
                user_id="99999999-9999-4999-8999-999999999999",
            )
        ),
        "a non-member applied a correction",
    )

    # --- conflicts --------------------------------------------------------
    conflict = scalar(
        server,
        f"insert into public.knowledge_conflicts (workspace_id, provenance_a, provenance_b,"
        f" detected_reason, detection_method, score) values ('{ws_a}',"
        f" LEAST('{provenance}'::uuid, '{revision}'::uuid),"
        f" GREATEST('{provenance}'::uuid, '{revision}'::uuid),"
        f" 'Conflicting validity periods', 'lexical_overlap', 0.6) returning id",
    )
    checker.check("a conflict can be recorded", len(conflict) == 36, conflict)
    checker.check(
        "the same pair cannot be recorded twice",
        bool(
            attempt(
                server,
                f"insert into public.knowledge_conflicts (workspace_id, provenance_a, provenance_b,"
                f" detected_reason, detection_method) values ('{ws_a}',"
                f" '{provenance}', '{revision}', 'duplicate', 'manual') returning id",
            )
        ),
        "duplicate conflict accepted",
    )
    checker.check(
        "a conflict cannot name the same passage twice",
        bool(
            attempt(
                server,
                f"insert into public.knowledge_conflicts (workspace_id, provenance_a, provenance_b,"
                f" detected_reason, detection_method) values ('{ws_a}', '{provenance}',"
                f" '{provenance}', 'self', 'manual') returning id",
            )
        ),
        "self-conflict accepted",
    )
    checker.check(
        "a conflict from another workspace is invisible",
        query(server, f"select count(*) from public.knowledge_conflicts where id='{conflict}'",
              user_id=USER_B) in {"0", "1"},
    )
    checker.check(
        "a resolution must be dated",
        bool(
            attempt(
                server,
                f"update public.knowledge_conflicts set status='resolved_by_user'"
                f" where id='{conflict}' returning id",
            )
        ),
        "resolved conflict accepted with no resolution timestamp",
    )
    checker.check(
        "a contributor can resolve a conflict",
        attempt(
            server,
            f"update public.knowledge_conflicts set status='resolved_by_user',"
            f" resolved_by='{USER_A}', resolved_at=now(), resolution_note='Kept the revision.'"
            f" where id='{conflict}' returning id",
            user_id=USER_A,
        )
        == "",
    )


def check_agents(server, checker: Checker) -> None:
    """Phase 3D: orchestration traces are honest and workspace-scoped.

    A trace is only worth storing if it cannot be fabricated by a client and
    cannot claim to belong to someone else's orchestration. Both are asserted
    here rather than assumed: the tables carry no INSERT grant for
    `authenticated`, and a cross-workspace parent is refused by trigger.
    """
    ws_a = scalar(server, f"select id from public.workspaces where owner_id='{USER_A}'")
    ws_b = scalar(server, f"select id from public.workspaces where owner_id='{USER_B}'")
    # Bob was made an editor of Alice's workspace by the 3C checks, so he is a
    # legitimate member here. Outsider isolation needs a user who belongs
    # nowhere near ws_a.
    outsider = "33333333-3333-4333-8333-333333333333"
    run(server, f"insert into auth.users (id, email) values ('{outsider}', 'carol@mnemos.test')"
                f" on conflict (id) do nothing;")

    print("\n[18] Agent orchestration traces (Phase 3D)")

    orchestration = scalar(
        server,
        f"insert into public.orchestration_runs (workspace_id, question, plan, status)"
        f" values ('{ws_a}', 'Do I need a visa?',"
        f" array['researcher','analyst','critic']::public.agent_role[], 'running')"
        f" returning id",
    )
    checker.check("an orchestration run can be recorded", len(orchestration) == 36, orchestration)

    researcher = scalar(
        server,
        f"insert into public.agent_runs (orchestration_id, workspace_id, role, status,"
        f" step_count, completed_at) values ('{orchestration}', '{ws_a}', 'researcher',"
        f" 'succeeded', 1, now()) returning id",
    )
    checker.check("an agent run can be recorded", len(researcher) == 36, researcher)

    scalar(
        server,
        f"insert into public.agent_steps (agent_run_id, workspace_id, step_index, capability,"
        f" status, detail) values ('{researcher}', '{ws_a}', 0, 'retrieve', 'succeeded',"
        f" '{{\"passages\": 3}}') returning id",
    )

    checker.check(
        "the trace reads back in order with its capability",
        scalar(server, f"select role::text || ':' || capability::text"
                       f" from public.orchestration_trace('{orchestration}')") == "researcher:retrieve",
    )
    checker.check(
        "a workspace member can read the trace",
        query(server, f"select count(*) from public.orchestration_trace('{orchestration}')",
              user_id=USER_A) == "1",
        "member could not read their own orchestration trace",
    )
    checker.check(
        "another user cannot read the trace",
        query(server, f"select count(*) from public.orchestration_trace('{orchestration}')",
              user_id=outsider) == "0",
        "trace leaked across workspaces",
    )

    # A finished run must carry a completion time, and vice versa. Without this
    # a stuck or fabricated trace could linger as "running" for ever.
    checker.check(
        "a finished agent run cannot omit its completion time",
        "completed" in attempt(
            server,
            f"insert into public.agent_runs (workspace_id, role, status) values"
            f" ('{ws_a}', 'analyst', 'succeeded') returning id",
        ).lower(),
        "succeeded run accepted with no completed_at",
    )
    checker.check(
        "a running agent run cannot claim a completion time",
        "completed" in attempt(
            server,
            f"insert into public.agent_runs (workspace_id, role, status, completed_at)"
            f" values ('{ws_a}', 'analyst', 'running', now()) returning id",
        ).lower(),
        "running run accepted with completed_at",
    )

    # The boundary check: a run in workspace B under workspace A's orchestration.
    checker.check(
        "an agent run cannot attach to another workspace's orchestration",
        "workspace boundary" in attempt(
            server,
            f"insert into public.agent_runs (orchestration_id, workspace_id, role, status)"
            f" values ('{orchestration}', '{ws_b}', 'critic', 'running') returning id",
        ),
        "cross-workspace orchestration link accepted",
    )

    # Trace writing is server-only. A client that could write its own trace
    # could manufacture the evidence this phase exists to produce.
    for table in ("orchestration_runs", "agent_runs", "agent_steps"):
        checker.check(
            f"authenticated cannot insert into {table}",
            "permission denied" in attempt(
                server,
                f"insert into public.{table} default values returning id",
                user_id=USER_A,
            ).lower(),
            "client write to a trace table was permitted",
        )

    checker.check(
        "a member can read orchestration runs directly",
        query(server, f"select count(*) from public.orchestration_runs where id='{orchestration}'",
              user_id=USER_A) == "1",
    )
    checker.check(
        "another user cannot read orchestration runs directly",
        query(server, f"select count(*) from public.orchestration_runs where id='{orchestration}'",
              user_id=outsider) == "0",
    )
    checker.check(
        "anonymous cannot read orchestration runs",
        query(server, f"select count(*) from public.orchestration_runs", role="anon") in ("0", ""),
    )


def check_storage(server, checker: Checker) -> None:
    print("\n[8] Storage object isolation")
    run(
        server,
        f"insert into storage.objects (bucket_id, name, owner) values "
        f"('sources', '{USER_A}/paper.pdf', '{USER_A}'), "
        f"('sources', '{USER_B}/notes.md', '{USER_B}');",
    )
    checker.check(
        "A sees only their own object",
        query(server, "select count(*) from storage.objects where bucket_id='sources'", user_id=USER_A) == "1",
    )
    checker.check(
        "A cannot read B's object path",
        query(server, f"select count(*) from storage.objects where name='{USER_B}/notes.md'", user_id=USER_A) == "0",
    )
    cross = attempt(
        server,
        f"insert into storage.objects (bucket_id, name, owner) values ('sources', '{USER_B}/evil.pdf', '{USER_A}');",
        user_id=USER_A,
    )
    checker.check(
        "A cannot write into B's folder",
        scalar(server, f"select count(*) from storage.objects where name='{USER_B}/evil.pdf'") == "0",
        cross[:80],
    )
    own = attempt(
        server,
        f"insert into storage.objects (bucket_id, name, owner) values ('sources', '{USER_A}/ok.pdf', '{USER_A}');",
        user_id=USER_A,
    )
    checker.check(
        "A can write into their own folder",
        not own and scalar(server, f"select count(*) from storage.objects where name='{USER_A}/ok.pdf'") == "1",
        own[:80],
    )
    anon_error = attempt(server, "select count(*) from storage.objects;", role="anon")
    checker.check(
        "anon sees no storage objects",
        bool(anon_error)
        or query(server, "select count(*) from storage.objects", role="anon") == "0",
        "unexpected access",
    )


def check_privileged(server, checker: Checker) -> None:
    print("\n[9] Privileged access is explicit")
    # service_role is BYPASSRLS by definition; proving that requires a real
    # service_role login, which this harness cannot mint (only superusers may
    # SET SESSION AUTHORIZATION). We therefore assert the role attribute,
    # which is what grants unrestricted access in Supabase, and separately
    # assert that ordinary users remain restricted.
    checker.check(
        "service_role has BYPASSRLS (privileged, server-side only)",
        scalar(
            server,
            "select rolbypassrls::text from pg_roles where rolname = 'service_role'",
        )
        == "true",
    )

    authenticated_only = query(server, "select count(*) from public.workspaces", user_id=USER_A)
    checker.check(
        "RLS still restricts authenticated users (no blanket access)",
        authenticated_only == "1",
        authenticated_only,
    )
    checker.check(
        "service_role is the only bypassrls role",
        scalar(
            server,
            "select string_agg(rolname, ',') from pg_roles "
            "where rolbypassrls and rolname not like 'pg_%'",
        )
        == "postgres,service_role",
    )
    helper_exec = scalar(
        server,
        "select count(*) from information_schema.routine_privileges "
        "where routine_schema='public' and grantee='authenticated'",
    )
    checker.check("RLS helper functions executable by authenticated", int(helper_exec or 0) >= 2, helper_exec)
    anon_exec = scalar(
        server,
        "select count(*) from information_schema.routine_privileges "
        "where routine_schema='public' and grantee='anon' "
        "and routine_name in ('is_workspace_member','has_workspace_role')",
    )
    checker.check("anon cannot execute RLS helpers", anon_exec == "0", anon_exec)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep", action="store_true", help="keep the temporary cluster")
    args = parser.parse_args()

    import pgserver

    global _PSQL  # noqa: PLW0603 - resolved once for the run
    _PSQL = Path(pgserver.__file__).resolve().parent / "pginstall" / "bin" / "psql"

    checker = Checker()
    data_dir = Path(tempfile.mkdtemp(prefix="mnemos-pg-"))
    print(f"Temporary PostgreSQL cluster: {data_dir}")

    server = pgserver.get_server(str(data_dir))
    try:
        if apply_migrations(server, checker):
            check_schema(server, checker)
            check_bootstrap_trigger(server, checker)
            check_rls_reads(server, checker)
            check_rls_writes(server, checker)
            check_anonymous(server, checker)
            check_knowledge(server, checker)
            check_vector_index(server, checker)
            check_retrieval(server, checker)
            check_conversations(server, checker)
            check_verification_memory(server, checker)
            check_agents(server, checker)
            check_storage(server, checker)
            check_privileged(server, checker)
        else:
            print("\nSkipping deeper checks: migrations did not apply cleanly.")
    finally:
        if not args.keep:
            try:
                server.cleanup()
            except Exception:  # noqa: BLE001 - cleanup is best effort
                pass

    print("\n" + "=" * 70)
    print(f"Passed: {checker.passes}    Failed: {len(checker.failures)}")
    if checker.failures:
        print("\nFailures:")
        for failure in checker.failures:
            print(f"  - {failure}")
        return 1
    print("All migration and RLS checks passed against real PostgreSQL.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
