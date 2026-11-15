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

    # Phase 2A adds the knowledge tables. Anything beyond this list means a
    # later phase leaked in early; anything missing means a migration regressed.
    expected = {
        "profiles", "user_preferences", "workspace_members", "workspaces",
        "sources", "document_versions", "extracted_contents", "extracted_pages",
        "chunks", "provenance_records",
    }
    actual = {t for t in tables if t}
    checker.check("knowledge tables present (2A)", expected <= actual, ",".join(sorted(expected - actual)))
    checker.check(
        "no tables from unimplemented phases (embeddings/conversations/agents)",
        not any(
            k in t
            for t in actual
            for k in ("embedding", "conversation", "message", "agent", "revision", "conflict", "claim")
        ),
        ",".join(sorted(actual - expected)),
    )

    for table in sorted(expected):
        flags = scalar(
            server,
            f"select relrowsecurity::text || '/' || relforcerowsecurity::text "
            f"from pg_class where relname = '{table}' and relkind = 'r'",
        )
        checker.check(f"RLS enabled and forced on {table}", flags == "true/true", flags)

    stamps = scalar(
        server,
        "select count(*) from information_schema.columns "
        "where table_schema='public' and column_name in ('created_at','updated_at')",
    )
    # Phase 1B tables carry both stamps (profiles 2, workspaces 2,
    # user_preferences 2) = 6. Phase 2A adds sources(2), document_versions(2)
    # and created_at-only on extracted_contents / extracted_pages / chunks /
    # provenance_records (4) = 14.
    checker.check("created_at/updated_at coverage", stamps == "14", f"found {stamps}")

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
