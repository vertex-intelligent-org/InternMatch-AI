'use client';

import { useEffect, useState } from 'react';
import { BowArrowBrand } from './BowArrowBrand';
import { useBrandText } from '@/features/brand/useBrandText';

export function BrandedWait({ fullPage = false, delay = 250 }: { fullPage?: boolean; delay?: number }) {
  const [visible, setVisible] = useState(delay === 0);
  const b = useBrandText();
  useEffect(() => {
    const timer = setTimeout(() => setVisible(true), delay);
    return () => clearTimeout(timer);
  }, [delay]);
  return <div className={`branded-wait ${fullPage ? 'full-page' : ''}`} role="status" aria-live="polite" aria-atomic="true">
    {visible ? <div className="wait-content"><BowArrowBrand /><p>{b.loading}</p><span className="wait-caption">{b.loadingHint}</span></div> : <span className="visually-hidden">{b.loading}</span>}
  </div>;
}
