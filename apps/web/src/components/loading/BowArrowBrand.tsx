'use client';

import { useEffect, useRef } from 'react';
import { useReducedMotion } from '@/components/mobile/useReducedMotion';
import { bowFrame, bowGeometry } from './bow-geometry';

export function BowArrowBrand({ animate = true }: { animate?: boolean }) {
  const svg = useRef<SVGSVGElement>(null);
  const bow = useRef<SVGGElement>(null);
  const arrow = useRef<SVGGElement>(null);
  const upper = useRef<SVGLineElement>(null);
  const lower = useRef<SVGLineElement>(null);
  const impact = useRef<SVGGElement>(null);
  const reduced = useReducedMotion();
  useEffect(() => {
    if (reduced || !animate) { svg.current?.setAttribute('data-phase', 'static'); impact.current?.classList.remove('has-impact'); return; }
    const bowElement = bow.current;
    const arrowElement = arrow.current;
    let frameId = 0; let start: number | null = null;
    const tick = (time: number) => {
      if (start === null) start = time;
      const value = bowFrame(time - start);
      svg.current?.setAttribute('data-phase', value.phase);
      bow.current?.setAttribute('transform', `translate(${bowGeometry.bowX} ${bowGeometry.bowY}) rotate(${value.angle})`);
      bow.current?.setAttribute('opacity', String(value.bowOpacity));
      upper.current?.setAttribute('x2', String(value.nock));
      lower.current?.setAttribute('x2', String(value.nock));
      arrow.current?.setAttribute('transform', `translate(${value.x} ${value.y}) rotate(${value.angle})`);
      arrow.current?.setAttribute('opacity', String(value.arrowOpacity));
      if (value.impact) impact.current?.classList.add('has-impact');
      if (!value.finished) frameId = requestAnimationFrame(tick);
    };
    frameId = requestAnimationFrame(tick);
    return () => { cancelAnimationFrame(frameId); bowElement?.setAttribute('opacity', '0'); arrowElement?.setAttribute('opacity', '0'); };
  }, [reduced, animate]);
  return <svg ref={svg} className="bow-brand-scene" viewBox="0 -24 320 240" aria-hidden="true" focusable="false" data-phase="static">
    <text className="bow-brand-wordmark" x="229" y="52" textAnchor="end" direction="ltr">InternMatch AI</text>
    <g transform={`translate(${bowGeometry.targetX} ${bowGeometry.targetY})`}>
      <g ref={impact} className="bow-target-impact"><g className="bow-target-wheel" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round">
        <circle r="8.5" /><path d="M0-14v3.5M0 10.5V14M-14 0h3.5M10.5 0H14" />
      </g></g>
    </g>
    <g ref={bow} opacity="0" fill="none" stroke="currentColor" strokeLinecap="round">
      <line ref={upper} x1="-8" y1="-42" x2="-7" y2="0" strokeWidth="1.4" />
      <line ref={lower} x1="-8" y1="42" x2="-7" y2="0" strokeWidth="1.4" />
      <path d="M -8 -42 Q 18 0 -8 42" strokeWidth="2.6" />
    </g>
    <g ref={arrow} opacity="0" stroke="currentColor" strokeLinecap="round">
      <line x1="-50" y1="0" x2="0" y2="0" strokeWidth="2" />
      <polygon points="0,0 -10,-3.5 -8,0 -10,3.5" fill="currentColor" stroke="none" />
      <path d="M-50-4 -44 0 M-50 4 -44 0 M-44-4 -38 0 M-44 4 -38 0" strokeWidth="1.5" fill="none" />
    </g>
  </svg>;
}
