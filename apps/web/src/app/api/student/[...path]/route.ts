import { NextRequest, NextResponse } from 'next/server';
import { createAuthContext, privateHeaders } from '@/lib/auth/context';
import { AuthFailure } from '@/lib/auth/policy';
import { studentRequest } from '@/lib/student/server';
import { StudentFailure } from '@/lib/student/contracts';
export const dynamic='force-dynamic';
async function handler(request:NextRequest,{params}:{params:Promise<{path:string[]}>}){
  let ctx:ReturnType<typeof createAuthContext>|undefined;
  try{ctx=createAuthContext(request);const {path}=await params;return ctx.response(await studentRequest(ctx,path,request.method));}
  catch(e){const error=e instanceof StudentFailure?e:e instanceof AuthFailure?new StudentFailure(e.code==='notConfigured'?'notConfigured':e.code==='invalidCredentials'?'unauthorized':e.code==='csrf'?'forbidden':'unavailable',e.status):new StudentFailure('unavailable',503);return ctx?ctx.response({code:error.code},error.status):NextResponse.json({code:error.code},{status:error.status,headers:privateHeaders()});}
}
export {handler as GET,handler as POST,handler as DELETE};
