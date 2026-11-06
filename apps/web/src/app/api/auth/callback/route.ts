import { NextRequest, NextResponse } from 'next/server';
import { createAuthContext, privateHeaders } from '@/lib/auth/context';
import { authCallback } from '@/lib/auth/actions';
import { AuthFailure } from '@/lib/auth/policy';
export const dynamic = 'force-dynamic';
export async function GET(request: NextRequest) {
  let ctx: ReturnType<typeof createAuthContext> | undefined;
  try { ctx = createAuthContext(request); return await authCallback(ctx); }
  catch (error) {
    const e = error instanceof AuthFailure ? error : new AuthFailure('unavailable', 503);
    if (ctx) { if (ctx.callbackState.attempted) ctx.clearFlow(); if (ctx.callbackState.exchanged && e.code !== 'unavailable') await ctx.clearSession(); return ctx.redirect('/app/sign-in?error=' + e.code); }
    return NextResponse.json({ code: e.code }, { status: e.status, headers: privateHeaders() });
  }
}
