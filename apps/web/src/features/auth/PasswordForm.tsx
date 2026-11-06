'use client';
import Link from 'next/link';
import { useRef, useState, type FormEvent } from 'react';
import { AuthSurface } from './AuthSurface';
import { authRequest, followAuthResult } from './request';
import { useAuthText } from './useAuthText';
import { useMobileText } from '@/features/mobile-parity/useMobileText';
import { PrimaryButton } from '@/components/mobile/PrimaryButton';
export function PasswordForm({ reset, enabled }: { reset: boolean; enabled: boolean }) {
  const t = useAuthText(); const { m } = useMobileText(); const [busy, setBusy] = useState(false); const [message, setMessage] = useState(''); const inFlight = useRef(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (inFlight.current || !enabled) return;
    const data = new FormData(event.currentTarget); const password = String(data.get('password') ?? '');
    if (reset && (password.length < 6 || password !== data.get('confirmation'))) { setMessage(t.passwordMismatch); return; }
    inFlight.current = true; setBusy(true); setMessage('');
    try { const result = await authRequest(reset ? 'reset' : 'recover', reset ? { password } : { email: data.get('email') }); if (!followAuthResult(result)) setMessage(result.code && Object.hasOwn(t, result.code) ? t[result.code] : t.unavailable); }
    finally { inFlight.current = false; setBusy(false); }
  }
  return <AuthSurface title={m('auth.forgotPasswordTitle')} subtitle={reset ? t.newPasswordHelp : m('auth.forgotPasswordMessage')}>
    {!enabled ? <p className="auth-config-note">{t.emailSetup}</p> : null}
    <form onSubmit={submit}>
      {reset ? <><div className="native-auth-field"><label htmlFor="new-password">{t.newPassword}</label><div className="auth-input-wrap"><input id="new-password" name="password" type="password" autoComplete="new-password" minLength={6} maxLength={1024} required disabled={!enabled || busy} /></div></div><div className="native-auth-field"><label htmlFor="confirm-password">{t.confirmPassword}</label><div className="auth-input-wrap"><input id="confirm-password" name="confirmation" type="password" autoComplete="new-password" minLength={6} maxLength={1024} required disabled={!enabled || busy} /></div></div></> : <div className="native-auth-field"><label htmlFor="recovery-email">{m('auth.email')}</label><div className="auth-input-wrap"><input id="recovery-email" name="email" type="email" dir="ltr" autoComplete="email" maxLength={254} required disabled={!enabled || busy} /></div></div>}
      <PrimaryButton className="auth-submit" type="submit" tone="accent" loading={busy} disabled={!enabled}>{reset ? t.savePassword : t.sendReset}</PrimaryButton>
    </form><p className="auth-message" role="status">{message}</p><Link className="text-link" href="/sign-in">{m('auth.signIn')}</Link>
  </AuthSurface>;
}
