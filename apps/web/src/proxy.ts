import { NextRequest, NextResponse } from 'next/server';
import { authConfig } from '@/lib/auth/config';
import { createAuthContext, privateHeaders } from '@/lib/auth/context';
import { identity } from '@/lib/auth/account';

export async function proxy(request: NextRequest) {
  let ctx: ReturnType<typeof createAuthContext> | undefined;
  try { if (authConfig()) { ctx = createAuthContext(request); await identity(ctx); } } catch { /* Pages independently verify identity and show a retryable error. */ }
  if (ctx) ctx.writes.forEach(c => request.cookies.set(c.name, c.value));
  const response = NextResponse.next({ request: { headers: request.headers } });
  Object.entries(privateHeaders()).forEach(([k, v]) => response.headers.set(k, v));
  ctx?.writes.forEach(c => response.cookies.set(c.name, c.value, c.options));
  return response;
}
export const config = { matcher: ['/', '/account/:path*', '/student/:path*', '/employer/:path*'] };
