'use client';

import Link from 'next/link';
import { useRef, useState, type FormEvent, type KeyboardEvent } from 'react';
import { BrandLogo } from '@/components/mobile/BrandLogo';
import { MobileIcon } from '@/components/mobile/MobileIcon';
import { PressableScale } from '@/components/mobile/PressableScale';
import { PrimaryButton } from '@/components/mobile/PrimaryButton';
import { AppleMark, GoogleMark } from '@/components/mobile/ProviderMarks';
import { PreferenceControls } from '@/components/PreferenceControls';
import { usePreferences } from '@/components/PreferencesProvider';
import { useMobileText } from './useMobileText';
import { useParityText } from './useParityText';

type Field = 'fullName' | 'email' | 'password' | 'department';
export function AuthReview({ initialMode = 'signIn' }: { initialMode?: 'signIn' | 'signUp' }) {
  const { locale, setLocale, t } = usePreferences(); const { m } = useMobileText(); const p = useParityText();
  const [mode, setMode] = useState<'signIn' | 'signUp'>(initialMode);
  const [expanded, setExpanded] = useState(false);
  const [role, setRole] = useState<'intern' | 'employer' | null>(null);
  const [visible, setVisible] = useState(false);
  const [guidance, setGuidance] = useState(false);
  const [notice, setNotice] = useState('');
  const [errors, setErrors] = useState<Partial<Record<Field, string>>>({});
  const form = useRef<HTMLFormElement>(null);
  const roleFirst = useRef<HTMLInputElement>(null);
  const languageTrigger = useRef<HTMLButtonElement>(null);
  const signUp = mode === 'signUp'; const locked = signUp && role === null;
  const fields: Field[] = signUp ? ['fullName', 'email', 'password', 'department'] : ['email', 'password'];
  function switchMode(next: 'signIn' | 'signUp') {
    setMode(next); setRole(null); setErrors({}); setNotice(''); setGuidance(false); form.current?.reset();
  }
  function guideRole() { setGuidance(true); roleFirst.current?.focus(); }
  function validate(e: FormEvent<HTMLFormElement>) {
    e.preventDefault(); setNotice('');
    if (locked) { guideRole(); return; }
    const data = new FormData(e.currentTarget); const found: Partial<Record<Field, string>> = {};
    for (const field of fields) {
      const value = String(data.get(field) ?? '').trim();
      if (field !== 'department' && !value) found[field] = p.required;
      if (field === 'email' && value && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)) found.email = p.emailInvalid;
      if (field === 'password' && signUp && value && value.length < 6) found.password = m('auth.passwordMinLength');
    }
    setErrors(found);
    const first = fields.find(field => found[field]);
    if (first) (e.currentTarget.elements.namedItem(first) as HTMLInputElement)?.focus();
    else setNotice(p.sampleValid);
  }
  function tabKeys(e: KeyboardEvent<HTMLButtonElement>) {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(e.key)) return;
    e.preventDefault();
    const next = e.key === 'Home' ? 'signIn' : e.key === 'End' ? 'signUp' : mode === 'signIn' ? 'signUp' : 'signIn';
    switchMode(next); document.getElementById('review-tab-' + next)?.focus();
  }
  return <main className="native-auth-page" id="main-content">
    <div className="auth-review-banner"><p>{p.review}</p><Link href="/foundation">{p.back}</Link></div>
    <div className="native-auth-shell">
      <div className="auth-toolbar">
        <div className={`preauth-language ${expanded ? 'expanded' : ''}`} dir="ltr" onKeyDown={e => { if (e.key === 'Escape') { setExpanded(false); languageTrigger.current?.focus(); } }}>
          {expanded ? <div className="preauth-options" role="group" aria-label={t.language}>{(['en', 'tr', 'ar'] as const).map(lang => <button key={lang} type="button" lang={lang} aria-pressed={locale === lang} onClick={() => { setLocale(lang); setExpanded(false); requestAnimationFrame(() => languageTrigger.current?.focus()); }}>{lang.toUpperCase()}</button>)}</div> : <button ref={languageTrigger} type="button" aria-expanded={false} aria-label={t.language} onClick={() => setExpanded(true)}>{locale.toUpperCase()}</button>}
        </div>
        <PreferenceControls showLanguage={false} />
      </div>
      <div className="native-auth-brand"><BrandLogo /></div>
      <header className="native-auth-heading"><h1>{m(signUp ? 'auth.createAccountTitle' : 'auth.welcomeBack')}</h1><p>{m(signUp ? 'auth.signUpSubtitle' : 'auth.signInSubtitle')}</p></header>
      <section className="native-auth-panel" aria-label={p.authTabs}>
        <div className="native-auth-segments" role="tablist" aria-label={p.authTabs}>
          {(['signIn', 'signUp'] as const).map(tab => <PressableScale id={`review-tab-${tab}`} key={tab} role="tab" aria-selected={mode === tab} aria-controls="auth-review-panel" tabIndex={mode === tab ? 0 : -1} scaleTo={.97} onKeyDown={tabKeys} onClick={() => switchMode(tab)}>{m(tab === 'signIn' ? 'auth.segmentedSignIn' : 'auth.segmentedSignUp')}</PressableScale>)}
        </div>
        <form ref={form} id="auth-review-panel" role="tabpanel" aria-labelledby={`review-tab-${mode}`} noValidate autoComplete="off" onSubmit={validate}>
          {signUp ? <fieldset className={`native-role-field ${guidance ? 'needs-choice' : ''}`}><legend>{m('auth.accountType')}</legend>
            <div className="native-role-options">{(['intern', 'employer'] as const).map(value => <label key={value}><input ref={value === 'intern' ? roleFirst : undefined} type="radio" name="preview-role" value={value} checked={role === value} onChange={() => { setRole(value); setGuidance(false); setErrors({}); }} /><span><MobileIcon name={value === 'intern' ? 'school-outline' : 'briefcase-outline'} width="18" height="18" />{m(value === 'intern' ? 'auth.intern' : 'auth.employer')}</span></label>)}</div>
            {locked ? <p id="role-guidance" className="role-guidance" role={guidance ? 'alert' : undefined}>{m('auth.selectAccountType')}</p> : null}
          </fieldset> : null}
          {fields.map(field => <div className="native-auth-field" key={field}>
            <label htmlFor={`sample-${field}`}>{m(field === 'department' ? 'auth.departmentField' : `auth.${field}`)}</label>
            <div className="auth-input-wrap">
              <input id={`sample-${field}`} name={field} disabled={locked} dir={field === 'email' ? 'ltr' : undefined} type={field === 'password' ? visible ? 'text' : 'password' : field === 'email' ? 'email' : 'text'} autoComplete="off" spellCheck={false} placeholder={field === 'department' ? m('auth.departmentPlaceholder') : field === 'email' ? 'sample@example.com' : field === 'password' ? p.previewPassword : p.previewName} aria-invalid={Boolean(errors[field])} aria-describedby={locked ? 'role-guidance' : errors[field] ? `sample-${field}-error` : undefined} onChange={() => { if (errors[field]) setErrors(current => ({ ...current, [field]: undefined })); }} />
              {field === 'password' ? <button type="button" className="auth-eye" disabled={locked} aria-label={visible ? p.hidePassword : p.showPassword} aria-pressed={visible} onClick={() => setVisible(v => !v)}><MobileIcon name={visible ? 'eye-outline' : 'eye-off-outline'} width="20" height="20" /></button> : null}
              {locked ? <button type="button" className="role-lock-overlay" aria-label={`${p.lockedField}: ${m(field === 'department' ? 'auth.departmentField' : `auth.${field}`)}`} onClick={guideRole}><span className="visually-hidden">{p.chooseRole}</span></button> : null}
            </div>
            {errors[field] ? <p id={`sample-${field}-error`} className="field-error">{errors[field]}</p> : null}
          </div>)}
          {!signUp ? <button type="button" className="native-forgot" onClick={() => setNotice(p.sampleOnly)}>{m('auth.forgotPassword')}</button> : null}
          <PrimaryButton type="submit" tone="accent" className="auth-submit">{m(signUp ? 'auth.createAccount' : 'auth.signIn')}</PrimaryButton>
        </form>
        {!signUp || role === 'intern' ? <><div className="native-divider"><span />{m('auth.or')}<span /></div>
          <PressableScale className="native-social" onClick={() => setNotice(p.sampleOnly)} aria-describedby="provider-note"><GoogleMark />{m(signUp ? 'auth.signUpWithGoogle' : 'auth.signInWithGoogle')}</PressableScale>
          <PressableScale className="native-social native-apple" onClick={() => setNotice(p.sampleOnly)} aria-describedby="provider-note"><AppleMark />{m('auth.continueWithApple')}</PressableScale>
          <p id="provider-note" className="native-provider-note">{p.providerNote}</p></> : null}
        <div className="native-legal"><a href="https://internmatch.college/privacy">{m('auth.privacyPolicy')}</a><span aria-hidden="true">·</span><a href="https://internmatch.college/terms">{m('auth.termsOfUse')}</a></div>
        <p className="auth-notice" role="status" aria-live="polite">{notice}</p>
      </section>
      <Link href="/review/motion" className="text-link">{p.motionPreview}</Link>
    </div>
  </main>;
}
