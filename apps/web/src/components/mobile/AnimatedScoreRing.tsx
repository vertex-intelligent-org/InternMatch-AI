'use client';

import { useEffect, useRef } from 'react';
import { mobileTokens } from '@/theme/mobile-tokens';
import { useReducedMotion } from './useReducedMotion';

export function AnimatedScoreRing({ score = 0, size = 140, strokeWidth = 12, label }: { score?: number; size?: number; strokeWidth?: number; label: string }) {
  const circle = useRef<SVGCircleElement>(null);
  const reduced = useReducedMotion();
  const safeScore = Number.isFinite(score) ? Math.max(0, Math.min(100, score)) : 0;
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference * (1 - safeScore / 100);
  useEffect(() => {
    if (!circle.current?.animate || reduced) return;
    const animation = circle.current.animate([{ strokeDashoffset: `${circumference}` }, { strokeDashoffset: `${offset}` }], { duration: mobileTokens.motion.durations.scoreRing, easing: 'cubic-bezier(.215,.61,.355,1)' });
    return () => animation.cancel();
  }, [circumference, offset, reduced]);
  return <div className="mobile-score-ring" style={{ width: size, height: size }} role="progressbar" aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={safeScore}>
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} aria-hidden="true">
      <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="var(--mobile-border-subtle)" strokeWidth={strokeWidth} />
      <circle ref={circle} cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="var(--accent-strong)" strokeWidth={strokeWidth} strokeDasharray={circumference} strokeDashoffset={offset} strokeLinecap="round" transform={`rotate(-90 ${size / 2} ${size / 2})`} />
    </svg><span aria-hidden="true">{safeScore}%</span>
  </div>;
}
