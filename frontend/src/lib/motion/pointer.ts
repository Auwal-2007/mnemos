/**
 * Pointer-aware interaction primitives.
 *
 * Every effect here is *additive*: it writes CSS custom properties or
 * transforms only. Nothing captures pointer events, nothing blocks selection,
 * nothing moves hit targets. A user who never moves their mouse sees the
 * fully styled component; a user who does sees it respond.
 *
 * All of them read `useMotionPreference()` and go inert when motion is
 * reduced, so cursor effects never fight a vestibular setting.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { useMotionPreference } from './index';

interface Pointer {
  /** Position within the element, in CSS pixels. */
  x: number;
  y: number;
  /** Position within the element, normalised to 0..1. */
  nx: number;
  ny: number;
}

const ORIGIN: Pointer = { x: 0, y: 0, nx: 0.5, ny: 0.5 };

/**
 * Tracks the pointer inside an element and exposes CSS custom properties
 * `--pointer-x`, `--pointer-y`, `--pointer-nx`, `--pointer-ny`.
 *
 * The values are written directly to the node's style (not React state) on
 * pointer move, so a moving cursor never triggers a render.
 */
export function useSpotlight<T extends HTMLElement>(): {
  ref: React.RefObject<T>;
  isActive: boolean;
} {
  const ref = useRef<T>(null);
  const [isActive, setIsActive] = useState(false);
  const reduced = useMotionPreference();

  useEffect(() => {
    const node = ref.current;
    if (!node || reduced) return undefined;

    let frame = 0;
    let pending: Pointer | null = null;

    const paint = (): void => {
      frame = 0;
      if (!pending) return;
      node.style.setProperty('--pointer-x', `${pending.x}px`);
      node.style.setProperty('--pointer-y', `${pending.y}px`);
      node.style.setProperty('--pointer-nx', pending.nx.toFixed(4));
      node.style.setProperty('--pointer-ny', pending.ny.toFixed(4));
    };

    const onMove = (event: PointerEvent): void => {
      const rect = node.getBoundingClientRect();
      const x = event.clientX - rect.left;
      const y = event.clientY - rect.top;
      pending = {
        x,
        y,
        nx: rect.width ? x / rect.width : 0.5,
        ny: rect.height ? y / rect.height : 0.5,
      };
      if (!frame) frame = requestAnimationFrame(paint);
    };

    const onEnter = (): void => setIsActive(true);
    const onLeave = (): void => {
      setIsActive(false);
      if (frame) {
        cancelAnimationFrame(frame);
        frame = 0;
      }
    };

    node.addEventListener('pointermove', onMove, { passive: true });
    node.addEventListener('pointerenter', onEnter);
    node.addEventListener('pointerleave', onLeave);
    return () => {
      node.removeEventListener('pointermove', onMove);
      node.removeEventListener('pointerenter', onEnter);
      node.removeEventListener('pointerleave', onLeave);
      if (frame) cancelAnimationFrame(frame);
    };
  }, [reduced]);

  return { ref, isActive: isActive && !reduced };
}

/**
 * Perspective tilt that follows the cursor across a card.
 *
 * Rotation is capped at `maxDeg` (default 4°) because anything more reads as
 * a toy. Children can use `--tilt-shift` for a parallax offset.
 */
export function useTilt<T extends HTMLElement>(maxDeg = 4): {
  ref: React.RefObject<T>;
  isActive: boolean;
} {
  const ref = useRef<T>(null);
  const [isActive, setIsActive] = useState(false);
  const reduced = useMotionPreference();

  useEffect(() => {
    const node = ref.current;
    if (!node || reduced) return undefined;

    let frame = 0;
    let target: { rx: number; ry: number; sx: number; sy: number } | null = null;

    const paint = (): void => {
      frame = 0;
      if (!target) return;
      node.style.transform = `perspective(1100px) rotateX(${target.rx.toFixed(
        2,
      )}deg) rotateY(${target.ry.toFixed(2)}deg)`;
      node.style.setProperty('--tilt-shift-x', `${(target.sx * 10).toFixed(1)}px`);
      node.style.setProperty('--tilt-shift-y', `${(target.sy * 10).toFixed(1)}px`);
    };

    const onMove = (event: PointerEvent): void => {
      const rect = node.getBoundingClientRect();
      const nx = (event.clientX - rect.left) / (rect.width || 1);
      const ny = (event.clientY - rect.top) / (rect.height || 1);
      target = {
        rx: (0.5 - ny) * 2 * maxDeg,
        ry: (nx - 0.5) * 2 * maxDeg,
        sx: nx - 0.5,
        sy: ny - 0.5,
      };
      if (!frame) frame = requestAnimationFrame(paint);
    };

    const reset = (): void => {
      setIsActive(false);
      if (frame) {
        cancelAnimationFrame(frame);
        frame = 0;
      }
      node.style.transform = '';
      node.style.removeProperty('--tilt-shift-x');
      node.style.removeProperty('--tilt-shift-y');
    };

    const onEnter = (): void => setIsActive(true);

    node.addEventListener('pointermove', onMove, { passive: true });
    node.addEventListener('pointerenter', onEnter);
    node.addEventListener('pointerleave', reset);
    return () => {
      node.removeEventListener('pointermove', onMove);
      node.removeEventListener('pointerenter', onEnter);
      node.removeEventListener('pointerleave', reset);
      if (frame) cancelAnimationFrame(frame);
    };
  }, [maxDeg, reduced]);

  return { ref, isActive: isActive && !reduced };
}

/**
 * Magnetic attraction toward the cursor.
 *
 * The element translates at most `strength` pixels (default 6). Kept tiny on
 * purpose: enough to feel alive under the finger, never enough to move the
 * hit target out from under a click.
 */
export function useMagnetic<T extends HTMLElement>(strength = 6): {
  ref: React.RefObject<T>;
  isActive: boolean;
  handlers: {
    onPointerMove: (event: React.PointerEvent<T>) => void;
    onPointerLeave: () => void;
  };
} {
  const ref = useRef<T>(null);
  const [isActive, setIsActive] = useState(false);
  const reduced = useMotionPreference();

  const onPointerMove = useCallback(
    (event: React.PointerEvent<T>) => {
      const node = ref.current;
      if (!node || reduced) return;
      const rect = node.getBoundingClientRect();
      const dx = (event.clientX - (rect.left + rect.width / 2)) / (rect.width / 2 || 1);
      const dy = (event.clientY - (rect.top + rect.height / 2)) / (rect.height / 2 || 1);
      const clamp = (value: number): number => Math.max(-1, Math.min(1, value));
      node.style.transform = `translate3d(${(clamp(dx) * strength).toFixed(
        2,
      )}px, ${(clamp(dy) * strength).toFixed(2)}px, 0)`;
      setIsActive(true);
    },
    [reduced, strength],
  );

  const onPointerLeave = useCallback(() => {
    const node = ref.current;
    if (node) node.style.transform = '';
    setIsActive(false);
  }, []);

  return { ref, isActive: isActive && !reduced, handlers: { onPointerMove, onPointerLeave } };
}

/**
 * Normalised pointer position for a whole window, for hero-scale effects.
 *
 * Returns `0.5, 0.5` at rest so no consumer has to guard against `null`.
 */
export function useGlobalPointer(): { nx: number; ny: number; active: boolean } {
  const [pointer, setPointer] = useState({ nx: 0.5, ny: 0.5, active: false });
  const reduced = useMotionPreference();

  useEffect(() => {
    if (reduced) return undefined;
    let frame = 0;
    let next: { nx: number; ny: number } | null = null;

    const paint = (): void => {
      frame = 0;
      if (!next) return;
      setPointer({ nx: next.nx, ny: next.ny, active: true });
    };

    const onMove = (event: PointerEvent): void => {
      next = {
        nx: event.clientX / (window.innerWidth || 1),
        ny: event.clientY / (window.innerHeight || 1),
      };
      if (!frame) frame = requestAnimationFrame(paint);
    };

    window.addEventListener('pointermove', onMove, { passive: true });
    return () => {
      window.removeEventListener('pointermove', onMove);
      if (frame) cancelAnimationFrame(frame);
    };
  }, [reduced]);

  return pointer;
}

/** Scroll offset in pixels, throttled to animation frames. */
export function useScrollOffset(): number {
  const [offset, setOffset] = useState(0);

  useEffect(() => {
    let frame = 0;
    let latest = 0;

    const paint = (): void => {
      frame = 0;
      setOffset(latest);
    };

    const onScroll = (): void => {
      latest = window.scrollY;
      if (!frame) frame = requestAnimationFrame(paint);
    };

    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => {
      window.removeEventListener('scroll', onScroll);
      if (frame) cancelAnimationFrame(frame);
    };
  }, []);

  return offset;
}

export { ORIGIN };
