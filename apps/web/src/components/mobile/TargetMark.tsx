import type { SVGProps } from 'react';

// Identical 32x32 circle/prong geometry to InternMatchLogo and BrandedAILoader.
export function TargetMark({ size = 22, ...props }: SVGProps<SVGSVGElement> & { size?: number }) {
  return <svg width={size} height={size} viewBox="0 0 32 32" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" aria-hidden="true" focusable="false" {...props}>
    <circle cx="16" cy="16" r="8.5" />
    <path d="M16 2v3.5M16 26.5V30M2 16h3.5M26.5 16H30" />
  </svg>;
}
