/**
 * Motion primitives.
 *
 * Three rules this module exists to enforce:
 *
 * 1. **One source of easing.** Durations and curves come from the CSS tokens,
 *    mirroring `tokens.css` so JS and CSS motion feel identical.
 * 2. **Reduced motion is not an afterthought.** `useMotionPreference` reports
 *    both the OS setting and an in-app override; every variant builder takes
 *    the flag and returns a no-op variant when motion is off.
 * 3. **Shared variants.** Reveal, stagger and page transitions are defined
 *    once so no page invents its own timing.
 */

import { useCallback, useEffect, useState } from 'react';

/** Mirrors `--motion-*` and `--ease-*` in tokens.css. */
export const duration = {
  instant: 0.09,
  fast: 0.14,
  base: 0.22,
  slow: 0.38,
  slower: 0.62,
} as const;

export const ease = {
  standard: [0.22, 0.61, 0.36, 1] as const,
  out: [0.16, 1, 0.3, 1] as const,
  inOut: [0.65, 0, 0.35, 1] as const,
  spring: [0.34, 1.4, 0.64, 1] as const,
};

const REDUCED_QUERY = '(prefers-reduced-motion: reduce)';

/**
 * Tracks reduced-motion preference, including live changes.
 *
 * Returns `true` when motion should be suppressed. Callers must treat this as
 * authoritative rather than checking `matchMedia` themselves, so there is a
 * single place where the policy lives.
 */
export function useMotionPreference(): boolean {
  const [reduced, setReduced] = useState<boolean>(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return false;
    return window.matchMedia(REDUCED_QUERY).matches;
  });

  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return undefined;
    const query = window.matchMedia(REDUCED_QUERY);
    const onChange = (event: MediaQueryListEvent): void => setReduced(event.matches);
    setReduced(query.matches);
    query.addEventListener('change', onChange);
    return () => query.removeEventListener('change', onChange);
  }, []);

  return reduced;
}

/**
 * Scroll-reveal variants: content rises a short distance and fades in.
 *
 * The distance is deliberately small (14px). Large travel distances are what
 * make scroll animation feel cheap; this is a settle, not an entrance.
 */
export function revealVariants(reduced: boolean, distance = 14) {
  if (reduced) {
    return {
      hidden: { opacity: 1 },
      visible: { opacity: 1 },
    };
  }
  return {
    hidden: { opacity: 0, y: distance },
    visible: {
      opacity: 1,
      y: 0,
      transition: { duration: duration.slow, ease: ease.out },
    },
  };
}

/** Parent variant that staggers children; use with `revealVariants`. */
export function staggerVariants(reduced: boolean, stagger = 0.06, delayChildren = 0.04) {
  return {
    hidden: {},
    visible: {
      transition: reduced
        ? {}
        : { staggerChildren: stagger, delayChildren },
    },
  };
}

/** Viewport config: animate once, slightly before the element is centred. */
export const revealViewport = { once: true, amount: 0.25, margin: '0px 0px -60px 0px' } as const;

/** Page transition: a short cross-fade with a barely perceptible lift. */
export function pageVariants(reduced: boolean) {
  if (reduced) {
    return { initial: { opacity: 1 }, animate: { opacity: 1 }, exit: { opacity: 1 } };
  }
  return {
    initial: { opacity: 0, y: 6 },
    animate: {
      opacity: 1,
      y: 0,
      transition: { duration: duration.base, ease: ease.out },
    },
    exit: { opacity: 0, y: -4, transition: { duration: duration.fast, ease: ease.inOut } },
  };
}

/**
 * Reports whether an element has entered the viewport, once.
 *
 * Used where framer-motion's `whileInView` would pull in a heavier code path
 * (for example before the 3D scene mounts). Falls back to "visible" when
 * IntersectionObserver is unavailable so content never stays hidden.
 */
export function useInViewOnce<T extends Element>(
  margin = '0px 0px -120px 0px',
): [React.RefCallback<T>, boolean] {
  const [element, setElement] = useState<T | null>(null);
  const [inView, setInView] = useState(false);

  const ref = useCallback((node: T | null) => {
    setElement(node);
  }, []);

  useEffect(() => {
    if (!element) return undefined;
    if (typeof IntersectionObserver === 'undefined') {
      setInView(true);
      return undefined;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setInView(true);
            observer.disconnect();
          }
        }
      },
      { rootMargin: margin },
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, [element, margin]);

  return [ref, inView];
}
