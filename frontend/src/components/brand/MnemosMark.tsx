/**
 * The MNEMOS mark.
 *
 * Draws the product thesis in one glyph: an open ring (the archive, always
 * incomplete and always extending) with three nodes on it — source, evidence,
 * answer — and a line linking them. Rendered as inline SVG so it inherits
 * currentColor, scales crisply, and needs no asset request.
 */

import './MnemosMark.css';

interface MarkProps {
  size?: number;
  /** Animate the ring's traversal. Off by default and always off for reduced motion. */
  animated?: boolean;
  className?: string;
}

export function MnemosMark({ size = 22, animated = false, className }: MarkProps): JSX.Element {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      className={className}
      aria-hidden="true"
      focusable="false"
    >
      <defs>
        <linearGradient id="mnemos-mark-ring" x1="4" y1="2" x2="28" y2="30">
          <stop offset="0%" stopColor="currentColor" stopOpacity="0.95" />
          <stop offset="55%" stopColor="currentColor" stopOpacity="0.42" />
          <stop offset="100%" stopColor="currentColor" stopOpacity="0.12" />
        </linearGradient>
      </defs>

      {/* The open ring: knowledge that is never declared finished. */}
      <path
        d="M27.5 19.2A12 12 0 1 1 20.6 5.1"
        stroke="url(#mnemos-mark-ring)"
        strokeWidth="1.6"
        strokeLinecap="round"
      />

      {/* Inward stroke: memory consolidating toward the centre. */}
      <path
        d="M16 8.5v9M16 17.5l-3.4 3M16 17.5l3.4 3"
        stroke="currentColor"
        strokeOpacity="0.55"
        strokeWidth="1.4"
        strokeLinecap="round"
      />

      {/* The three nodes. */}
      <circle cx="16" cy="6.4" r="2.1" fill="currentColor" />
      <circle cx="10.9" cy="22.4" r="1.6" fill="currentColor" fillOpacity="0.72" />
      <circle cx="21.1" cy="22.4" r="1.6" fill="currentColor" fillOpacity="0.72" />

      {animated && (
        <circle cx="16" cy="6.4" r="2.1" fill="currentColor" className="mark-pulse" />
      )}
    </svg>
  );
}

/** Wordmark lockup used in headers and footers. */
export function MnemosLockup({
  size = 22,
  className,
}: {
  size?: number;
  className?: string;
}): JSX.Element {
  return (
    <span className={`lockup ${className ?? ''}`.trim()}>
      <MnemosMark size={size} />
      <span className="lockup__word">MNEMOS</span>
    </span>
  );
}
