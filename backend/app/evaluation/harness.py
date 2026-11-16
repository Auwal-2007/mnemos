"""Real PostgreSQL substrate for evaluation runs (Phase 4A).

Why the evaluation runs against a real database
-----------------------------------------------
The system under test is, at its core, a SQL retrieval function plus RLS. A
mocked search would measure the mock. So the harness boots a real PostgreSQL
server, applies every real migration in order, seeds the corpus through the real
ingestion chain, and lets the systems call the real functions.

The only thing stubbed is the embedding provider, and only because none is
configured in this environment; when it is absent both systems run lexically
and the run records that fact.

How parameters are handled
--------------------------
There is no SQL driver in this environment, so statements go through ``psql``.
Query results come back as a single JSON document rather than tab-separated
cells, because corpus text contains newlines and tabs and a TSV parse would
silently corrupt it. Parameters are rendered as properly quoted SQL literals;
this harness only ever runs locally against a scratch database, and it never
accepts input from a request.
"""

from __future__ import annotations

import contextlib
import json
import shutil
import subprocess
import tempfile
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

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


def sql_literal(value: Any) -> str:
    """Render a Python value as a SQL literal.

    Strings are single-quoted with embedded quotes doubled, which is the
    standard-safe form for a literal (no backslash processing assumptions).
    """
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    text = str(value)
    return "'" + text.replace("'", "''") + "'"


def render(sql: str, params: Sequence[Any]) -> str:
    """Substitute ``%s`` placeholders with literals, in order."""
    parts = sql.split("%s")
    if len(parts) - 1 != len(params):
        raise ValueError(
            f"expected {len(parts) - 1} parameters, received {len(params)}; "
            "every %s must have exactly one bound value"
        )
    out: list[str] = [parts[0]]
    for value, tail in zip(params, parts[1:], strict=True):
        out.append(sql_literal(value))
        out.append(tail)
    return "".join(out)


class PsqlDatabase:
    """A thin, JSON-round-tripping psql wrapper."""

    def __init__(self, psql: Path, uri: str) -> None:
        self._psql = psql
        self._uri = uri

    # --- execution -------------------------------------------------------

    def execute(
        self,
        sql: str,
        params: Sequence[Any] = (),
        *,
        user: str | None = None,
    ) -> str:
        """Run a statement batch. Raises on the first error.

        ``params`` is only rendered when supplied, so a migration containing a
        literal percent sign is never mistaken for a placeholder.
        """
        if params:
            sql = render(sql, params)
        prefix = ""
        if user is not None:
            prefix = (
                f"set request.jwt.claim.sub = {sql_literal(user)};\n"
                "set session authorization authenticated;\n"
            )
        script = (
            "\\set ON_ERROR_STOP on\n"
            "\\pset format unaligned\n"
            "\\pset tuples_only on\n"
            f"{prefix}{sql}\n"
        )
        result = subprocess.run(
            [str(self._psql), self._uri],
            input=script.encode(),
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.decode("utf-8", "replace").strip() or "psql failed")
        noise = ("SET", "BEGIN", "COMMIT", "ROLLBACK", "Output format", "Tuples only")
        return "\n".join(
            line.strip()
            for line in result.stdout.decode("utf-8", "replace").splitlines()
            if line.strip() and not any(line.strip().startswith(word) for word in noise)
        )

    def rows(self, sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
        """Return query results as dictionaries.

        Wrapping in ``json_agg`` keeps multi-line text intact, which a
        line-oriented parse cannot promise.
        """
        statement = render(sql, params)
        wrapped = (
            f"select coalesce(json_agg(row_to_json(t)), '[]'::json)::text from ({statement}) t;"
        )
        output = self.execute(wrapped)
        if not output:
            return []
        return list(json.loads(output))

    def scalar(self, sql: str, params: Sequence[Any] = (), *, user: str | None = None) -> str:
        statement = render(sql, params)
        output = self.execute(statement, user=user)
        return output.splitlines()[0].strip() if output else ""

    def one(self, sql: str, params: Sequence[Any] = ()) -> dict[str, Any] | None:
        found = self.rows(sql, params)
        return found[0] if found else None


@dataclass(slots=True)
class EvalDatabase:
    """Bootstrap + migrations + seed, in one place.

    Holding the server handle keeps it alive for the duration of a run; a
    dropped handle would take the scratch cluster with it.
    """

    db: PsqlDatabase
    root: Path
    migrations: tuple[Path, ...] = ()
    _scratch: Path | None = None
    _server: Any = field(default=None, repr=False)

    @property
    def migration_count(self) -> int:
        return len(self.migrations)

    def close(self) -> None:
        server = self._server
        if server is not None:
            # Cleanup is best-effort: a failed stop must not mask a result.
            with contextlib.suppress(Exception):
                server.cleanup()
        self._server = None


def _psql_path() -> Path:
    import pgserver

    return Path(pgserver.__file__).resolve().parent / "pginstall" / "bin" / "psql"


def pgserver_available() -> bool:
    """Whether a scratch PostgreSQL can be started here."""
    try:
        import pgserver  # noqa: F401
    except Exception:
        return False
    return _psql_path().exists()


@contextmanager
def scratch_database(*, migrate: bool = True) -> Iterator[EvalDatabase]:
    """Start a scratch PostgreSQL, apply migrations, yield a handle.

    The cluster is created in a temporary directory and removed on exit; it is
    never the developer's real database.
    """
    import pgserver

    data_dir = Path(tempfile.mkdtemp(prefix="mnemos-eval-"))
    # pgserver exposes `get_server` at runtime but does not declare it, so the
    # attribute is reached dynamically rather than suppressed at the call site.
    get_server = getattr(pgserver, "get_server", None)
    if get_server is None:
        raise RuntimeError("pgserver does not expose get_server")
    server = get_server(str(data_dir))
    psql = _psql_path()
    wrapper = PsqlDatabase(psql, server.get_uri())
    root = Path(__file__).resolve().parents[3]
    migrations = tuple(sorted((root / "supabase" / "migrations").glob("*.sql")))
    handle = EvalDatabase(db=wrapper, root=root, migrations=migrations, _scratch=data_dir)
    handle._server = server
    try:
        wrapper.execute(BOOTSTRAP)
        if migrate:
            for migration in migrations:
                wrapper.execute(migration.read_text(encoding="utf-8"))
        yield handle
    finally:
        handle.close()
        # The server may keep its data directory open briefly after shutdown.
        with contextlib.suppress(Exception):
            shutil.rmtree(data_dir, ignore_errors=True)


__all__ = [
    "BOOTSTRAP",
    "EvalDatabase",
    "PsqlDatabase",
    "pgserver_available",
    "render",
    "scratch_database",
    "sql_literal",
]
