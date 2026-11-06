'use client';

import { useEffect, useRef, type ButtonHTMLAttributes } from 'react';
import { mobileTokens } from '@/theme/mobile-tokens';
import { springSamples } from './spring';
import { useReducedMotion } from './useReducedMotion';

type Props = ButtonHTMLAttributes<HTMLButtonElement> & { scaleTo?: number };
export function PressableScale({ scaleTo = mobileTokens.motion.scales.buttonPressed, children, onPointerDown, onPointerUp, onPointerCancel, onPointerLeave, onKeyDown, onKeyUp, onBlur, ...props }: Props) {
  const ref = useRef<HTMLButtonElement>(null);
  const motion = useRef<Animation | null>(null);
  const currentScale = useRef(1);
  const reduced = useReducedMotion();
  const animate = (pressed: boolean) => {
    const element = ref.current;
    if (!element || props.disabled) return;
    motion.current?.cancel();
    const target = pressed ? scaleTo : 1;
    if (reduced || !element.animate) { currentScale.current = 1; return; }
    const start = currentScale.current;
    const frames = springSamples(start, target, mobileTokens.motion.spring.press).map(value => ({ transform: `scale(${value})`, opacity: pressed ? mobileTokens.motion.opacities.pressed : 1 }));
    currentScale.current = target;
    motion.current = element.animate(frames, { duration: 800, fill: 'forwards' });
  };
  useEffect(() => { if (reduced) motion.current?.cancel(); return () => motion.current?.cancel(); }, [reduced]);
  return <button ref={ref} type="button" {...props}
    onPointerDown={e => { if (e.button === 0) animate(true); onPointerDown?.(e); }}
    onPointerUp={e => { animate(false); onPointerUp?.(e); }}
    onPointerCancel={e => { animate(false); onPointerCancel?.(e); }}
    onPointerLeave={e => { animate(false); onPointerLeave?.(e); }}
    onKeyDown={e => { if ((e.key === ' ' || e.key === 'Enter') && !e.repeat) animate(true); onKeyDown?.(e); }}
    onKeyUp={e => { animate(false); onKeyUp?.(e); }}
    onBlur={e => { animate(false); onBlur?.(e); }}>{children}</button>;
}
