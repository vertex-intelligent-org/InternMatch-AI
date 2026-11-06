'use client';

import type { ButtonHTMLAttributes } from 'react';
import { PressableScale } from './PressableScale';

export function PrimaryButton({ children, loading = false, outline = false, tone = 'default', className = '', disabled, ...rest }: ButtonHTMLAttributes<HTMLButtonElement> & { loading?: boolean; outline?: boolean; tone?: 'default' | 'accent' }) {
  return <PressableScale className={`native-primary ${outline ? 'outline' : ''} tone-${tone} ${className}`} disabled={disabled || loading} aria-busy={loading || undefined} {...rest}>
    {loading ? <span className="dotted-spinner" aria-hidden="true">{[1, .88, .76, .64, .52, .40, .28, .18].map((opacity, i) => <span key={i} style={{ transform: `rotate(${i * 45}deg)` }}><i style={{ opacity }} /></span>)}</span> : null}
    <span>{children}</span>
  </PressableScale>;
}
