# Phase UI — Product Redesign Report

**Date:** 2026-11-15
**Scope:** A complete visual and interaction redesign of the existing
application. No backend, schema, API contract or business-logic change.

---

## 1. What existed before (audit)

| Area | State found |
|---|---|
| Framework | React 18.3, Vite 5, TypeScript strict, react-router 6 |
| Styling | Hand-authored CSS with custom properties (ADR-0009 forbids CSS-in-JS) |
| Design system | 8 colour tokens per theme, Inter only, one 6-link sidebar, no motion |
| Public surface | **None.** `/` rendered the authenticated dashboard shell |
| Pages | Home, Knowledge, Conversations (2 modes), Agents, Settings, Sign-in, 404 |
| Dependencies | React, react-router, supabase-js. No animation, icon or 3D library |
| Test suite | 87 tests; axe audit over 7 surfaces; token-derived contrast checks |
| Backend contracts | Sources, versions, chunks, provenance, indexing, workspaces, health |
| Honest-reporting invariants | Status read back from DB, no sample data, planned areas labelled, disabled composers explained |

The functional foundation was sound. What was missing was identity, a public
entry point, and interaction craft.

## 2. What was built

### Public site (new)
`/` is now a marketing surface with its own shell; the product moved to `/app`.

- **Hero** — editorial serif headline ("Your knowledge deserves more than a
  search bar"), a live Three.js knowledge network depicting consolidation,
  two CTAs, an honest privacy line, and a capability marquee.
- **Product demonstration** — a seven-step illustrated pipeline walkthrough
  (ingest → extract → index → retrieve → orchestrate → answer → remember) where
  each step is explicitly labelled **Implemented** or **Planned**, with a
  footer stating that no model runs on the page.
- **Feature bands** — deliberately asymmetric: an editorial split with a
  workspace interface fragment, a reversed split with a retrieval result
  fragment, and one full-width principles band. The three-column card grid is
  used exactly once, for three genuinely parallel facts.
- **Agent showcase** — an interactive topology: orchestrator above, three
  specialists below, SVG connectors that animate only for the selected role,
  and a contract panel listing responsibilities and hard boundaries, sourced
  from the same `AGENT_CATALOG` the product uses.
- **Provenance showcase** — the research contribution made visible: a claim
  traced through passage, version, location, timestamp and content hash, plus
  a revision switcher showing current / superseded / disputed states.
- **Closing CTA and footer** — real navigation only; no invented social links.

### Product shell (redesigned)
- Grouped sidebar (Workspace / Intelligence / System) with a brass active
  marker, collapsible rail, workspace context, and a **command palette**
  (⌘K / Ctrl-K) with keyboard navigation.
- Page transitions that are a 220 ms cross-fade, not a performance.
- Mobile: conditionally-mounted top bar plus a grouped drawer; desktop rail
  never renders clipped labels.

### Screens (all redesigned)
- **Dashboard** (`/app`) — greeting, four real corpus counts, recent sources,
  a proportional pipeline view, agent roster with phases, live integration
  status. Refuses to draw the pipeline without a session.
- **Knowledge** (`/app/knowledge`) — three-column workspace: submission rail
  with live status, filterable/searchable source list, and a detail surface
  showing versions, character ranges, chunk offsets and indexing state.
- **Agents** (`/app/agents`) — orchestration schematic, roster, and a full
  contract inspector with responsibilities, boundaries and inputs/outputs.
- **Conversations** — two modes presented as different kinds of conversation;
  the orchestrator view carries an **execution timeline** that is explicitly
  marked "Planned — not run" because no execution events exist.
- **Evidence panel** (new) — a non-modal drawer reading
  `/chunks/{id}/provenance`, showing document, version, exact character range,
  page, submission timestamp, information status and supersession link.
- **Sign-in** — split surface: identity and thesis on one side, form on the
  other; states unconfigured deployments honestly.
- **Settings** — real preferences and deployment facts only.

### Design system (new)
Tokens in `styles/tokens.css`: three hue families (teal / brass / rose) on a
warm charcoal ramp, a five-step motion scale, fluid type scale, hairlines.
Primitives rebuilt: `Button` (5 variants), `Badge` (3 variants × 6 tones),
`Card` (4 surfaces + cursor glow), `EmptyState` (orbit mark, hero size),
`LoadingState` (skeletons), `Icon` (Lucide, MNEMOS-semantic names).
Motion primitives in `lib/motion/`: reveal, stagger, page transitions,
spotlight, tilt, magnetic, global pointer, scroll offset — every one reduced-
motion aware.

### 3D
One scene, raw Three.js (R3F v9 needs React 19): a single `Points` draw call
with a custom shader for nodes plus one `LineSegments` for edges, three
orbital shells (sources outward in brass, evidence inward in teal), cursor
parallax on the camera, paused when hidden or scrolled away, thinned below
768px, and **lazy-loaded** so `three` never enters the first-paint payload.

## 3. Verification

```
npx tsc --noEmit        → clean
npx vitest run          → 119 passed (11 files)
npm run build           → succeeds
```

Chunk output (gzipped in brackets):

| Chunk | Size | Loaded |
|---|---|---|
| `index` (app) | 151 kB (39.7) | first paint |
| `vendor` | 392 kB (112.5) | first paint |
| `motion` | 130 kB (42.9) | first paint |
| `three` | 472 kB (117.8) | **only when the hero mounts** |
| `HeroOrbit` | 6.2 kB (2.6) | lazy |

Confirmed by inspecting `dist/index.html`: no entry chunk references `three`.

New tests added (32): landing structure and honesty labels, gate on all four
agent roles, contract switching, provenance revision tabs, design-token
integrity, reduced-motion behaviour, cursor effects writing only custom
properties, palette filtering/keyboard/Escape, and shell responsive decisions.
The axe audit was extended to the landing page, the palette and the agent
directory — **0 violations**.

Two real accessibility bugs were found by that audit and fixed:
1. the palette's `role="listbox"` had no accessible name;
2. it contained `div`/`p` children where the listbox pattern only permits
   `group` and `option` — restructured into a valid combobox/listbox.

A third was found by a motion test: the mobile top bar was rendered on desktop
and hidden with CSS, which put duplicate controls in the accessibility tree.
It is now conditionally mounted.

## 4. Acceptance criteria

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | Public landing page exists | **Pass** | `/` renders `LandingPage` + `MarketingShell` |
| 2 | Coherent design system in the app | **Pass** | tokens + primitives + `DESIGN_SYSTEM.md` |
| 3 | All major screens redesigned | **Pass** | dashboard, knowledge, agents, conversations, settings, sign-in, 404 |
| 4 | Agent experiences distinctive | **Pass** | topology diagram, contract inspector, execution timeline |
| 5 | Evidence inspection polished | **Pass** | `EvidencePanel` on the real provenance API |
| 6 | Memory/revision experience polished | **Pass** | provenance showcase revision switcher; real revision data in the detail panel |
| 7 | Cursor interactions work | **Pass (structurally)** | spotlight/tilt/magnetic; asserted by pointer-event tests |
| 8 | Scroll animations work | **Pass** | `Reveal`/`RevealItem` on all landing sections |
| 9 | Meaningful micro-interactions | **Pass** | buttons, nav rail, palette, chips, tabs, uploads, badges |
| 10 | Selected 3D works | **Partial** | scene built and lazy-loaded; **WebGL never executed in a browser** (none available) |
| 11 | Mobile responsiveness verified | **Partial** | decision-level tests pass; no device or browser rendering |
| 12 | Reduced-motion behaviour works | **Pass** | asserted in tests |
| 13 | Backend integrations intact | **Pass** | no API, schema or contract change; all prior backend tests untouched |
| 14 | No critical functionality broken | **Pass** | 119 frontend tests, build succeeds, all routes serve 200 |
| 15 | Production build succeeds | **Pass** | `npm run build` |
| 16 | No placeholder/generic sections | **Pass** | one dead button removed during review; every surface states its own limits |

## 5. Honest gaps

1. **No visual verification.** No browser exists in this environment
   (Playwright's Chromium download is blocked), so nothing was seen rendered.
   Layout and colour were reasoned and structurally tested. **This is the
   largest caveat in this report** and the reason criteria 10 and 11 are marked
   partial rather than pass. A human should load the app and inspect the hero,
   agent diagram and knowledge workspace on a real screen.
2. **The 3D scene has never rendered.** jsdom has no WebGL, so tests exercise
   the fallback path. Shader and geometry are unproven at runtime.
3. **No real-device testing** for touch targets, safe-area insets or mobile
   Safari's `dvh` behaviour.
4. **The evidence panel is not yet wired into a message list**, because there
   are no messages: conversations are not persisted and no model runs. The
   component is complete and reads the real endpoint, but nothing opens it
   automatically yet.
5. **Instrument Serif is Latin-only**; display type in other scripts would fall
   back to the system serif.
6. **`three` is 472 kB.** It is isolated and lazy, but a lighter path (an
   instanced `Points`-only scene without the extra materials) could trim it
   further if the payload becomes a concern.

## 6. Files

**New (24):** `components/brand/MnemosMark.{tsx,css}`,
`components/layout/MarketingShell.{tsx,css}`, `CommandPalette.{tsx,css}`,
`components/conversation/EvidencePanel.{tsx,css}`,
`ExecutionTimeline.{tsx,css}`,
`features/landing/{LandingPage,ProductDemo,AgentShowcase,ProvenanceShowcase,FeatureSections,HeroOrbit,Reveal}.{tsx,css}`,
`features/home/{DashboardPage,KpiStrip,DashboardTimeline,SystemStatusPage}.{tsx,css}`,
`features/home/useCountUp.ts`, `lib/motion/{index,pointer}.ts`,
`styles/fonts.css`, `public/favicon.svg`, `app/designSystem.test.tsx`,
`docs/DESIGN_SYSTEM.md`, `docs/adr/0011-visual-identity-and-motion.md`.

**Modified:** `styles/tokens.css`, `styles/global.css`, `index.html`,
`app/{AppRoutes,navigation,App.test,accessibility.test}`,
`components/layout/{AppShell,Sidebar,MobileNav}` + CSS,
`components/ui/{Button,Badge,Card,EmptyState,LoadingState,Icon,Spinner}` + CSS,
`components/conversation/{ConversationView,ConversationHeader,MessageComposer}` + CSS,
`features/{agents,conversations,knowledge,settings,auth}/**`,
`vite.config.ts`, `package.json`, `src/test/setup.ts`.

**Untouched:** the entire `backend/`, `supabase/`, and `scripts/` trees.
