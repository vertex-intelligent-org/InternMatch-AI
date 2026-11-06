'use client';

import { useEffect, useRef } from 'react';
import { TargetMark } from './TargetMark';
import { useReducedMotion } from './useReducedMotion';
import { useMobileText } from '@/features/mobile-parity/useMobileText';

export function BrandLogo({ className = '' }: { className?: string }) {
  const icon = useRef<HTMLSpanElement>(null);
  const animation = useRef<Animation | null>(null);
  const reduced = useReducedMotion();
  const { m } = useMobileText();
  useEffect(() => {
    const element = icon.current;
    if (!element || reduced || !element.animate) return;
    animation.current = element.animate([{ transform: 'rotate(0deg)' }, { transform: 'rotate(360deg)' }], { duration: 800, easing: 'cubic-bezier(.215,.61,.355,1)' });
    return () => animation.current?.cancel();
  }, [reduced]);
  return <button className={`mobile-brand ${className}`} type="button" aria-label={m('components.logoA11y')} onClick={() => {
    animation.current?.cancel();
    if (!reduced && icon.current?.animate) animation.current = icon.current.animate([{ transform: 'rotate(0deg)' }, { transform: 'rotate(360deg)' }], { duration: 750, easing: 'cubic-bezier(.215,.61,.355,1)' });
  }}>
    <span dir="ltr">InternMatch</span><span className="brand-target" ref={icon}><TargetMark /></span>
  </button>;
}
