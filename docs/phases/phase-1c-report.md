# Phase 1C — Application Shell and Responsive Experience

**Status:** Complete and verified
**Date:** 2026-11-15

## What was built

### Application shell

| Element | Behaviour |
|---|---|
| Desktop sidebar | 264 px, collapsible to 72 px icon rail; preference persists for the session |
| Tablet (768–1023 px) | Rail is CSS-forced to 72 px and the component renders icon-only, with the collapse control hidden (mismatch found and fixed — see below) |
| Mobile (< 768 px) | Top bar with menu trigger, slide-in drawer with full labels, bottom navigation for the four primary destinations, body scroll locked while the drawer is open |
| Page structure | `PageHeader` (eyebrow, title, description, actions) + `PageContainer` (default/wide/reading/full widths) |
| User area | Identity, account menu, settings link, real sign-out; reports `Signed in` / `Signed out` / `Auth not configured` truthfully |

### Routes

| Route | Surface |
|---|---|
| `/` | Home — product identity, real system status, real workspaces, honest empties |
| `/knowledge` | Knowledge workspace structure (documents, notes, entries, revisions) with disabled actions |
| `/conversations` | Entry point to both conversation modes |
| `/conversations/orchestrator` | Mode A interface |
| `/conversations/agent/:agentId` | Mode B interface (unknown ids render a real not-found state) |
| `/agents` | Directory of the four planned roles |
| `/settings` | Working theme switch, identity, deployment details |
| `/sources` | Explicit "reserved for a later phase" placeholder |
| `/sign-in` | Real Supabase email/password sign-in and sign-up |
| `*` | 404 |

Every navigation destination exists. Nothing in the shell links to a dead route.

### Conversation components (shared by both modes)

`ConversationHeader` (with an explicit `Orchestrated` / `Direct specialist`
badge), `MessageList`, `UserMessage`, `AssistantMessage`, `MessageComposer`,
`ConversationMetadata`, `AgentIndicator`, `EvidencePlaceholder`,
`ConversationView`, plus loading and error states.

The composer is **disabled with a stated reason** in both modes because no
model execution exists. No assistant message is ever fabricated; the
transcript is genuinely empty.

### Agent directory

All four roles render with their intended responsibility, boundaries, inputs,
outputs and target phase, each marked `Planned`. A banner states that these are
contracts, not capabilities.

## Design system

Tokens (`styles/tokens.css`) cover colour, typography, spacing, radius,
borders, shadows, motion, layout widths and breakpoints. Dark is the default
identity; light is first-class. Switching is instant (CSS custom properties on
`[data-theme]`) and persists to `localStorage`.

Type scale runs 11 → 36 px with a 4 px spacing base. Motion is limited to
120–260 ms with one easing curve and is fully disabled under
`prefers-reduced-motion`.

## Defects found and fixed during this subphase

1. **Tablet sidebar mismatch.** CSS forced a 72 px rail below 1024 px while the
   component still rendered full labels, so labels would have been clipped.
   Fixed by deriving the rendered state from the same breakpoint the CSS uses
   (`useMediaQuery`) and hiding the collapse control when the viewport dictates
   the width. Covered by `responsive.test.tsx`.
2. **Accent contrast failure.** White text on the dark-theme accent measured
   **3.18:1** — below WCAG AA. A single accent cannot serve both link-text and
   button-fill roles in dark mode, so a separate `--accent-fill` /
   `--accent-fill-hover` pair was introduced (5.43:1 and 7.03:1 with white).
   The bright accent is retained for text and borders (9.99:1 on surfaces).

## Verification (actual results)

| Check | Result |
|---|---|
| `npm test -- --run` | **78 passed** (9 files) |
| axe-core accessibility audit | **7 surfaces, 0 violations** |
| WCAG contrast assertions | **28 checks across both themes** |
| Responsive/behavioural tests | 9 (mobile trigger, skip link, tablet icon-only, desktop labels, drawer, bottom nav, collapse toggle) |
| `npm run typecheck` | Passed |
| `npm run build` | Passed — 447 kB JS / 44 kB CSS (127 / 6.9 kB gzip) |
| Live dev servers | Frontend 200, backend 200, proxy verified |
| SPA deep links (`/agents`, `/conversations/agent/retrieval`) | 200 |

## Accessibility measures

- Semantic landmarks: `nav` (labelled), `main`, `aside`, `header`, `form`, `dl`.
- Skip link to `#main-content`; `main` is `tabindex="-1"` so it receives focus.
- Visible focus via `:focus-visible` with a two-ring box-shadow.
- Composer labelled, `aria-describedby` for the disabled reason.
- Drawer marked `aria-hidden` when closed; `aria-expanded` on triggers.
- Menus use `role="menu"` / `role="menuitem"`, Escape closes, outside click closes.
- Toasts announced via `role="status"` `aria-live="polite"`.
- Errors use `role="alert"`.
- Touch targets ≥ 44 px on mobile (drawer links, composer, segmented control).
- Contrast verified numerically for both themes (28 assertions).
- `prefers-reduced-motion` honoured globally.

## Responsive strategy

Base styles are mobile-first; desktop enhancements are additive. Breakpoints
align with the required test widths:

| Width | Layout |
|---|---|
| 1440 px | Full 264 px sidebar with labels, 3-column capability grid, aside visible on wide conversations (≥ 1200 px) |
| 1024 px | Icon rail, 2-column grids |
| 768 px | Icon rail; single-column content begins at 767 px |
| 390 px | Top bar + bottom nav, single column, full-width composer |
| 360 px | Same as 390 px; no fixed width exceeds the viewport |

Structural safeguards: all grids use `minmax(0, 1fr)` so children cannot force
overflow; the only fixed width (288 px conversation aside) is `display: none`
below 1200 px; the viewport meta enables `width=device-width`.

## Limitation: no automated visual capture

A real browser could not be provisioned in this environment (Playwright's
Chromium download and browser dependency installation both failed; no system
browser is installed). Consequently:

- **Verified:** layout decisions, breakpoint behaviour, landmark structure,
  labels, focusability, contrast ratios, and build output.
- **Not verified:** pixel rendering at specific widths, and visual regressions.

Responsive correctness is therefore asserted structurally
(`src/app/responsive.test.tsx`) and by CSS inspection, not by screenshots.
When a browser is available, the recommended follow-up is to add Playwright
visual snapshots at 1440/1024/768/390/360. This is recorded as an open item,
not claimed as done.

## Not implemented (by scope)

Agent intelligence, orchestration, OpenRouter execution, document parsing,
chunking, embeddings, vector retrieval, evidence verification, revision
processing, supersession, conflict resolution, deployment.

## CI coverage added

The GitHub Actions workflow now runs four jobs:

| Job | Scope |
|---|---|
| `backend` | Ruff, format check, `mypy` strict, pytest |
| `database` | `scripts/verify-migrations.py` against a real PostgreSQL in CI |
| `frontend` | Vitest, `tsc --noEmit`, production build |
| `repository-hygiene` | env template validation; fails if `.env` is tracked or the service-role key appears in frontend code |
