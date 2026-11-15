/**
 * Colour contrast verification for both themes.
 *
 * jsdom cannot compute rendered contrast, so the ratios are calculated
 * directly from the token values using the WCAG 2.1 relative-luminance
 * formula. Body text is held to 7:1 (AAA) and UI/muted text to 4.5:1.
 */

import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

type Theme = 'dark' | 'light';

const css = readFileSync(resolve(__dirname, 'tokens.css'), 'utf8');

/** Extract a custom property's value for a given theme block. */
function token(theme: Theme, name: string): string {
  const startMarker =
    theme === 'dark' ? ":root,\n[data-theme='dark'] {" : "[data-theme='light'] {";
  const start = css.indexOf(startMarker);
  if (start === -1) throw new Error(`Theme block not found for ${theme}`);
  const end = css.indexOf('}', start);
  const block = css.slice(start, end);
  const match = new RegExp(`${name}:\\s*([^;]+);`).exec(block);
  if (!match) throw new Error(`Token ${name} not found in ${theme}`);
  return match[1].trim();
}

function toRgb(value: string): [number, number, number] {
  const hex = value.startsWith('#') ? value.slice(1) : value;
  const full =
    hex.length === 3
      ? hex
          .split('')
          .map((char) => char + char)
          .join('')
      : hex;
  return [
    parseInt(full.slice(0, 2), 16),
    parseInt(full.slice(2, 4), 16),
    parseInt(full.slice(4, 6), 16),
  ];
}

function relativeLuminance([r, g, b]: [number, number, number]): number {
  const channel = (value: number): number => {
    const srgb = value / 255;
    return srgb <= 0.03928 ? srgb / 12.92 : ((srgb + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

function contrast(foreground: string, background: string): number {
  const l1 = relativeLuminance(toRgb(foreground));
  const l2 = relativeLuminance(toRgb(background));
  const [lighter, darker] = l1 > l2 ? [l1, l2] : [l2, l1];
  return (lighter + 0.05) / (darker + 0.05);
}

/** Colour pairs that actually appear together in the UI. */
const PAIRS: { fg: string; bg: string; minimum: number; label: string }[] = [
  { fg: '--text-primary', bg: '--bg-canvas', minimum: 7, label: 'primary text on canvas' },
  { fg: '--text-primary', bg: '--bg-surface', minimum: 7, label: 'primary text on surface' },
  { fg: '--text-primary', bg: '--bg-elevated', minimum: 7, label: 'primary text on elevated' },
  { fg: '--text-secondary', bg: '--bg-surface', minimum: 4.5, label: 'secondary text on surface' },
  { fg: '--text-secondary', bg: '--bg-canvas', minimum: 4.5, label: 'secondary text on canvas' },
  { fg: '--text-tertiary', bg: '--bg-surface', minimum: 3, label: 'tertiary text on surface' },
  { fg: '--text-tertiary', bg: '--bg-inset', minimum: 3, label: 'tertiary text on inset' },
  { fg: '--text-primary', bg: '--bg-active', minimum: 7, label: 'active nav text' },
  { fg: '--text-primary', bg: '--bg-hover', minimum: 7, label: 'hover nav text' },
];

describe.each<Theme>(['dark', 'light'])('%s theme contrast', (theme) => {
  for (const pair of PAIRS) {
    it(`${pair.label} meets ${pair.minimum}:1`, () => {
      const ratio = contrast(token(theme, pair.fg), token(theme, pair.bg));
      expect(
        ratio,
        `${pair.fg} (${token(theme, pair.fg)}) on ${pair.bg} (${token(theme, pair.bg)}) = ${ratio.toFixed(2)}:1`,
      ).toBeGreaterThanOrEqual(pair.minimum);
    });
  }

  it('accent text is legible on surfaces', () => {
    const ratio = contrast(token(theme, '--accent-text'), token(theme, '--bg-surface'));
    expect(ratio).toBeGreaterThanOrEqual(4.5);
  });

  it('danger text is legible on surfaces', () => {
    const ratio = contrast(token(theme, '--danger'), token(theme, '--bg-surface'));
    expect(ratio).toBeGreaterThanOrEqual(4.5);
  });

  it('primary button text is legible on the accent fill', () => {
    expect(
      contrast(token(theme, '--text-on-accent'), token(theme, '--accent-fill')),
    ).toBeGreaterThanOrEqual(4.5);
  });

  it('primary button hover state stays legible', () => {
    expect(
      contrast(token(theme, '--text-on-accent'), token(theme, '--accent-fill-hover')),
    ).toBeGreaterThanOrEqual(4.5);
  });

  it('accent fill is distinguishable from the canvas', () => {
    expect(contrast(token(theme, '--accent-fill'), token(theme, '--bg-canvas'))).toBeGreaterThanOrEqual(
      3,
    );
  });
});
