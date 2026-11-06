'use client';

import { useEffect, useRef, type HTMLAttributes } from 'react';
import { mobileTokens } from '@/theme/mobile-tokens';
import { springSamples } from './spring';
import { useReducedMotion } from './useReducedMotion';

export function Reveal({ children, delay = 0, className = '', variant = 'reveal', ...rest }: HTMLAttributes<HTMLDivElement> & { delay?: number; variant?: 'reveal' | 'hero' }) {
  const ref = useRef<HTMLDivElement>(null);
  const reduced = useReducedMotion();
  useEffect(() => {
    const element = ref.current;
    if (!element || reduced || !element.animate) return;
    const hero = variant === 'hero';
    const opacity = element.animate([{ opacity: 0 }, { opacity: 1 }], { duration: mobileTokens.motion.durations.reveal + (hero ? 100 : 0), delay, easing: 'ease-out', fill: 'backwards' });
    const values = hero ? springSamples(mobileTokens.motion.scales.orbSettleStart, 1, mobileTokens.motion.spring.hero) : springSamples(8, 0, mobileTokens.motion.spring.reveal);
    const position = element.animate(values.map(value => ({ transform: hero ? `scale(${value})` : `translateY(${value}px)` })), { duration: 800, delay, fill: 'backwards' });
    return () => { opacity.cancel(); position.cancel(); };
  }, [delay, reduced, variant]);
  // Never hide server-rendered content before JavaScript initializes.
  return <div ref={ref} className={`mobile-reveal ${className}`} {...rest}>{children}</div>;
}
