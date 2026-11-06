import 'server-only';
import { createServerClient, type CookieOptions } from '@supabase/ssr';
import { NextRequest, NextResponse } from 'next/server';
import { requiredConfig } from './config';
import { AuthFailure } from './policy';
import { flowCookie } from './flow';

export const sessionCookie = 'im-web-session';
export function privateHeaders() { return { 'Cache-Control': 'private, no-store, max-age=0', Pragma: 'no-cache', Expires: '0', Vary: 'Cookie', 'Referrer-Policy': 'no-referrer', 'X-Content-Type-Options': 'nosniff' }; }
export function createAuthContext(request: NextRequest) {
  const config = requiredConfig();
  const jar = new Map(request.cookies.getAll().map(c => [c.name, c.value]));
  const writes = new Map<string, { name: string; value: string; options: CookieOptions }>();
  const cacheHeaders = new Headers(privateHeaders());
  const callbackState = { attempted: false, exchanged: false };
  const cookie = (name: string, value: string, options: CookieOptions = {}) => {
    jar.set(name, value); writes.set(name, { name, value, options: { ...options, path: '/app', httpOnly: true, sameSite: 'lax', secure: config.secure } });
  };
  const client = createServerClient(config.url, config.key, {
    cookieOptions: { name: sessionCookie, path: '/app', httpOnly: true, sameSite: 'lax', secure: config.secure },
    cookies: {
      getAll: () => Array.from(jar, ([name, value]) => ({ name, value })),
      setAll: (values, headers) => { values.forEach(c => cookie(c.name, c.value, c.options)); Object.entries(headers ?? {}).forEach(([k, v]) => cacheHeaders.set(k, v)); },
    },
    global: { fetch: (input, init) => fetch(input, { ...init, cache: 'no-store', redirect: 'error', signal: AbortSignal.timeout(10_000) }) },
  });
  const response = (body: unknown, status = 200) => {
    const result = NextResponse.json(body, { status, headers: cacheHeaders });
    cacheHeaders.forEach((v, k) => result.headers.set(k, v));
    writes.forEach(c => result.cookies.set(c.name, c.value, c.options)); return result;
  };
  const redirect = (path: string) => {
    // Every destination is an internal constant constructed by this module's callers.
    if (!path.startsWith('/app/') || path.includes('://') || path.includes('\\')) throw new AuthFailure('flowExpired');
    const result = NextResponse.redirect(new URL(path, config.origin), 303);
    cacheHeaders.forEach((v, k) => result.headers.set(k, v)); writes.forEach(c => result.cookies.set(c.name, c.value, c.options)); return result;
  };
  const clearSession = async () => {
    try { await client.auth.signOut({ scope: 'local' }); } catch { /* Browser cookies must still be removed. */ }
    for (const name of jar.keys()) if (name === sessionCookie || name.startsWith(sessionCookie + '.') || name === sessionCookie + '-code-verifier' || name.startsWith(sessionCookie + '-code-verifier.')) cookie(name, '', { maxAge: 0 });
  };
  return { request, config, client, jar, cookie, response, redirect, clearSession, clearFlow: () => cookie(flowCookie, '', { maxAge: 0 }), writes, callbackState };
}
export type AuthContext = ReturnType<typeof createAuthContext>;
