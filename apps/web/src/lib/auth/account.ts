import 'server-only';
import type { User } from '@supabase/supabase-js';
import type { AuthContext } from './context';
import { AuthFailure, accountDestination, emailSignupIntent, roleOf, type AccountRole } from './policy';

export async function backend<T>(ctx: AuthContext, token: string, path: '/auth/sync' | '/auth/complete-signup' | '/profile' | '/auth/account', method = 'GET', body?: unknown): Promise<T> {
  let result: Response;
  try { result = await fetch(ctx.config.api + path, { method, body: body === undefined ? undefined : JSON.stringify(body), headers: { Authorization: `Bearer ${token}`, Accept: 'application/json', ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) }, cache: 'no-store', redirect: 'error', signal: AbortSignal.timeout(10_000) }); }
  catch { throw new AuthFailure('unavailable', 503); }
  if (!result.ok) throw new AuthFailure(result.status === 409 ? 'existingAccount' : result.status === 401 ? 'invalidCredentials' : 'unavailable', result.status === 409 ? 409 : result.status === 401 ? 401 : 503);
  try { return await result.json() as T; } catch { throw new AuthFailure('unavailable', 503); }
}
export async function identity(ctx: AuthContext) {
  const { data, error } = await ctx.client.auth.getUser();
  if (error || !data.user) {
    if (error?.name === 'AuthRetryableFetchError') throw new AuthFailure('unavailable', 503);
    if (error && ('status' in error && typeof error.status === 'number') && (error.status >= 500 || error.status === 0)) throw new AuthFailure('unavailable', 503);
    return null;
  }
  const { data: session } = await ctx.client.auth.getSession();
  if (!session.session?.access_token || session.session.user.id !== data.user.id) return null;
  return { user: data.user, token: session.session.access_token };
}
export type CanonicalAccount = { userId: string; role: AccountRole; fullName: string; destination: string };
export async function canonical(ctx: AuthContext, user: User, token: string): Promise<CanonicalAccount | null> {
  const sync = await backend<{ user_id: string; has_profile: boolean }>(ctx, token, '/auth/sync', 'POST');
  if (sync.user_id !== user.id || typeof sync.has_profile !== 'boolean') throw new AuthFailure('unavailable', 503);
  if (!sync.has_profile) return null;
  const profile = await backend<{ user_id: string; full_name: string; preferences?: { account_type?: unknown } }>(ctx, token, '/profile');
  if (profile.user_id !== user.id || typeof profile.full_name !== 'string') throw new AuthFailure('unavailable', 503);
  const role = roleOf(profile.preferences?.account_type);
  if (!role) throw new AuthFailure('roleUnavailable', 409);
  return { userId: user.id, role, fullName: profile.full_name, destination: accountDestination(role) };
}
export async function complete(ctx: AuthContext, user: User, token: string, payload: { full_name: string; department: string | null; account_type: AccountRole }) {
  const created = await backend<{ created: boolean; user_id: string; account_type: AccountRole }>(ctx, token, '/auth/complete-signup', 'POST', payload);
  if (created.user_id !== user.id || created.created !== true || created.account_type !== payload.account_type) throw new AuthFailure('unavailable', 503);
  const account = await canonical(ctx, user, token);
  if (!account) throw new AuthFailure('unavailable', 503);
  return account;
}
export async function finishEmailSignin(ctx: AuthContext, user: User, token: string) {
  const account = await canonical(ctx, user, token); if (account) return account;
  const intent = emailSignupIntent(user);
  if (intent) {
    try { return await complete(ctx, user, token, intent); }
    catch (e) { if (e instanceof AuthFailure && e.code === 'existingAccount') { const raced = await canonical(ctx, user, token); if (raced) return raced; } throw e; }
  }
  throw new AuthFailure('noAccount', 403);
}
