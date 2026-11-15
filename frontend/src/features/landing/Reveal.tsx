import type { ReactNode } from 'react';
import { motion } from 'framer-motion';
import { revealVariants, revealViewport, staggerVariants, useMotionPreference } from '../../lib/motion';

interface RevealProps {
  children: ReactNode;
  /** Wraps the content in a stagger container instead of a single element. */
  stagger?: boolean;
  className?: string;
  delay?: number;
}

/**
 * Scroll reveal wrapper.
 *
 * Content animates in once, slightly before it is centred, and never again —
 * re-animating on every scroll pass is the behaviour that makes a page feel
 * jumpy. Under reduced motion the variants collapse to opacity 1 with no
 * transform, so nothing shifts at all.
 */
export function Reveal({ children, stagger = false, className, delay = 0 }: RevealProps): JSX.Element {
  const reduced = useMotionPreference();
  const variants = stagger ? staggerVariants(reduced) : revealVariants(reduced);

  return (
    <motion.div
      className={className}
      variants={variants}
      initial="hidden"
      whileInView="visible"
      viewport={revealViewport}
      transition={delay && !reduced ? { delay } : undefined}
    >
      {children}
    </motion.div>
  );
}

interface RevealItemProps {
  children: ReactNode;
  className?: string;
}

/** A child of a `stagger` Reveal. Carries the same variant names. */
export function RevealItem({ children, className }: RevealItemProps): JSX.Element {
  const reduced = useMotionPreference();
  return (
    <motion.div className={className} variants={revealVariants(reduced)}>
      {children}
    </motion.div>
  );
}
