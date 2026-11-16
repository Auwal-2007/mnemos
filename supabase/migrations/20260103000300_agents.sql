-- =========================================================================
-- MNEMOS — Phase 3D agent definitions and orchestration traces
--
-- What an "agent" is here, stated precisely
--   Not a separate process, not a service, not an autonomous loop. An agent is
--   a named role with: a configured purpose, a model resolved from
--   configuration at run time, a restricted set of capabilities expressed as
--   typed service calls, and a persisted trace of what it did.
--
--   There is no SQL capability, no filesystem access and no network access
--   beyond the configured completion provider. The capability set is enforced
--   in Python by which services an agent is constructed with; the database
--   records what actually happened.
--
-- Tables
--   agent_runs          one row per agent invocation within an orchestration
--   agent_steps         the ordered steps a run took, with typed inputs/outputs
--   orchestration_runs  one row per orchestrated turn, joining the runs
--
-- Why traces are stored and not just logged
--   FR-014 requires execution metadata, and Phase 7 needs evidence that
--   orchestration genuinely happened rather than being described. A trace row
--   that is written only when a real step executed cannot be produced by a
--   system that did not do the work.
--
-- Idempotent, and safe to re-run.
-- =========================================================================

do $$
begin
  if not exists (select 1 from pg_type where typname = 'agent_run_status') then
    create type public.agent_run_status as enum (
      'pending',
      'running',
      'succeeded',
      'failed',
      'skipped'
    );
  end if;
  if not exists (select 1 from pg_type where typname = 'agent_capability') then
    create type public.agent_capability as enum (
      'retrieve',
      'generate',
      'verify',
      'critique',
      'synthesise'
    );
  end if;
end;
$$;

-- -------------------------------------------------------------------------
-- orchestration_runs — one orchestrated answer attempt
-- -------------------------------------------------------------------------
create table if not exists public.orchestration_runs (
  id                  uuid primary key default gen_random_uuid(),
  workspace_id        uuid not null references public.workspaces (id) on delete cascade,
  conversation_id     uuid references public.conversations (id) on delete cascade,
  answer_id           uuid references public.answers (id) on delete set null,
  question            text not null check (char_length(question) between 1 and 4000),
  -- The plan that was chosen, recorded so a run can be explained after the fact.
  plan                text[] not null default '{}',
  status              public.agent_run_status not null default 'pending',
  started_at          timestamptz not null default now(),
  completed_at        timestamptz,
  total_latency_ms    integer check (total_latency_ms is null or total_latency_ms >= 0),
  total_tokens        integer check (total_tokens is null or total_tokens >= 0),
  metadata            jsonb not null default '{}'::jsonb
);

comment on table public.orchestration_runs is
  'One orchestrated question. plan lists the agent roles that were going to run, so a deviation is visible rather than invisible.';

create index if not exists orchestration_runs_workspace_idx
  on public.orchestration_runs (workspace_id, started_at desc);

-- -------------------------------------------------------------------------
-- agent_runs — one agent invocation
-- -------------------------------------------------------------------------
create table if not exists public.agent_runs (
  id                  uuid primary key default gen_random_uuid(),
  orchestration_id    uuid references public.orchestration_runs (id) on delete cascade,
  workspace_id        uuid not null references public.workspaces (id) on delete cascade,
  role                public.agent_role not null,
  status              public.agent_run_status not null default 'pending',
  input_summary       jsonb not null default '{}'::jsonb,
  output_summary      jsonb not null default '{}'::jsonb,
  execution_id        uuid references public.execution_records (id) on delete set null,
  latency_ms          integer check (latency_ms is null or latency_ms >= 0),
  error_code          text,
  step_count          integer not null default 0 check (step_count >= 0),
  started_at          timestamptz not null default now(),
  completed_at        timestamptz,
  constraint agent_runs_completed_when_finished check (
    (status in ('succeeded', 'failed', 'skipped')) = (completed_at is not null)
  )
);

comment on table public.agent_runs is
  'One invocation of one agent role. output_summary holds results (counts, verdicts), never raw prompts or document text.';

create index if not exists agent_runs_orchestration_idx
  on public.agent_runs (orchestration_id, started_at);
create index if not exists agent_runs_workspace_idx
  on public.agent_runs (workspace_id, started_at desc);

-- -------------------------------------------------------------------------
-- agent_steps — the ordered record of what a run did
-- -------------------------------------------------------------------------
create table if not exists public.agent_steps (
  id                  uuid primary key default gen_random_uuid(),
  agent_run_id        uuid not null references public.agent_runs (id) on delete cascade,
  workspace_id        uuid not null references public.workspaces (id) on delete cascade,
  step_index          integer not null check (step_index >= 0),
  capability          public.agent_capability not null,
  status              public.agent_run_status not null,
  detail              jsonb not null default '{}'::jsonb,
  latency_ms          integer check (latency_ms is null or latency_ms >= 0),
  created_at          timestamptz not null default now(),
  constraint agent_steps_unique unique (agent_run_id, step_index)
);

comment on table public.agent_steps is
  'What an agent actually did, step by step. detail records typed outcomes (passage counts, claim verdicts) — not prompts.';

create index if not exists agent_steps_run_idx on public.agent_steps (agent_run_id, step_index);

-- -------------------------------------------------------------------------
-- Row Level Security
--
-- Traces are readable by workspace members so orchestration is inspectable
-- (a user can see which specialists ran and what they concluded). They are
-- written only by the server: an agent trace a client could write would be
-- worthless as evidence.
-- -------------------------------------------------------------------------
alter table public.orchestration_runs enable row level security;
alter table public.agent_runs         enable row level security;
alter table public.agent_steps        enable row level security;

alter table public.orchestration_runs force row level security;
alter table public.agent_runs         force row level security;
alter table public.agent_steps        force row level security;

revoke all on public.orchestration_runs, public.agent_runs, public.agent_steps from anon;
grant select on public.orchestration_runs, public.agent_runs, public.agent_steps
  to authenticated;

drop policy if exists "orchestration_runs_select_member" on public.orchestration_runs;
create policy "orchestration_runs_select_member"
  on public.orchestration_runs for select to authenticated
  using (public.is_workspace_member(workspace_id));

drop policy if exists "agent_runs_select_member" on public.agent_runs;
create policy "agent_runs_select_member"
  on public.agent_runs for select to authenticated
  using (public.is_workspace_member(workspace_id));

drop policy if exists "agent_steps_select_member" on public.agent_steps;
create policy "agent_steps_select_member"
  on public.agent_steps for select to authenticated
  using (public.is_workspace_member(workspace_id));

-- -------------------------------------------------------------------------
-- A trace cannot claim to belong to another workspace's orchestration.
-- -------------------------------------------------------------------------
create or replace function public.validate_agent_run_scope()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  parent_workspace uuid;
begin
  if new.orchestration_id is not null then
    select workspace_id into parent_workspace
      from public.orchestration_runs where id = new.orchestration_id;
    if parent_workspace is null then
      raise exception 'orchestration % does not exist', new.orchestration_id
        using errcode = 'foreign_key_violation';
    end if;
    if parent_workspace <> new.workspace_id then
      raise exception 'agent run crosses a workspace boundary'
        using errcode = 'check_violation';
    end if;
  end if;
  return new;
end;
$$;

drop trigger if exists agent_runs_validate_scope on public.agent_runs;
create trigger agent_runs_validate_scope
  before insert or update of orchestration_id, workspace_id on public.agent_runs
  for each row execute function public.validate_agent_run_scope();

-- -------------------------------------------------------------------------
-- Trace retrieval for one orchestration, in order.
-- SECURITY INVOKER so RLS restricts what a member can read.
-- -------------------------------------------------------------------------
create or replace function public.orchestration_trace(p_orchestration_id uuid)
returns table (
  agent_run_id uuid,
  role public.agent_role,
  run_status public.agent_run_status,
  latency_ms integer,
  step_index integer,
  capability public.agent_capability,
  step_status public.agent_run_status,
  detail jsonb
)
language sql
stable
security invoker
set search_path = public, pg_temp
as $$
  select
    r.id,
    r.role,
    r.status,
    r.latency_ms,
    s.step_index,
    s.capability,
    s.status,
    s.detail
  from public.agent_runs r
  left join public.agent_steps s on s.agent_run_id = r.id
  where r.orchestration_id = p_orchestration_id
  order by r.started_at, r.role, s.step_index;
$$;

comment on function public.orchestration_trace(uuid) is
  'Flattened, ordered trace of an orchestration. SECURITY INVOKER: only a workspace member sees rows.';

revoke all on function public.orchestration_trace(uuid) from public, anon;
grant execute on function public.orchestration_trace(uuid) to authenticated;
