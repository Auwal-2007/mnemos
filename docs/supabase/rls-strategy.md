# Row Level Security Strategy

Every user-owned resource must have a clear ownership relationship and an
RLS policy. Authorization is enforced server-side and via RLS — never
frontend-only.

## Principles

1. **Deny by default:** enable RLS on every user-owned table; policies
   grant access only to the owning user.
2. **Ownership column:** every user-owned table has `owner_id`
   referencing `auth.users(id)`, set from the authenticated session —
   never from client-supplied input.
3. **Least privilege:** policies are per-operation (`SELECT`, `INSERT`,
   `UPDATE`, `DELETE`) with `USING` and `WITH CHECK` clauses.
4. **No privileged keys in clients:** the service-role key bypasses RLS
   and must remain server-side for privileged operations only.
5. **Auditability:** ownership and provenance columns are immutable
   after creation except through validated service operations.

## Planned tables (Phase 1 — not yet created)

- `knowledge_items` — user knowledge with provenance.
- `knowledge_revisions` — versioned revisions of knowledge items.
- `sources` — original document references (Storage paths).
- `evidence_links` — links between claims/answers and sources.
- `conversations` / `messages` — chat history (if required by scope).
- `agent_executions` — model ID, usage, and metadata per execution.

## Policy pattern (illustrative — to be implemented in Phase 1)

```sql
-- Enable RLS and deny by default
alter table public.knowledge_items enable row level security;

-- Users can only see their own rows
create policy "owner_select" on public.knowledge_items
  for select using (auth.uid() = owner_id);
create policy "owner_insert" on public.knowledge_items
  for insert with check (auth.uid() = owner_id);
create policy "owner_update" on public.knowledge_items
  for update using (auth.uid() = owner_id)
  with check (auth.uid() = owner_id);
create policy "owner_delete" on public.knowledge_items
  for delete using (auth.uid() = owner_id);
```

## Testing

RLS policies are tested with two users: user A must not read, modify, or
delete user B's rows. Tests run against a Supabase project or local
stack in the database-test phase — never against production data.
