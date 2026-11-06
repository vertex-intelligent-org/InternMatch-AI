import { NextRequest, NextResponse } from 'next/server';
import { createAuthContext, privateHeaders } from '@/lib/auth/context';
import { canonical, identity } from '@/lib/auth/account';
import { AuthFailure } from '@/lib/auth/policy';
export const dynamic = 'force-dynamic';
export async function GET(request: NextRequest) {
  let ctx: ReturnType<typeof createAuthContext> | undefined;
  try {
    ctx = createAuthContext(request); const user = await identity(ctx);
    if (!user) return ctx.response({ authenticated: false });
    const account = await canonical(ctx, user.user, user.token);
    if (!account) return ctx.response({ authenticated: false, code: 'noAccount' }, 403);
    // No tokens, metadata, email or name in the marketing session-status response.
    return ctx.response({ authenticated: true, role: account.role, destination: account.destination });
  } catch (error) { const e = error instanceof AuthFailure ? error : new AuthFailure('unavailable', 503); return ctx ? ctx.response({ code: e.code }, e.status) : NextResponse.json({ code: e.code }, { status: e.status, headers: privateHeaders() }); }
}
