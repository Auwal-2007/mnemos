# ADR-0009 — Frontend styling approach

**Status:** Accepted
**Date:** 2026-11-15

## Context

MNEMOS needs a premium, restrained visual identity with light and dark
themes, responsive behaviour at 360–1440 px, and accessibility guarantees.
The Phase 0 stack is React 18 + Vite 5 + TypeScript.

## Decision

1. **Design tokens as CSS custom properties** (`styles/tokens.css`), with a
   TypeScript mirror (`styles/tokens.ts`) for values JS must know
   (breakpoints, motion). Themes swap by `[data-theme]` on `<html>`.
2. **Plain per-component stylesheets** with a strict BEM-ish convention
   (`block__element`, `block--modifier`). Class names are strings in JSX.
3. **No CSS Modules, no CSS-in-JS, no utility framework.**
4. **Breakpoints**: 360 / 390 / 768 / 1024 / 1440. Mobile-first base styles;
   desktop enhancements in `min-width` queries where practical.
5. **Motion** is restricted to short, purposeful transitions
   (120–260 ms, one easing curve) and is fully disabled under
   `prefers-reduced-motion`.
6. **Accessibility**: semantic landmarks, visible focus rings via
   `:focus-visible`, skip link, 44 px minimum touch targets on mobile, and
   contrast-checked colour pairs.

## Alternatives considered

- **CSS Modules** — scoping is nice, but hashed class names hurt debuggability
  and the codebase is small enough that a naming convention suffices.
  (Attempted first; reverted for this reason.)
- **Tailwind** — fast for prototyping, but pushes long class strings into JSX
  and makes a token-driven, themeable identity harder to audit.
- **styled-components / Emotion** — runtime cost, extra dependency, and
  no benefit for a token-based static theme.
- **Sass** — nesting and variables duplicate what custom properties already
  provide at runtime (needed for theme switching).

## Consequences

- Theme switching is instant with no re-render of styled components.
- Class-name collisions are possible in principle; the BEM convention and
  one-stylesheet-per-component keep them contained.
- Tokens are the single source of visual truth; changing a colour happens in
  one file.
