'use client';
import type { ReactNode } from 'react';
import { BrandedWait } from './BrandedWait';

// The caller owns the actual request. There is no minimum duration or artificial delay.
export function PendingRegion({ pending, children, label }: { pending: boolean; children: ReactNode; label: string }) {
  return <section className="pending-region" aria-label={label} aria-busy={pending}>
    {pending ? <BrandedWait /> : children}
  </section>;
}
