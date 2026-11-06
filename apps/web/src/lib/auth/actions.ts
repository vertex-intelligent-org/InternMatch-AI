import 'server-only';
import { AuthFailure, checkOrigin, emailValue, roleOf, stringValue } from './policy';
import { flowCookie, openFlow, sealFlow, tokenHash } from './flow';
import { backend, canonical, complete, finishEmailSignin, identity } from './account';
import type { AuthContext } from './context';

function authError(error: { code?: string; status?: number } | null) {
  if (!error) return;
  throw new AuthFailure(error.status === 429 ? 'rateLimited' : error.code === 'email_not_confirmed' ? 'confirmEmail' : error.code === 'invalid_credentials' ? 'invalidCredentials' : 'unavailable', error.status === 429 ? 429 : error.code === 'email_not_confirmed' ? 403 : error.code === 'invalid_credentials' ? 401 : 503);
}
async function body(ctx: AuthContext): Promise<Record<string, unknown>> {
  checkOrigin(ctx.request.headers.get('origin'), ctx.config.origin, ctx.request.headers.get('sec-fetch-site'));
  if (!ctx.request.headers.get('content-type')?.startsWith('application/json')) throw new AuthFailure('invalidFields', 415);
  const reader = ctx.request.body?.getReader(); if (!reader) throw new AuthFailure('invalidFields');
  let size = 0; const chunks: Uint8Array[] = [];
  while (true) { const next = await reader.read(); if (next.done) break; size += next.value.length; if (size > 8192) { await reader.cancel(); throw new AuthFailure('invalidFields', 413); } chunks.push(next.value); }
  try { const value = JSON.parse(Buffer.concat(chunks).toString('utf8')); if (!value || Array.isArray(value) || typeof value !== 'object') throw new Error(); return value; } catch { throw new AuthFailure('invalidFields'); }
}
function passwordOf(data: Record<string, unknown>, signup = false) { const password = data.password; if (typeof password !== 'string' || password.length > 1024 || password.length < (signup ? 6 : 1)) throw new AuthFailure('invalidFields'); return password; }
function setFlow(ctx: AuthContext, data: Parameters<typeof sealFlow>[1]) { ctx.cookie(flowCookie, sealFlow(ctx.config.secret, data), { maxAge: 600 }); }
const callback = (ctx: AuthContext) => ctx.config.origin + '/app/api/auth/callback';

export async function authAction(ctx: AuthContext, action: string) {
  const data = await body(ctx);
  if (action === 'logout') { await ctx.clearSession(); ctx.clearFlow(); return ctx.response({ code: 'signedOut', destination: '/app/sign-in' }); }
  if (action === 'reset') {
    const flow = openFlow(ctx.config.secret, ctx.jar.get(flowCookie)); const current = await identity(ctx);
    if (!current || flow?.intent !== 'recovery-ready' || flow.userId !== current.user.id || flow.tokenHash !== tokenHash(current.token)) throw new AuthFailure('flowExpired', 403);
    const password = passwordOf(data, true); const { error } = await ctx.client.auth.updateUser({ password }); authError(error);
    await ctx.clearSession(); ctx.clearFlow(); return ctx.response({ code: 'passwordUpdated', destination: '/app/sign-in?notice=passwordUpdated' });
  }
  if (await identity(ctx)) throw new AuthFailure('sessionExists', 409);
  if (action === 'signin') {
    const email = emailValue(data.email); if (!email) throw new AuthFailure('invalidFields');
    const { data: login, error } = await ctx.client.auth.signInWithPassword({ email, password: passwordOf(data) }); authError(error);
    if (!login.user || !login.session) throw new AuthFailure('invalidCredentials', 401);
    try { const account = await finishEmailSignin(ctx, login.user, login.session.access_token); ctx.clearFlow(); return ctx.response({ destination: account.destination }); }
    catch (e) { if (e instanceof AuthFailure && e.code !== 'unavailable') await ctx.clearSession(); throw e; }
  }
  if (action === 'signup') {
    if (!ctx.config.emailFlows) throw new AuthFailure('providerUnavailable', 503);
    const role = roleOf(data.role); if (!role) throw new AuthFailure('roleRequired');
    const name = stringValue(data.fullName); const department = stringValue(data.department); const email = emailValue(data.email);
    if (!name || !email) throw new AuthFailure('invalidFields');
    const password = passwordOf(data, true);
    const { data: signup, error } = await ctx.client.auth.signUp({ email, password, options: { emailRedirectTo: callback(ctx), data: { full_name: name, department: department || null, account_type: role } } }); authError(error);
    if (!signup.session || !signup.user) { setFlow(ctx, { intent: 'email-signup' }); return ctx.response({ code: 'checkEmail' }); }
    try { const account = await complete(ctx, signup.user, signup.session.access_token, { full_name: name, department: department || null, account_type: role }); ctx.clearFlow(); return ctx.response({ destination: account.destination }); }
    catch (e) { if (e instanceof AuthFailure && e.code === 'existingAccount') await ctx.clearSession(); throw e; }
  }
  if (action === 'recover' || action === 'resend') {
    if (!ctx.config.emailFlows) throw new AuthFailure('providerUnavailable', 503);
    const email = emailValue(data.email); if (!email) throw new AuthFailure('invalidFields');
    const result = action === 'recover' ? await ctx.client.auth.resetPasswordForEmail(email, { redirectTo: callback(ctx) }) : await ctx.client.auth.resend({ type: 'signup', email, options: { emailRedirectTo: callback(ctx) } });
    authError(result.error); setFlow(ctx, { intent: action === 'recover' ? 'recovery' : 'email-signup' }); return ctx.response({ code: 'checkEmail' });
  }
  if (action === 'oauth') {
    // Apple web credentials/revocation are a separate integration gate. Never fake it.
    if (!ctx.config.google || data.provider !== 'google') throw new AuthFailure('providerUnavailable', 503);
    const signup = data.mode === 'signup'; const role = roleOf(data.role);
    if (signup && !role) throw new AuthFailure('roleRequired');
    if (!signup && data.mode !== 'signin') throw new AuthFailure('invalidFields');
    const { data: oauth, error } = await ctx.client.auth.signInWithOAuth({ provider: 'google', options: { redirectTo: callback(ctx), skipBrowserRedirect: true } }); authError(error);
    if (!oauth.url || new URL(oauth.url).origin !== new URL(ctx.config.url).origin) throw new AuthFailure('unavailable', 503);
    setFlow(ctx, signup ? { intent: 'social-signup', role: role!, department: stringValue(data.department) } : { intent: 'signin' });
    return ctx.response({ oauthUrl: oauth.url });
  }
  throw new AuthFailure('invalidFields', 404);
}

export async function authCallback(ctx: AuthContext) {
  const flow = openFlow(ctx.config.secret, ctx.jar.get(flowCookie));
  const code = ctx.request.nextUrl.searchParams.get('code');
  if (!flow || !code || code.length > 4096 || ctx.request.nextUrl.searchParams.has('error')) throw new AuthFailure('flowExpired', 403);
  ctx.callbackState.attempted = true;
  // Consume the one-time intent. The PKCE verifier is handled by the SDK.
  ctx.clearFlow();
  const { data, error } = await ctx.client.auth.exchangeCodeForSession(code); authError(error);
  ctx.callbackState.exchanged = Boolean(data.session);
  const current = await identity(ctx);
  if (!data.session || !current) throw new AuthFailure('flowExpired', 403);
  if (flow.intent === 'recovery') {
    setFlow(ctx, { intent: 'recovery-ready', userId: current.user.id, tokenHash: tokenHash(current.token) });
    return ctx.redirect('/app/reset-password');
  }
  if (flow.intent === 'email-signup') {
    const account = await finishEmailSignin(ctx, current.user, current.token); return ctx.redirect(account.destination);
  }
  if (flow.intent !== 'signin' && flow.intent !== 'social-signup') throw new AuthFailure('flowExpired', 403);
  if (current.user.app_metadata?.provider !== 'google' && !current.user.identities?.some(value => value.provider === 'google')) throw new AuthFailure('flowExpired', 403);
  const account = await canonical(ctx, current.user, current.token);
  if (flow.intent === 'signin') {
    if (account) return ctx.redirect(account.destination);
    // Same explicit mobile contract: a new OAuth identity must not become an implicit account.
    // Backend enforces fresh-session reauthentication and authoritative identity itself.
    const deleted = await backend<{ deleted: boolean }>(ctx, current.token, '/auth/account', 'DELETE');
    if (deleted.deleted !== true) throw new AuthFailure('unavailable', 503);
    await ctx.clearSession(); throw new AuthFailure('noAccount', 403);
  }
  if (account) { await ctx.clearSession(); throw new AuthFailure('existingAccount', 409); }
  if (!flow.role) throw new AuthFailure('roleRequired');
  const name = stringValue(current.user.user_metadata.full_name) || stringValue(current.user.user_metadata.name) || 'InternMatch User';
  try { const created = await complete(ctx, current.user, current.token, { full_name: name, department: flow.department || null, account_type: flow.role }); return ctx.redirect(created.destination); }
  catch (e) { if (e instanceof AuthFailure && e.code === 'existingAccount') await ctx.clearSession(); throw e; }
}
