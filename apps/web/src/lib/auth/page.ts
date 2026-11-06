import 'server-only';
import { cookies } from 'next/headers';
import { NextRequest } from 'next/server';
import { redirect } from 'next/navigation';
import { createAuthContext } from './context';
import { requiredConfig, authConfig } from './config';
import { canonical, identity } from './account';
import { AuthFailure, type AccountRole } from './policy';

export function publicAuthSettings() {
  try { const c = authConfig(); return { enabled: Boolean(c), emailFlows: Boolean(c?.emailFlows), google: Boolean(c?.google) }; }
  catch { return { enabled: false, emailFlows: false, google: false }; }
}
export async function accountForPage(expected?: AccountRole) {
  let account;
  try {
    const config = requiredConfig(); const jar = await cookies();
    const headers = new Headers(); headers.set('cookie', jar.toString());
    const ctx = createAuthContext(new NextRequest(config.origin + '/app/account', { headers }));
    const user = await identity(ctx); account = user ? await canonical(ctx, user.user, user.token) : null;
    if (user && !account) return { error: 'noAccount' as const, account: null };
  } catch (e) {
    return { error: e instanceof AuthFailure ? e.code : 'unavailable' as const, account: null };
  }
  if (!account) redirect('/sign-in');
  if (expected && expected !== account.role) redirect(account.destination.slice(4));
  return { error: null, account };
}
