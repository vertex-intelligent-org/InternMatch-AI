'use client';
import Link from 'next/link';
import { BrandLogo } from '@/components/mobile/BrandLogo';
import { PreferenceControls } from '@/components/PreferenceControls';
import { useMobileText } from '@/features/mobile-parity/useMobileText';
import { useAuthText } from './useAuthText';
export function AuthSurface({ children, title, subtitle, mode }: { children: React.ReactNode; title: string; subtitle?: string; mode?: 'signin' | 'signup' }) {
  const { m } = useMobileText(); const t = useAuthText();
  return <main className="native-auth-page real-auth" id="main-content"><div className="native-auth-shell">
    <div className="auth-toolbar"><PreferenceControls /></div><div className="native-auth-brand"><BrandLogo /></div>
    <header className="native-auth-heading"><h1>{title}</h1>{subtitle ? <p>{subtitle}</p> : null}</header>
    <section className="native-auth-panel">
      {mode ? <nav className="native-auth-segments real-auth-tabs" aria-label={t.accountAccess}><Link href="/sign-in" prefetch={false} aria-current={mode === 'signin' ? 'page' : undefined}>{m('auth.segmentedSignIn')}</Link><Link href="/sign-up" prefetch={false} aria-current={mode === 'signup' ? 'page' : undefined}>{m('auth.segmentedSignUp')}</Link></nav> : null}
      {children}
      <div className="native-legal"><a href="https://internmatch.college/privacy">{m('auth.privacyPolicy')}</a><span aria-hidden="true">·</span><a href="https://internmatch.college/terms">{m('auth.termsOfUse')}</a></div>
    </section><Link className="text-link" href="/foundation">{t.interfacePreview}</Link>
  </div></main>;
}
