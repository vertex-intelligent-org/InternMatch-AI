'use client';
import Link from 'next/link';
import { useEffect, useRef, useState } from 'react';
import { BrandLogo } from '@/components/mobile/BrandLogo';
import { PreferenceControls } from '@/components/PreferenceControls';
import { BowArrowBrand } from '@/components/loading/BowArrowBrand';
import { PendingRegion } from '@/components/loading/PendingRegion';
import { useBrandText } from './useBrandText';

export function LoadingReview() {
  const b = useBrandText();
  const [pending, setPending] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => { if (timer.current !== null) clearTimeout(timer.current); }, []);
  function simulate(duration: number) {
    if (timer.current !== null) clearTimeout(timer.current);
    setPending(true);
    timer.current = setTimeout(() => { setPending(false); timer.current = null; }, duration);
  }
  return <main className="loading-review" id="main-content">
    <header className="parity-header"><BrandLogo /><PreferenceControls /></header>
    <Link className="text-link" href="/foundation">{b.back}</Link>
    <h1>{b.loadingTitle}</h1><p className="muted">{b.loadingDescription}</p>
    <div className="loading-demo-actions"><button type="button" className="button primary" disabled={pending} onClick={() => simulate(2000)}>{b.simulateTwo}</button><button type="button" className="button secondary" disabled={pending} onClick={() => simulate(5000)}>{b.simulateFive}</button></div>
    <PendingRegion pending={pending} label={b.loadingTitle}><div className="loading-ready"><BowArrowBrand animate={false} /><p>{b.ready}</p></div></PendingRegion>
    <p className="small muted">{b.demoOnly}</p>
  </main>;
}
