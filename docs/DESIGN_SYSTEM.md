# MNEMOS Design System

The visual and interaction language of the product. Implementation lives in
`frontend/src/styles/tokens.css` (the single source of visual truth),
`frontend/src/lib/motion/` (motion and pointer primitives) and
`frontend/src/components/ui/` (primitives).

Decisions and their rationale: **ADR-0011**.

---

## 1. Identity

**Warm archive, cold machine.**

MNEMOS is a memory instrument, so the visual language borrows from archives and
scholarly publishing rather than from dashboards: warm charcoal surfaces that
read like rag paper under low light, an editorial serif for voice, and
monospaced type for anything that is literally a stored value.

The identity is carried by restraint. Three hue families, one neutral ramp,
hairline borders, and typography that does the hierarchy work. There is no
fourth accent, because a fourth would make the other three meaningless.

## 2. Colour

Semantics are fixed. Do not use a colour outside its meaning.

| Token family | Hue | Means | Never used for |
|---|---|---|---|
| `--accent*` | teal `#4fc3b4` | live intelligence, active state, links, focus | decoration, primary buttons |
| `--brass*` | brass `#c99a52` | the human record: sources, provenance, revisions, supersession | errors |
| `--danger` | rose `#e87d73` | conflict, failure, destruction | emphasis |
| `--success` | green | completed processing | general positivity |

Surfaces ascend by value, and depth is expressed this way rather than with
shadow, because shadow is invisible on a near-black canvas:

```
--bg-inset      darker than the page    code blocks, inputs, wells
--bg-canvas     the page
--bg-surface    cards and panels
--bg-elevated   popovers, menus, raised cards
--bg-hover / --bg-active                interaction feedback
```

**Contrast is enforced, not aspirational.** `src/styles/contrast.test.ts`
parses `tokens.css` and computes real WCAG 2.1 ratios from the token values for
both themes: body text ≥ 7:1, secondary ≥ 4.5:1, tertiary ≥ 3:1, button label on
its fill ≥ 4.5:1. A palette change that breaks these fails the suite.

### Text on surfaces

- `--text-primary` — headings and body. Warm off-white, not pure white.
- `--text-secondary` — supporting copy.
- `--text-tertiary` — metadata, labels, disabled.
- `--text-inverse` — only on inverted fills.

## 3. Typography

| Role | Family | Where | Notes |
|---|---|---|---|
| Display | Instrument Serif | hero, page titles, section headings, big numbers | 400 only; italic is the emphasis form |
| UI | Inter Variable | all interface text | optical sizing on |
| Data | JetBrains Mono | offsets, hashes, ids, timestamps, status pills, eyebrows | tabular by default |

Self-hosted via `@fontsource`; imported once in `src/styles/fonts.css`.

**Scale** (`--text-*`): 11, 12, 13, 15, 17, 21, 26, 32, plus three fluid
display sizes (`3xl`, `4xl`, `5xl`) that clamp between breakpoints. Never
hardcode a size outside this scale.

**Rules**

- Display type is for titles only. Body copy in serif slows reading.
- Any literal value from the API goes in mono. This is what makes real data
  visually distinguishable from prose.
- Eyebrows and status labels: mono, 11px, `letter-spacing: 0.16em`, uppercase.

## 4. Space, radius, borders

- Spacing is a 4px scale: 1, 2, 3, 4, 5, 6, 8, 10, 12, 16, 20, 24, 32.
- Radii: `xs 4`, `sm 6`, `md 10`, `lg 14`, `xl 20`, `2xl 28`, `pill`.
- Borders are **hairlines**, always. A 2px border only ever means "this edge
  carries state" (a superseded claim, a dangerous action).
- Shadows exist for floating surfaces only; on dark, hairlines do the work.

## 5. Components

### Button (`components/ui/Button`)
Variants: `primary` (paper on charcoal — the single filled action per view),
`secondary` (hairline), `ghost` (text), `quiet` (lowest, for in-row actions),
`danger`. Sizes `sm 32 / md 38 / lg 46`.
Always a real `<button>`; loading state sets `aria-busy` and disables.

### Badge (`components/ui/Badge`)
Tones `neutral | accent | brass | success | warning | danger`; variants
`soft | outline | dot`. Use `dot` for live state — the quietest signal. Only
`accent` dots pulse, because only they mean "a process is running now".

### Card (`components/ui/Card`)
Surfaces: `plain | raised | inset | glass`. **Glass is reserved for content
that genuinely floats above other content** (dialogs, sheets); it is never
decorative, because blurring the layer beneath destroys legibility.
`glow` adds the cursor-tracking highlight and requires `interactive`.

### EmptyState (`components/ui/EmptyState`)
An empty corpus is a normal state, so it gets a drawn piece of geometry (orbit
rings, not a grey box), a plain explanation and the one action that would fill
it. `size="hero"` for full-page emptiness. Never substitute sample data.

### LoadingState (`components/ui/LoadingState`)
`inline` (spinner + status word), `rows` / `panel` (skeletons shaped like the
content that is arriving). **No percentage is ever displayed that did not come
from the backend.**

### Icon (`components/ui/Icon`)
One source (Lucide), one stroke weight (1.5), one grid. Names are
MNEMOS-semantic (`provenance`, `supersede`, `conflict`), so a future icon swap
touches one file.

## 6. Motion

Tokens mirror between CSS and JS (`lib/motion/index.ts`):

| Token | ms | Use |
|---|---|---|
| `instant` | 90 | colour/opacity on hover |
| `fast` | 140 | small state changes |
| `base` | 220 | surface transitions, page fade |
| `slow` | 380 | reveals, panels |
| `slower` | 620 | large layout change |

Easing: `--ease-standard` (general), `--ease-out` (entrances), `--ease-in-out`
(cross-fades), `--ease-spring` (magnetic buttons only).

### Rules

1. **Reveals settle, they do not travel.** 14px rise, `once: true`. Never
   re-animate on a second scroll pass.
2. **Motion explains a change of state.** If nothing changed, nothing moves.
3. **Nothing is slower than it is useful.** Page transitions are 220ms; if a
   transition makes navigation feel slow, it is wrong.
4. **Reduced motion is honoured at the source.** `useMotionPreference()` is the
   single policy point. Variant builders return no-ops, the 3D scene renders a
   single static frame, the demo progress bar unmounts, and `tokens.css`
   neutralises CSS durations globally.

## 7. Pointer interactions

Implemented in `lib/motion/pointer.ts`. All are additive and all go inert
under reduced motion.

| Primitive | Effect | Guard rails |
|---|---|---|
| `useSpotlight` | writes `--pointer-x/y/nx/ny` for a radial highlight | rAF-throttled; writes to `style`, never React state, so a moving cursor causes no render |
| `useTilt` | ≤4° perspective rotation | capped small so it reads as a settle, not a toy |
| `useMagnetic` | ≤6px translation toward the cursor | tiny on purpose — the hit target must never move out from under a click |
| `useGlobalPointer` | normalised window position | returns `0.5, 0.5` at rest so no consumer guards against null |

**Never** put a pointer layer above content without `pointer-events: none`, and
never make a cursor effect the only way to reach a control.

## 8. Layout and responsiveness

Breakpoints: **1280**, **1024** (`--sidebar-width-collapsed` rail), **768**
(mobile top bar replaces the rail), **640**, **480**.

- The public shell and the product shell are different components
  (`MarketingShell`, `AppShell`); a landing page and a work surface have
  different chrome.
- Nav labels are decided by the *effective* rail width, not the stored
  preference, so a 68px rail never renders clipped text.
- The mobile top bar is conditionally **mounted**, not hidden with CSS, so the
  accessibility tree never holds a duplicate set of controls.
- Every multi-column layout collapses to one column by 880-980px; the
  knowledge workspace's three-column layout collapses at 1340 and 900.

## 9. Accessibility

- Semantic landmarks everywhere (`header`/`main`/`nav`/`aside`/`footer`), one
  `h1` per page, headings in order.
- Focus is always visible: a two-ring `--focus-ring` that reads on any surface.
- The command palette is a real combobox/listbox: focus stays in the input,
  the active option is announced with `aria-activedescendant`, and the listbox
  contains only `group` and `option` children (axe enforces this).
- Motion, contrast, and reduced-motion behaviour are test-enforced.
- Dialogs are labelled, Escape closes them from anywhere (document-level, not
  input-level), and the evidence drawer declares `aria-modal="false"` because
  it is deliberately non-blocking on desktop.

## 10. Copy voice

- State facts. "Not implemented yet" beats a plausible-looking empty chart.
- Never imply a capability that does not exist. Every preview surface says what
  it is in its own words.
- Numbers get units and provenance ("read from the database").
- No exclamation marks, no "magic", no anthropomorphising the model.

---

## Verified

This is the honest record of what was checked, and how.

| Check | Method | Result |
|---|---|---|
| TypeScript strict | `tsc --noEmit` | clean |
| Unit + integration | `vitest run` | **119 passed / 11 files** |
| Contrast, both themes | `styles/contrast.test.ts` computes WCAG ratios from tokens | all pairs pass |
| Accessibility | `axe-core` over 10 surfaces incl. landing page, palette, shells | 0 violations |
| Reduced motion | `designSystem.test.tsx` drives `matchMedia` | static frame, no progress bar, no reveal transform |
| Cursor effects | `designSystem.test.tsx` dispatches real pointer events | CSS custom properties written only after movement |
| Keyboard | palette arrow/Enter/Escape, filter, close | asserted |
| Responsive *decisions* | `responsive.test.tsx` + `matchMedia` mocks | rail vs top bar, drawer, palette trigger |
| Production build | `npm run build` | succeeds; entry 151 kB, `three` isolated at 472 kB and absent from first paint |
| Lazy loading | inspected `dist/index.html` chunk references | `three` appears in no entry chunk |

**Not verified — and not claimed:**

- **No visual/pixel verification.** No browser was available in the build
  environment (Playwright's Chromium download is blocked). Layout, spacing and
  colour were reasoned and structurally tested, not seen. Anyone reviewing this
  should load the app and check the hero, the agent diagram and the knowledge
  workspace on a real screen before calling the design signed off.
- **No WebGL execution test.** jsdom has no WebGL, so the 3D scene's fallback
  path is what the tests exercise. The shader and geometry have not been
  rendered anywhere.
- **No real-device testing** for touch, safe-area insets or mobile Safari's
  dynamic viewport units.
