import { NextRequest, NextResponse } from 'next/server';
import { createAuthContext, privateHeaders } from '@/lib/auth/context';
import { authAction } from '@/lib/auth/actions';
import { AuthFailure } from '@/lib/auth/policy';
export const dynamic = 'force-dynamic';
export async function POST(request: NextRequest, { params }: { params: Promise<{ action: string }> }) {
  let ctx: ReturnType<typeof createAuthContext> | undefined;
  try { ctx = createAuthContext(request); return await authAction(ctx, (await params).action); }
  catch (error) { const e = error instanceof AuthFailure ? error : new AuthFailure('unavailable', 503); return ctx ? ctx.response({ code: e.code }, e.status) : NextResponse.json({ code: e.code }, { status: e.status, headers: privateHeaders() }); }
}
