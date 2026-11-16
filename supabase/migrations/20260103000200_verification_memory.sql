-- =========================================================================
-- MNEMOS — Phase 3C verification, corrections and conflict detection
--
-- What was missing before this migration
--   The `information_status` enum and the `revision_of` / `superseded_by`
--   columns were created in Phase 2A and never used by any code. An answer
--   could therefore cite superseded material with no way to mark it, and a user
--   had no way to correct anything the system had stored.
--
-- Three capabilities, each with its own audit trail
--
--   1. Verification (FR-006, FR-010)
--      Every claim gets a verdict: supported, partially_supported, unsupported,
--      contradicted or unverified. The verdict is stored with the evidence that
--      produced it, so "why did this claim fail" is answerable later.
--
--   2. Corrections and revisions (FR-007, FR-009, FR-012)
--      A correction never edits the original passage. It creates a *new*
--      provenance record for the corrected text, links it as a revision, and
--      marks the original superseded. The old row remains queryable, which is
--      what makes historical questions answerable and the audit honest.
--
--   3. Conflict detection (FR-008)
--      When two passages in the same workspace assert incompatible things, a
--      conflict row records both, the detected reason and a status. Detection
--      is deliberately conservative and its method is recorded, so nobody can
--      mistake a heuristic for a proof.
--
-- Idempotent, and safe to re-run.
-- =========================================================================

do $$
begin
  if not exists (select 1 from pg_type where typname = 'verification_method') then
    create type public.verification_method as enum (
      'lexical_overlap',
      'model_judgement',
      'manual'
    );
  end if;
  if not exists (select 1 from pg_type where typname = 'correction_status') then
    create type public.correction_status as enum (
      'proposed',
      'approved',
      'rejected',
      'applied'
    );
  end if;
  if not exists (select 1 from pg_type where typname = 'conflict_status') then
    create type public.conflict_status as enum (
      'open',
      'resolved_by_user',
      'dismissed'
    );
  end if;
end;
$$;

-- -------------------------------------------------------------------------
-- claim_verifications — one verdict per claim, with its basis
-- -------------------------------------------------------------------------
create table if not exists public.claim_verifications (
  id                  uuid primary key default gen_random_uuid(),
  claim_id            uuid not null unique references public.claims (id) on delete cascade,
  workspace_id        uuid not null references public.workspaces (id) on delete cascade,
  verdict             public.claim_support not null,
  method              public.verification_method not null,
  -- 0..1; how well the cited evidence actually supports the claim. NULL when the
  -- method does not produce a score, rather than a misleading zero.
  confidence          double precision check (confidence is null or confidence between 0 and 1),
  explanation         text check (explanation is null or char_length(explanation) <= 2000),
  -- The evidence the verdict was based on. Empty means "nothing supported it",
  -- which is different from "not checked" (a claim with no verification row).
  supporting_chunk_ids uuid[] not null default '{}',
  contradicted_by_chunk_ids uuid[] not null default '{}',
  execution_id        uuid references public.execution_records (id) on delete set null,
  verified_at         timestamptz not null default now()
);

comment on table public.claim_verifications is
  'Verdict for one claim. Absence of a row means unverified; unsupported is a positive finding, so the two must never be conflated.';

create index if not exists claim_verifications_workspace_idx
  on public.claim_verifications (workspace_id, verified_at desc);

-- -------------------------------------------------------------------------
-- knowledge_corrections — a proposed change to a passage (FR-009)
--
-- The correction text is stored separately from the passage it corrects. It
-- only becomes knowledge when approved, at which point apply_knowledge_correction
-- creates the revision and supersession. Nothing is ever overwritten.
-- -------------------------------------------------------------------------
create table if not exists public.knowledge_corrections (
  id                    uuid primary key default gen_random_uuid(),
  workspace_id          uuid not null references public.workspaces (id) on delete cascade,
  provenance_id         uuid not null references public.provenance_records (id) on delete cascade,
  corrected_text        text not null check (char_length(corrected_text) between 1 and 20000),
  rationale             text check (rationale is null or char_length(rationale) <= 2000),
  status                public.correction_status not null default 'proposed',
  proposed_by           uuid not null references auth.users (id) on delete cascade,
  reviewed_by           uuid references auth.users (id) on delete set null,
  reviewed_at           timestamptz,
  -- Set when applied: the revision provenance record created from this row.
  applied_provenance_id uuid references public.provenance_records (id) on delete set null,
  created_at            timestamptz not null default now(),
  constraint corrections_review_consistent check (
    (status in ('approved', 'rejected', 'applied')) = (reviewed_at is not null)
  ),
  constraint corrections_applied_has_revision check (
    (status = 'applied') = (applied_provenance_id is not null)
  )
);

comment on table public.knowledge_corrections is
  'A proposed correction. Approval is a separate, auditable act; applying it creates a revision rather than editing history.';

create index if not exists knowledge_corrections_workspace_idx
  on public.knowledge_corrections (workspace_id, status, created_at desc);
create index if not exists knowledge_corrections_provenance_idx
  on public.knowledge_corrections (provenance_id);

-- -------------------------------------------------------------------------
-- knowledge_conflicts — two passages that cannot both be current (FR-008)
-- -------------------------------------------------------------------------
create table if not exists public.knowledge_conflicts (
  id                    uuid primary key default gen_random_uuid(),
  workspace_id          uuid not null references public.workspaces (id) on delete cascade,
  provenance_a          uuid not null references public.provenance_records (id) on delete cascade,
  provenance_b          uuid not null references public.provenance_records (id) on delete cascade,
  -- Why the pair was flagged. Recorded verbatim so the method is auditable and
  -- cannot be presented as more certain than it is.
  detected_reason       text not null check (char_length(detected_reason) between 1 and 200),
  detection_method      public.verification_method not null,
  score                 double precision check (score is null or score between 0 and 1),
  status                public.conflict_status not null default 'open',
  resolved_by           uuid references auth.users (id) on delete set null,
  resolved_at           timestamptz,
  resolution_note       text check (resolution_note is null or char_length(resolution_note) <= 2000),
  created_at            timestamptz not null default now(),
  constraint conflicts_distinct_provenance check (provenance_a <> provenance_b),
  -- Canonical ordering, so the same pair cannot be stored twice in two orders.
  constraint conflicts_canonical_order check (provenance_a < provenance_b),
  constraint conflicts_unique_pair unique (provenance_a, provenance_b),
  constraint conflicts_resolution_consistent check (
    (status = 'open') = (resolved_at is null)
  )
);

comment on table public.knowledge_conflicts is
  'A detected contradiction between two passages. The pair is stored in canonical id order with a unique constraint so one conflict is one row.';

create index if not exists knowledge_conflicts_workspace_idx
  on public.knowledge_conflicts (workspace_id, status, created_at desc);

-- -------------------------------------------------------------------------
-- Applying a correction
--
-- A single transaction that:
--   1. creates a new chunk holding the corrected text (same version, so the
--      original document is not altered);
--   2. creates a provenance record for it, linked as revision_of the original;
--   3. marks the original superseded and points superseded_by at the revision;
--   4. marks the correction applied.
--
-- SECURITY DEFINER because it writes derived rows users may not write directly,
-- but it checks membership itself before doing anything. It cannot be used to
-- touch another workspace's data.
-- -------------------------------------------------------------------------
create or replace function public.apply_knowledge_correction(
  p_correction_id uuid,
  p_actor uuid
)
returns uuid
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  correction public.knowledge_corrections;
  original public.provenance_records;
  new_chunk_id uuid;
  new_provenance_id uuid;
  next_index integer;
begin
  select * into correction
    from public.knowledge_corrections
   where id = p_correction_id;

  if correction.id is null then
    raise exception 'correction % does not exist', p_correction_id
      using errcode = 'no_data_found';
  end if;

  -- The actor is passed explicitly because, inside a SECURITY DEFINER function,
  -- auth.uid() still reflects the *invoker's* JWT — but relying on that would
  -- make the check invisible at the call site and easy to break. The caller in
  -- the service layer passes the authenticated user id it already verified, and
  -- membership is checked here again so the function is safe on its own.
  if p_actor is null or not exists (
    select 1 from public.workspace_members m
     where m.workspace_id = correction.workspace_id
       and m.user_id = p_actor
       and m.role in ('owner', 'editor')
  ) then
    raise exception 'not a contributor to this workspace'
      using errcode = 'insufficient_privilege';
  end if;

  -- Belt and braces: if a JWT happens to be present, it must match the actor,
  -- so one authenticated request cannot apply a correction as another user.
  if auth.uid() is not null and auth.uid() <> p_actor then
    raise exception 'actor does not match the authenticated user'
      using errcode = 'insufficient_privilege';
  end if;

  if correction.status not in ('approved', 'applied') then
    raise exception 'only an approved correction can be applied (status=%)', correction.status
      using errcode = 'check_violation';
  end if;

  if correction.applied_provenance_id is not null then
    return correction.applied_provenance_id;  -- idempotent
  end if;

  select * into original
    from public.provenance_records
   where id = correction.provenance_id;

  if original.id is null then
    raise exception 'the passage being corrected no longer exists'
      using errcode = 'no_data_found';
  end if;

  select coalesce(max(chunk_index), -1) + 1 into next_index
    from public.chunks
   where document_version_id = original.document_version_id;

  insert into public.chunks (
    workspace_id, source_id, document_version_id, chunk_index, content,
    content_hash, char_count, source_location, chunking_method, chunking_version, metadata
  )
  values (
    original.workspace_id, original.source_id, original.document_version_id, next_index,
    correction.corrected_text,
    encode(sha256(convert_to(correction.corrected_text, 'UTF8')), 'hex'),
    char_length(correction.corrected_text),
    jsonb_build_object(
      'start_offset', 0,
      'end_offset', char_length(correction.corrected_text)
    ),
    'user-correction', 1,
    jsonb_build_object('corrects_chunk_id', original.chunk_id)
  )
  returning id into new_chunk_id;

  insert into public.provenance_records (
    workspace_id, source_id, document_version_id, chunk_id, source_location,
    information_status, revision_of, submitted_at, resolution_metadata
  )
  values (
    original.workspace_id, original.source_id, original.document_version_id,
    new_chunk_id,
    jsonb_build_object(
      'start_offset', 0,
      'end_offset', char_length(correction.corrected_text)
    ),
    'current', original.id, original.submitted_at,
    jsonb_build_object(
      'correction_id', correction.id,
      'corrected_by', correction.reviewed_by,
      'rationale', correction.rationale
    )
  )
  returning id into new_provenance_id;

  update public.provenance_records
     set information_status = 'superseded',
         superseded_by = new_provenance_id
   where id = original.id;

  update public.knowledge_corrections
     set status = 'applied',
         applied_provenance_id = new_provenance_id
   where id = correction.id;

  return new_provenance_id;
end;
$$;

comment on function public.apply_knowledge_correction(uuid, uuid) is
  'Creates a revision of the corrected passage and supersedes the original. Takes the acting user explicitly and re-checks contributor membership; idempotent for an already-applied correction.';

revoke all on function public.apply_knowledge_correction(uuid, uuid) from public, anon;
grant execute on function public.apply_knowledge_correction(uuid, uuid) to authenticated;

-- -------------------------------------------------------------------------
-- Row Level Security
--
-- Verifications are readable in the workspace and written only by the server
-- (a user who could write their own verdicts could mark their own claims
-- supported). Corrections are different: a user *may* propose one, because that
-- is the point, but only a reviewer may approve or reject it.
-- -------------------------------------------------------------------------
alter table public.claim_verifications    enable row level security;
alter table public.knowledge_corrections  enable row level security;
alter table public.knowledge_conflicts    enable row level security;

alter table public.claim_verifications    force row level security;
alter table public.knowledge_corrections  force row level security;
alter table public.knowledge_conflicts    force row level security;

revoke all on public.claim_verifications, public.knowledge_corrections,
              public.knowledge_conflicts
  from anon;

grant select on public.claim_verifications to authenticated;
grant select, insert, update on public.knowledge_corrections to authenticated;
grant select, update on public.knowledge_conflicts to authenticated;

drop policy if exists "claim_verifications_select_member" on public.claim_verifications;
create policy "claim_verifications_select_member"
  on public.claim_verifications for select to authenticated
  using (public.is_workspace_member(workspace_id));

drop policy if exists "corrections_select_member" on public.knowledge_corrections;
create policy "corrections_select_member"
  on public.knowledge_corrections for select to authenticated
  using (public.is_workspace_member(workspace_id));

drop policy if exists "corrections_insert_contributor" on public.knowledge_corrections;
create policy "corrections_insert_contributor"
  on public.knowledge_corrections for insert to authenticated
  with check (
    proposed_by = auth.uid()
    and public.can_contribute_to_workspace(workspace_id)
  );

-- Only a reviewer (still a contributor, but acting on the row) may move a
-- correction forward. The trigger below stops the proposing user from
-- approving their own correction.
drop policy if exists "corrections_update_reviewer" on public.knowledge_corrections;
create policy "corrections_update_reviewer"
  on public.knowledge_corrections for update to authenticated
  using (public.can_contribute_to_workspace(workspace_id))
  with check (public.can_contribute_to_workspace(workspace_id));

drop policy if exists "conflicts_select_member" on public.knowledge_conflicts;
create policy "conflicts_select_member"
  on public.knowledge_conflicts for select to authenticated
  using (public.is_workspace_member(workspace_id));

drop policy if exists "conflicts_resolve_contributor" on public.knowledge_conflicts;
create policy "conflicts_resolve_contributor"
  on public.knowledge_conflicts for update to authenticated
  using (public.can_contribute_to_workspace(workspace_id))
  with check (public.can_contribute_to_workspace(workspace_id));

-- -------------------------------------------------------------------------
-- A correction cannot be self-approved
--
-- Separation of duties: the person who proposes a correction may not be the
-- person who approves it. Enforced in the database so a future API change
-- cannot quietly drop the rule.
-- -------------------------------------------------------------------------
create or replace function public.validate_correction_review()
returns trigger
language plpgsql
security definer
set search_path = public, pg_temp
as $$
begin
  if new.status in ('approved', 'rejected', 'applied')
     and old.status = 'proposed'
     and new.reviewed_by = new.proposed_by then
    raise exception 'a correction cannot be approved by the user who proposed it'
      using errcode = 'check_violation';
  end if;

  -- Content is immutable once proposed: changing what was approved would make
  -- the audit trail meaningless.
  if new.corrected_text <> old.corrected_text
     or new.provenance_id <> old.provenance_id
     or new.workspace_id <> old.workspace_id then
    raise exception 'a correction''s content is immutable once proposed'
      using errcode = 'integrity_constraint_violation';
  end if;

  return new;
end;
$$;

drop trigger if exists corrections_validate_review on public.knowledge_corrections;
create trigger corrections_validate_review
  before update on public.knowledge_corrections
  for each row execute function public.validate_correction_review();

-- The one-argument form from the first draft, if it exists, is removed so a
-- deployment cannot keep calling a version without the actor check.
drop function if exists public.apply_knowledge_correction(uuid);

-- -------------------------------------------------------------------------
-- Reading superseded material is always possible; using it as current is not.
-- This view makes the current set explicit for any caller that wants it.
-- -------------------------------------------------------------------------
create or replace view public.current_provenance
with (security_invoker = true)
as
  select *
    from public.provenance_records
   where information_status in ('current', 'disputed', 'pending_review');

comment on view public.current_provenance is
  'Provenance records that may be treated as live. SECURITY INVOKER so RLS on the base table applies to the reader.';

-- A view is a separate object: the SELECT grant on the base table does not
-- carry over. Without this, a real authenticated request receives "permission
-- denied", which the migration verifier caught (the seed script ran as owner).
revoke all on public.current_provenance from anon;
grant select on public.current_provenance to authenticated;

-- -------------------------------------------------------------------------
-- Reading passage text by provenance id
--
-- Verification and conflict detection both need the text behind a provenance
-- id. Doing it one id at a time would be a round trip per claim, so this takes
-- an array. SECURITY INVOKER: RLS on provenance_records, chunks and sources
-- applies, and ids outside the caller's workspaces simply return nothing.
-- -------------------------------------------------------------------------
create or replace function public.provenance_text_for_workspace(
  p_workspace_id uuid,
  p_provenance_ids uuid[]
)
returns table (
  provenance_id uuid,
  chunk_id uuid,
  source_id uuid,
  source_title text,
  information_status public.information_status,
  content text
)
language sql
stable
security invoker
set search_path = public, pg_temp
as $$
  select
    p.id,
    c.id,
    c.source_id,
    s.title,
    p.information_status,
    c.content
  from public.provenance_records p
  join public.chunks c on c.id = p.chunk_id
  join public.sources s on s.id = c.source_id
  where p.workspace_id = p_workspace_id
    and p.id = any(p_provenance_ids);
$$;

comment on function public.provenance_text_for_workspace(uuid, uuid[]) is
  'Passage text and title for a set of provenance ids in one workspace. SECURITY INVOKER so RLS restricts it to what the caller may read.';

revoke all on function public.provenance_text_for_workspace(uuid, uuid[]) from public, anon;
grant execute on function public.provenance_text_for_workspace(uuid, uuid[]) to authenticated;
