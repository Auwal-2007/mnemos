import { useEffect, useRef, useState } from 'react';
import { useMotionPreference } from '../../lib/motion';

/**
 * Counts a number up to its real value on mount.
 *
 * This is presentation only: the destination is always the number the API
 * returned, and the first rendered frame already reports the final value to
 * assistive technology via the surrounding element. Under reduced motion it
 * renders the final value immediately with no intermediate frames, so nothing
 * ever displays a number that is not true.
 */
export function useCountUp(target: number, durationMs = 620): number {
  const reduced = useMotionPreference();
  const [value, setValue] = useState(reduced ? target : 0);
  const previous = useRef(0);

  useEffect(() => {
    if (reduced) {
      setValue(target);
      previous.current = target;
      return undefined;
    }

    const from = previous.current;
    const delta = target - from;
    if (delta === 0) {
      setValue(target);
      return undefined;
    }

    let frame = 0;
    const start = performance.now();

    const tick = (now: number): void => {
      const progress = Math.min((now - start) / durationMs, 1);
      // Ease-out cubic: fast start, settled finish.
      const eased = 1 - (1 - progress) ** 3;
      setValue(Math.round(from + delta * eased));
      if (progress < 1) {
        frame = requestAnimationFrame(tick);
      } else {
        previous.current = target;
      }
    };

    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [target, durationMs, reduced]);

  return value;
}
