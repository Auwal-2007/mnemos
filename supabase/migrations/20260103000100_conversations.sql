-- =========================================================================
-- MNEMOS — Phase 3B conversations, grounded answers, claims and citations
--
-- What this migration adds
--   The durable record of *asking*. A conversation belongs to one workspace
--   and one user; a message is either the user's question or the assistant's
--   answer; an answer is decomposed into claims; a claim cites evidence by
--   provenance id; a citation row points at the exact passage that supports it.
--
-- Why claims are separate rows rather than one blob of prose
--   FR-006 requires that a user can inspect the sources supporting a generated
--   answer, and Phase 3C must verify each statement independently. Neither is
--   possible if the answer is stored as a single string with citation markers
--   embedded in it. Decomposing into claim rows makes "which sentence is
--   unsupported" a query rather than a parsing problem.
--
-- Append-only by design
--   messages and answers are never updated in place. A regenerated answer is a
--   new answer row. claims are likewise immutable except for their verification
--   outcome, which Phase 3C writes once. This keeps the audit trail honest: an
--   answer cannot be edited after being shown to a user.
--
-- Execution records
--   execution_records captures what model was used, how long it took, token
--   usage and the outcome. FR-014 requires model id and usage metadata per
--   execution, and Phase 6 needs this table for cost management. No prompt text
--   is stored beyond what the user can already see.
--
-- Idempotent, and safe to re-run.
-- =========================================================================

do $$
begin
  if not exists (select 1 from pg_type where typname = 'message_role') then
    create type public.message_role as enum ('user', 'assistant', 'system');
  end if;
  if not exists (select 1 from pg_type where typname = 'answer_status') then
    create type public.answer_status as enum (
      'answered',
      'insufficient_evidence',
      'refused',
      'failed'
    );
  end if;
  if not exists (select 1 from pg_type where typname = 'claim_support') then
    create type public.claim_support as enum (
      'supported',
      'partially_supported',
      'unsupported',
      'contradicted',
      'unverified'
    );
  end if;
  if not exists (select 1 from pg_type where typname = 'execution_status') then
    create type public.execution_status as enum ('succeeded', 'failed', 'abstained');
  end if;
  if not exists (select 1 from pg_type where typname = 'agent_role') then
    create type public.agent_role as enum (
      'orchestrator',
      'researcher',
      'analyst',
      'critic'
    );
  end if;
end;
$$;

-- -------------------------------------------------------------------------
-- conversations
-- -------------------------------------------------------------------------
create table if not exists public.conversations (
  id                  uuid primary key default gen_random_uuid(),
  workspace_id        uuid not null references public.workspaces (id) on delete cascade,
  owner_id            uuid not null references auth.users (id) on delete cascade,
  title               text not null check (char_length(title) between 1 and 200),
  -- NULL means the central orchestrator; a role means a direct specialist chat.
  agent_role          public.agent_role,
  is_archived         boolean not null default false,
  metadata            jsonb not null default '{}'::jsonb,
  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now()
);

comment on table public.conversations is
  'One conversation thread, scoped to a workspace and its owner. agent_role is NULL for orchestrator threads and set for direct specialist threads.';

create index if not exists conversations_workspace_idx
  on public.conversations (workspace_id, updated_at desc);
create index if not exists conversations_owner_idx on public.conversations (owner_id);

-- -------------------------------------------------------------------------
-- messages
-- -------------------------------------------------------------------------
create table if not exists public.messages (
  id                  uuid primary key default gen_random_uuid(),
  conversation_id     uuid not null references public.conversations (id) on delete cascade,
  workspace_id        uuid not null,
  role                public.message_role not null,
  content             text not null check (char_length(content) > 0),
  sequence_number     integer not null check (sequence_number >= 0),
  -- An assistant message is produced by exactly one execution; a user message
  -- by none. The check below makes that asymmetry a database invariant.
  execution_id        uuid,
  created_at          timestamptz not null default now(),
  constraint messages_sequence_unique unique (conversation_id, sequence_number),
  constraint messages_workspace_fk
    foreign key (workspace_id) references public.workspaces (id) on delete cascade
);

comment on table public.messages is
  'Append-only conversation turns. sequence_number orders them; uniqueness per conversation prevents two turns claiming the same position.';

create index if not exists messages_conversation_idx
  on public.messages (conversation_id, sequence_number);

-- -------------------------------------------------------------------------
-- execution_records — one row per model call (FR-014)
-- -------------------------------------------------------------------------
create table if not exists public.execution_records (
  id                  uuid primary key default gen_random_uuid(),
  workspace_id        uuid not null references public.workspaces (id) on delete cascade,
  conversation_id     uuid references public.conversations (id) on delete cascade,
  agent_role          public.agent_role not null,
  purpose             text not null check (char_length(purpose) between 1 and 64),
  model_id            text not null check (char_length(model_id) between 1 and 200),
  provider            text not null default 'openrouter' check (char_length(provider) between 1 and 64),
  status              public.execution_status not null,
  latency_ms          integer check (latency_ms is null or latency_ms >= 0),
  prompt_tokens       integer check (prompt_tokens is null or prompt_tokens >= 0),
  completion_tokens   integer check (completion_tokens is null or completion_tokens >= 0),
  total_tokens        integer check (total_tokens is null or total_tokens >= 0),
  attempt_count       integer not null default 1 check (attempt_count >= 1),
  error_code          text,
  request_fingerprint text check (request_fingerprint is null or char_length(request_fingerprint) = 64),
  metadata            jsonb not null default '{}'::jsonb,
  started_at          timestamptz not null default now(),
  completed_at        timestamptz
);

comment on table public.execution_records is
  'One row per model invocation: which model, how long, how many tokens, whether it succeeded. FR-014 evidence and Phase 6 cost accounting. No prompt or completion text is stored here.';

create index if not exists execution_records_workspace_idx
  on public.execution_records (workspace_id, started_at desc);
create index if not exists execution_records_conversation_idx
  on public.execution_records (conversation_id);

-- -------------------------------------------------------------------------
-- answers
-- -------------------------------------------------------------------------
create table if not exists public.answers (
  id                  uuid primary key default gen_random_uuid(),
  message_id          uuid not null unique references public.messages (id) on delete cascade,
  workspace_id        uuid not null,
  conversation_id     uuid not null references public.conversations (id) on delete cascade,
  execution_id        uuid references public.execution_records (id) on delete set null,
  status              public.answer_status not null,
  content             text not null check (char_length(content) > 0),
  -- Set when status = insufficient_evidence or refused, so the UI can explain
  -- the abstention instead of showing an unexplained empty answer.
  abstention_reason   text,
  -- Number of passages retrieval supplied, and how many are cited by a claim.
  evidence_considered integer not null default 0 check (evidence_considered >= 0),
  evidence_cited      integer not null default 0 check (evidence_cited >= 0),
  created_at          timestamptz not null default now(),
  constraint answers_workspace_fk
    foreign key (workspace_id) references public.workspaces (id) on delete cascade,
  constraint answers_abstention_explained check (
    status in ('answered', 'failed') or abstention_reason is not null
  ),
  constraint answers_cited_within_considered check (evidence_cited <= evidence_considered)
);

comment on table public.answers is
  'A generated answer, immutable once written. status=insufficient_evidence records an honest abstention rather than a fabricated answer (FR-010).';

create index if not exists answers_conversation_idx on public.answers (conversation_id);

-- -------------------------------------------------------------------------
-- claims — one statement of an answer, verifiable on its own
-- -------------------------------------------------------------------------
create table if not exists public.claims (
  id                  uuid primary key default gen_random_uuid(),
  answer_id           uuid not null references public.answers (id) on delete cascade,
  workspace_id        uuid not null,
  claim_index         integer not null check (claim_index >= 0),
  text                text not null check (char_length(text) between 1 and 4000),
  support             public.claim_support not null default 'unverified',
  -- Populated by Phase 3C verification. NULL means "not yet examined", which
  -- must stay distinguishable from "examined and found unsupported".
  verification_note   text,
  verified_at         timestamptz,
  created_at          timestamptz not null default now(),
  constraint claims_answer_index_unique unique (answer_id, claim_index),
  constraint claims_workspace_fk
    foreign key (workspace_id) references public.workspaces (id) on delete cascade
);

comment on table public.claims is
  'A single factual statement extracted from an answer. support defaults to unverified, which is deliberately different from unsupported: Phase 3C distinguishes "not checked yet" from "checked and failed".';

create index if not exists claims_answer_idx on public.claims (answer_id, claim_index);

-- -------------------------------------------------------------------------
-- claim_citations — which passage supports which claim
-- -------------------------------------------------------------------------
create table if not exists public.claim_citations (
  id                  uuid primary key default gen_random_uuid(),
  claim_id            uuid not null references public.claims (id) on delete cascade,
  provenance_id       uuid not null references public.provenance_records (id) on delete cascade,
  workspace_id        uuid not null,
  -- The quoted span the model relied on, bounded so a citation cannot become
  -- a copy of the whole document.
  quoted_text         text check (quoted_text is null or char_length(quoted_text) <= 2000),
  relevance           double precision check (relevance is null or relevance between 0 and 1),
  created_at          timestamptz not null default now(),
  constraint claim_citations_unique unique (claim_id, provenance_id),
  constraint claim_citations_workspace_fk
    foreign key (workspace_id) references public.workspaces (id) on delete cascade
);

comment on table public.claim_citations is
  'Links one claim to one provenance record. Because provenance is the citation identity, a rendered citation always resolves to an exact document version and offset.';

create index if not exists claim_citations_claim_idx on public.claim_citations (claim_id);
create index if not exists claim_citations_provenance_idx
  on public.claim_citations (provenance_id);

-- messages.execution_id gains its foreign key now that the table exists.
do $$
begin
  if not exists (
    select 1 from pg_constraint where conname = 'messages_execution_fk'
  ) then
    alter table public.messages
      add constraint messages_execution_fk
      foreign key (execution_id) references public.execution_records (id) on delete set null;
  end if;
end;
$$;

-- -------------------------------------------------------------------------
-- Integrity: a claim may only cite evidence from its own workspace
--
-- Enforced in the database because a citation crossing a tenant boundary would
-- leak content even if the API never built such a request. The application
-- also checks this; the constraint is the backstop.
-- -------------------------------------------------------------------------
create or replace function public.validate_claim_citation_workspace()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  claim_workspace uuid;
  provenance_workspace uuid;
begin
  select workspace_id into claim_workspace from public.claims where id = new.claim_id;
  select workspace_id into provenance_workspace
    from public.provenance_records where id = new.provenance_id;

  if claim_workspace is null then
    raise exception 'claim % does not exist', new.claim_id using errcode = 'foreign_key_violation';
  end if;
  if provenance_workspace is null then
    raise exception 'provenance % does not exist', new.provenance_id
      using errcode = 'foreign_key_violation';
  end if;
  if claim_workspace <> provenance_workspace or claim_workspace <> new.workspace_id then
    raise exception 'citation crosses a workspace boundary'
      using errcode = 'check_violation';
  end if;
  return new;
end;
$$;

drop trigger if exists claim_citations_validate_workspace on public.claim_citations;
create trigger claim_citations_validate_workspace
  before insert or update of claim_id, provenance_id, workspace_id on public.claim_citations
  for each row execute function public.validate_claim_citation_workspace();

-- -------------------------------------------------------------------------
-- Integrity: a citation count cannot exceed what retrieval supplied
-- -------------------------------------------------------------------------
create or replace function public.validate_answer_citation_counts()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
begin
  if new.evidence_cited > new.evidence_considered then
    raise exception 'evidence_cited (%) cannot exceed evidence_considered (%)',
      new.evidence_cited, new.evidence_considered
      using errcode = 'check_violation';
  end if;
  return new;
end;
$$;

drop trigger if exists answers_validate_citation_counts on public.answers;
create trigger answers_validate_citation_counts
  before insert or update of evidence_cited, evidence_considered on public.answers
  for each row execute function public.validate_answer_citation_counts();

-- -------------------------------------------------------------------------
-- Row Level Security
--
-- Read access: any member of the workspace may read conversations and their
-- answers, because a shared workspace is a shared knowledge base and an answer
-- about it is not private to the user who asked. Write access is narrower: only
-- the owner may add messages to their own conversation. This is deliberately
-- asymmetric and is asserted in verify-migrations.py.
-- -------------------------------------------------------------------------
alter table public.conversations       enable row level security;
alter table public.messages            enable row level security;
alter table public.execution_records   enable row level security;
alter table public.answers             enable row level security;
alter table public.claims              enable row level security;
alter table public.claim_citations     enable row level security;

alter table public.conversations       force row level security;
alter table public.messages            force row level security;
alter table public.execution_records   force row level security;
alter table public.answers             force row level security;
alter table public.claims              force row level security;
alter table public.claim_citations     force row level security;

revoke all on public.conversations, public.messages, public.execution_records,
              public.answers, public.claims, public.claim_citations
  from anon;
grant select on public.conversations, public.messages, public.execution_records,
                public.answers, public.claims, public.claim_citations
  to authenticated;
grant insert on public.conversations to authenticated;

drop policy if exists "conversations_select_member" on public.conversations;
create policy "conversations_select_member"
  on public.conversations for select to authenticated
  using (public.is_workspace_member(workspace_id));

drop policy if exists "conversations_insert_owner" on public.conversations;
create policy "conversations_insert_owner"
  on public.conversations for insert to authenticated
  with check (
    owner_id = auth.uid() and public.is_workspace_member(workspace_id)
  );

drop policy if exists "conversations_update_owner" on public.conversations;
create policy "conversations_update_owner"
  on public.conversations for update to authenticated
  using (owner_id = auth.uid() and public.is_workspace_member(workspace_id))
  with check (owner_id = auth.uid() and public.is_workspace_member(workspace_id));

drop policy if exists "conversations_delete_owner" on public.conversations;
create policy "conversations_delete_owner"
  on public.conversations for delete to authenticated
  using (owner_id = auth.uid());

drop policy if exists "messages_select_member" on public.messages;
create policy "messages_select_member"
  on public.messages for select to authenticated
  using (public.is_workspace_member(workspace_id));

-- Derived tables are written only by the server-side service role; users can
-- read them but never insert, so a client cannot fabricate an answer.
drop policy if exists "answers_select_member" on public.answers;
create policy "answers_select_member"
  on public.answers for select to authenticated
  using (public.is_workspace_member(workspace_id));

drop policy if exists "claims_select_member" on public.claims;
create policy "claims_select_member"
  on public.claims for select to authenticated
  using (public.is_workspace_member(workspace_id));

drop policy if exists "claim_citations_select_member" on public.claim_citations;
create policy "claim_citations_select_member"
  on public.claim_citations for select to authenticated
  using (public.is_workspace_member(workspace_id));

drop policy if exists "execution_records_select_member" on public.execution_records;
create policy "execution_records_select_member"
  on public.execution_records for select to authenticated
  using (public.is_workspace_member(workspace_id));

-- =========================================================================
-- 5. No schema change for the ingestion write defect
--
-- DEFECT FOUND DURING PHASE 3B WORK (diagnosed here, fixed in the service layer)
--   The Phase 2A/2B/2C pipeline writes extracted text, chunks, provenance and
--   embeddings through the caller's user-scoped Supabase client. The RLS
--   migration granted `authenticated` only SELECT on those tables, so those
--   writes are rejected by PostgreSQL with "permission denied for table chunks".
--   Verified against real PostgreSQL.
--
-- Why this migration deliberately does NOT relax the grants
--   Granting write access to `authenticated` was tried first and rejected: the
--   verifier's existing invariants "users cannot forge chunks" and "users cannot
--   change information status directly" both started failing. That is the
--   correct outcome — a user who can write a chunk or relabel provenance can
--   manufacture a citation, which is exactly what the provenance model exists to
--   prevent.
--
--   The bug is therefore in the server, not the schema: trusted derived writes
--   must go through the service role, as the Phase 2A design states
--   ("written only by the ingestion service (service_role)"). The fix lives in
--   `app/api/deps.py`, which builds the ingestion pipeline with a service-role
--   client for derived writes while keeping the caller's user-scoped client for
--   every operation RLS is meant to police.
--
--   The table grants and policies are unchanged, so the invariant still holds:
--   an authenticated user can read derived knowledge but cannot author it.
-- =========================================================================
