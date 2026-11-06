'use client';
import Link from 'next/link';
import { useStudentText } from '@/features/student/useStudentText';
import { useRef, useState } from 'react';
import { AuthSurface } from './AuthSurface';
import { authRequest, followAuthResult } from './request';
import { useAuthText } from './useAuthText';
import type { CanonicalAccount } from '@/lib/auth/account';
import { PrimaryButton } from '@/components/mobile/PrimaryButton';
export function AccountView({ account, error }: { account: CanonicalAccount | null; error: string | null }) {
  const student = useStudentText();
  const t = useAuthText(); const [busy, setBusy] = useState(false); const [message, setMessage] = useState(''); const flight = useRef(false);
  async function logout() { if (flight.current) return; flight.current = true; setBusy(true); const result = await authRequest('logout', {}); if (!followAuthResult(result)) { setMessage(t.unavailable); setBusy(false); flight.current = false; } }
  return <AuthSurface title={account ? t.accountReady : t.accountAccess} subtitle={account?.fullName}>
    {account ? <><p className="account-role">{account.role === 'employer' ? t.employerRole : t.studentRole}</p><p className="account-stage-note">{account.role === 'intern' ? student.t.profileHelp : t.workspaceNext}</p>{account.role === 'intern' ? <Link className="button primary" href="/student">{student.t.home}</Link> : null}</> : <p className="auth-config-note">{error && Object.hasOwn(t, error) ? t[error as keyof typeof t] : t.unavailable}</p>}
    <div className="button-row"><PrimaryButton disabled={busy} onClick={() => void logout()} loading={busy}>{t.signOut}</PrimaryButton>{!account ? <button type="button" className="button secondary" onClick={() => window.location.reload()}>{t.retry}</button> : null}</div>
    <p role="status" className="auth-message">{message}</p><Link className="text-link" href="/sign-in">{t.signInAgain}</Link>
  </AuthSurface>;
}
