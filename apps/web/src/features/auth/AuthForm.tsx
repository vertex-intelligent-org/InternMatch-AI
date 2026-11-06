'use client';
import Link from 'next/link';
import { useEffect, useRef, useState, type FormEvent } from 'react';
import { AuthSurface } from './AuthSurface';
import { authRequest, followAuthResult } from './request';
import { useAuthText, type AuthMessage } from './useAuthText';
import { useMobileText } from '@/features/mobile-parity/useMobileText';
import { PrimaryButton } from '@/components/mobile/PrimaryButton';
import { MobileIcon } from '@/components/mobile/MobileIcon';
import { GoogleMark, AppleMark } from '@/components/mobile/ProviderMarks';
import type { AccountRole } from '@/lib/auth/policy';

export type Settings = { enabled: boolean; emailFlows: boolean; google: boolean };
export function AuthForm({ mode, settings, initialCode }: { mode: 'signin' | 'signup'; settings: Settings; initialCode?: string }) {
  const t = useAuthText(); const { m } = useMobileText(); const signup = mode === 'signup';
  const [role, setRole] = useState<AccountRole | null>(null); const [visible, setVisible] = useState(false);
  const [busy, setBusy] = useState(false); const [message, setMessage] = useState(initialCode ?? ''); const [guidance, setGuidance] = useState(false);
  const [cooldown, setCooldown] = useState(0); const inFlight = useRef(false); const form = useRef<HTMLFormElement>(null); const firstRole = useRef<HTMLInputElement>(null);
  const locked = signup && role === null;
  const enabled = settings.enabled && (!signup || settings.emailFlows);
  useEffect(() => { if (cooldown <= 0) return; const timer = setTimeout(() => setCooldown(v => v - 1), 1000); return () => clearTimeout(timer); }, [cooldown]);
  const text = (code: string) => Object.hasOwn(t, code) ? t[code as AuthMessage] : t.unavailable;
  const guide = () => { setGuidance(true); firstRole.current?.focus(); };
  async function run(action: string, values: Record<string, unknown>) {
    if (inFlight.current) return;
    inFlight.current = true; setBusy(true); setMessage('');
    try { const result = await authRequest(action, values); if (!followAuthResult(result)) setMessage(result.code ?? 'unavailable'); if (action === 'resend' && result.code === 'checkEmail') setCooldown(60); }
    finally { inFlight.current = false; setBusy(false); }
  }
  function values() { const data = new FormData(form.current!); return { email: String(data.get('email') ?? ''), password: String(data.get('password') ?? ''), fullName: String(data.get('fullName') ?? ''), department: String(data.get('department') ?? ''), role }; }
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); if (!enabled) return;
    if (locked) { guide(); return; }
    const data = values();
    if (!data.email || !data.password || (signup && !data.fullName.trim()) || (signup && data.password.length < 6)) { setMessage('invalidFields'); return; }
    await run(mode, data);
  }
  return <AuthSurface mode={mode} title={m(signup ? 'auth.createAccountTitle' : 'auth.welcomeBack')} subtitle={m(signup ? 'auth.signUpSubtitle' : 'auth.signInSubtitle')}>
    {!settings.enabled ? <p className="auth-config-note">{t.notConfigured}</p> : signup && !settings.emailFlows ? <p className="auth-config-note">{t.emailSetup}</p> : null}
    <form ref={form} onSubmit={submit}>
      {signup ? <fieldset className={`native-role-field ${guidance ? 'needs-choice' : ''}`} disabled={busy}><legend>{m('auth.accountType')}</legend><div className="native-role-options">{(['intern', 'employer'] as const).map(value => <label key={value}><input ref={value === 'intern' ? firstRole : undefined} type="radio" name="role" value={value} checked={role === value} onChange={() => { setRole(value); setGuidance(false); }} /><span><MobileIcon name={value === 'intern' ? 'school-outline' : 'briefcase-outline'} width="18" height="18" />{m(value === 'intern' ? 'auth.intern' : 'auth.employer')}</span></label>)}</div>{locked ? <p id="signup-role-help" className="role-guidance" role={guidance ? 'alert' : undefined}>{m('auth.selectAccountType')}</p> : null}</fieldset> : null}
      {(signup ? ['fullName', 'email', 'password', 'department'] : ['email', 'password']).map(field => <div className="native-auth-field" key={field}><label htmlFor={`auth-${field}`}>{m(field === 'fullName' ? 'auth.fullName' : field === 'department' ? 'auth.departmentField' : field === 'email' ? 'auth.email' : 'auth.password')}</label><div className="auth-input-wrap">
        <input id={`auth-${field}`} name={field} required={field !== 'department'} minLength={field === 'password' && signup ? 6 : undefined} maxLength={field === 'password' ? 1024 : field === 'email' ? 254 : 200} type={field === 'password' ? visible ? 'text' : 'password' : field === 'email' ? 'email' : 'text'} dir={field === 'email' ? 'ltr' : undefined} disabled={locked || busy || !enabled} autoComplete={field === 'password' ? signup ? 'new-password' : 'current-password' : field === 'fullName' ? 'name' : field === 'email' ? 'username' : 'off'} aria-describedby={locked ? 'signup-role-help' : undefined} />
        {field === 'password' ? <button type="button" className="auth-eye" disabled={locked || busy || !enabled} aria-pressed={visible} aria-label={visible ? t.hidePassword : t.showPassword} onClick={() => setVisible(v => !v)}><MobileIcon name={visible ? 'eye-outline' : 'eye-off-outline'} width="20" height="20" /></button> : null}
        {locked ? <button type="button" className="role-lock-overlay" aria-label={t.roleRequired + ': ' + (field === 'fullName' ? m('auth.fullName') : field === 'department' ? m('auth.departmentField') : field === 'email' ? m('auth.email') : m('auth.password'))} onClick={guide} disabled={busy}><span className="visually-hidden">{t.roleRequired}</span></button> : null}
      </div></div>)}
      {!signup ? <Link href="/forgot-password" className="native-forgot">{m('auth.forgotPassword')}</Link> : null}
      <PrimaryButton type="submit" tone="accent" className="auth-submit" disabled={!enabled} loading={busy}>{busy ? m(signup ? 'auth.creatingAccount' : 'auth.signingIn') : m(signup ? 'auth.createAccount' : 'auth.signIn')}</PrimaryButton>
    </form>
    {!signup || role === 'intern' ? <><div className="native-divider"><span />{m('auth.or')}<span /></div><button type="button" className="native-social" disabled={busy || !settings.google || !settings.enabled} onClick={() => { if (locked) guide(); else void run('oauth', { provider: 'google', mode, role }); }}><GoogleMark />{m(signup ? 'auth.signUpWithGoogle' : 'auth.signInWithGoogle')}</button><button type="button" className="native-social native-apple" disabled aria-describedby="apple-web-gate"><AppleMark />{m('auth.continueWithApple')}</button><p id="apple-web-gate" className="native-provider-note">{settings.google ? t.appleSetup : t.providerSetup}</p></> : null}
    {!signup ? <button type="button" className="text-action" disabled={busy || cooldown > 0 || !settings.emailFlows} onClick={() => void run('resend', { email: values().email })}>{m('auth.emailConfirmation.resend')}{cooldown > 0 ? ` (${cooldown})` : ''}</button> : null}
    <p className="auth-message" role="status" aria-live="polite">{message ? text(message) : ''}</p>
    {!signup ? <Link className="text-link" href="/account">{t.continueAccount}</Link> : null}
    {!signup && settings.enabled ? <button type="button" className="text-action" disabled={busy} onClick={() => void run('logout', {})}>{t.signOut}</button> : null}
  </AuthSurface>;
}
