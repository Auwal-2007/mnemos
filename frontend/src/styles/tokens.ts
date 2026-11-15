/**
 * Design tokens — the single source of visual truth for MNEMOS.
 *
 * Direction: sophisticated productivity software. Minimal, premium,
 * restrained colour, strong typography, generous but purposeful spacing.
 * Tokens are defined as CSS custom properties in `styles/tokens.css`;
 * this module mirrors the values needed by TypeScript/JS logic.
 */

export const breakpoints = {
  mobile: 360,
  mobileWide: 390,
  tablet: 768,
  tabletWide: 1024,
  desktop: 1440,
} as const;

export type BreakpointName = keyof typeof breakpoints;

/** Media query helper used by components that need JS-side breakpoint logic. */
export function minWidth(name: BreakpointName): string {
  return `(min-width: ${breakpoints[name]}px)`;
}

export const motion = {
  fast: '120ms',
  base: '180ms',
  slow: '260ms',
  easing: 'cubic-bezier(0.2, 0, 0, 1)',
} as const;

export const radius = {
  sm: '6px',
  md: '10px',
  lg: '14px',
  pill: '999px',
} as const;

export const space = {
  xxs: '4px',
  xs: '8px',
  sm: '12px',
  md: '16px',
  lg: '24px',
  xl: '32px',
  xxl: '48px',
  xxxl: '64px',
} as const;
