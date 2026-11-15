# ADR-0011: Visual identity, motion system and selected 3D

- **Status:** Accepted
- **Date:** 2026-11-15
- **Extends:** ADR-0002 (React + Vite), ADR-0009 (CSS custom properties, no CSS-in-JS)

## Context

The product worked but looked like a generic dashboard: default-blue accents,
Inter everywhere, a six-link sidebar, an unstyled landing area, and no motion
language. The brief was a genuine redesign — a distinctive identity, a real
public site, and interaction craft — without touching the backend, the data
model, or any honest-reporting behaviour the earlier phases had established.

Three constraints shaped every decision:

1. **The product's credibility rests on honesty.** It refuses to fabricate
   data, status or activity. A redesign that added decorative "AI thinking"
   animations, invented metrics or fake agent traces would have destroyed the
   thing that makes the product worth using. The visual system had to be
   *more* precise about what is real, not less.
2. **ADR-0009 forbids CSS-in-JS.** Styling stays in hand-authored CSS with
   custom properties. A tokens file is therefore the only place a palette can
   live, and contrast has to be verifiable from that file.
3. **React 18.** React-Three-Fiber v9 requires React 19, so a declarative 3D
   renderer is not available without a React upgrade that is out of scope.

## Decision

### 1. One identity: "warm archive, cold machine"

The palette is built on a **warm charcoal** ramp — a trace of red and yellow in
the greys — instead of the blue-black that every AI product uses. Against it,
exactly three hue families carry meaning:

| Hue | Meaning | Where it appears |
|---|---|---|
| **Teal** (`#4fc3b4`) | live machine intelligence | active nav, focus rings, running processes, links |
| **Brass** (`#c99a52`) | the durable human record | sources, citations, provenance, revisions, supersession |
| **Rose** (`#e87d73`) | conflict and failure | disputes, errors, destructive affordances |

Nothing else. A fourth colour would dilute the semantic load, so states are
expressed with surface value and weight instead. Saturated teal is reserved
for *state*, never for primary buttons — which is why the primary action is
paper-white on charcoal, the single highest-contrast element on any screen.

### 2. Typography does the hierarchy

Three faces, each with a job:

- **Instrument Serif** — display only (hero, page titles, section headings).
  An editorial, high-contrast serif signals "archive", not "startup".
- **Inter Variable** — all UI text.
- **JetBrains Mono** — every literal value: character offsets, content hashes,
  chunk ids, timestamps, status labels. If a number came from the database it
  is set in mono, so real data is visually distinguishable from prose.

Self-hosted via `@fontsource`, so there is no third-party font CDN, no
render-blocking remote stylesheet and no licensing ambiguity.

### 3. Motion is a system, not decoration

One engine (`framer-motion`) plus CSS transitions driven by shared tokens.
Durations and curves are mirrored between `tokens.css` and `lib/motion` so JS
and CSS motion are indistinguishable. Four rules:

- **Reveals settle, they do not travel.** 14px of rise, once, slightly before
  centre. Content never re-animates on a second scroll pass.
- **Cursor effects are additive.** Spotlight, tilt and magnetic all write CSS
  custom properties or transforms; none captures pointer events, none moves a
  hit target, and a user who never moves the mouse sees the finished design.
- **Reduced motion is honoured at the source.** `useMotionPreference()` is the
  single policy point; every variant builder returns a no-op under it, the 3D
  scene renders one static frame, and the demo progress bar is not rendered.
- **Loading states never invent progress.** The interface prints a percentage
  only when it came from the backend; otherwise it shows a status word.

### 4. 3D: one scene, lazily loaded, with a designed fallback

The hero's knowledge network is **raw Three.js**, not React-Three-Fiber, for
the React 18 reason above. It is:

- **lazy-loaded** behind `React.lazy` so `three` (472 kB) is absent from the
  first-paint payload — verified: it appears in no entry chunk;
- **one draw call for nodes** (a single `Points` with a custom shader) plus one
  for edges, not hundreds of meshes;
- **paused** when the tab is hidden or the hero scrolls out of view;
- **thinned** on viewports under 768px;
- **fallback-first**: a designed SVG orbit renders underneath, which is what
  users see before WebGL initialises, if context creation fails, or when
  motion is reduced.

The scene depicts consolidation — sources on the outer shell feeding inward to
a core — so it is an argument about the product, not a particle sphere.

### 5. Honesty is a visual feature

Every new surface states its own limits, and the design makes those statements
prominent rather than burying them:

- the hero visual is captioned "a rendering … not a live session";
- the product demo is a fixed illustration with a per-step **Implemented /
  Planned** pill and a footer saying no model runs on the page;
- agent panels say "not yet executable" and name the phase;
- the dashboard's pipeline view refuses to draw when there is no session,
  because an empty chart would be indistinguishable from zero data;
- the command palette contains no "ask AI" entry, because that capability does
  not exist.

## Alternatives considered

- **Stay with the blue accent and restyle surfaces only.** Rejected: the brief
  asked for a recognisable identity, and a palette swap alone does not produce
  one.
- **Gradients and glass as the primary language.** Rejected as the 2024-25 AI
  SaaS cliché. Glass survives in exactly one place (`Card surface="glass"`,
  for overlays above content) and gradients in two (the hero veil, the closing
  CTA glow).
- **React-Three-Fiber.** Rejected: requires React 19. Deferred rather than
  forcing a runtime upgrade inside a visual-only task.
- **GSAP in addition to framer-motion.** Rejected: two animation engines for
  one page's needs is unjustifiable weight; nothing here needs a timeline
  sequencer.
- **A separate marketing site / framework.** Rejected: one codebase and one
  design system keeps the public page and the product from drifting apart, and
  the marketing shell is ~200 lines.

## Consequences

- **Positive:** a distinctive, coherent identity across public and product
  surfaces; a single place to change palette, type or motion; contrast and
  reduced-motion are test-enforced rather than aspirational; the heaviest
  asset loads only when needed.
- **Negative:** three new fonts and two new runtime dependencies (~160 kB
  gzipped combined, split into cacheable chunks). Instrument Serif has a
  limited character set, so display type must stay Latin.
- **Unverified:** no browser was available in the build environment, so
  rendering was verified structurally (jsdom + axe + build output) rather than
  visually. See `docs/DESIGN_SYSTEM.md § Verified` for exactly what was and was
  not checked; do not read this ADR as a claim of pixel verification.
