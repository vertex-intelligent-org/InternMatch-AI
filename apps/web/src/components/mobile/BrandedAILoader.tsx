'use client';

import { TargetMark } from './TargetMark';
import { useMobileText } from '@/features/mobile-parity/useMobileText';

export function BrandedAILoader({ size = 28, active = true }: { size?: number; active?: boolean }) {
  const { m } = useMobileText();
  return <span className={`branded-ai-loader ${active ? 'is-active' : ''}`} role="progressbar" aria-label={m('components.aiLoaderA11y')}>
    <span className="loader-rotation"><TargetMark size={size} strokeWidth="2.2" /></span>
  </span>;
}
