import {NextRequest,NextResponse} from 'next/server';
import {createAuthContext,privateHeaders} from '@/lib/auth/context';
import {AuthFailure} from '@/lib/auth/policy';
import {StudentFailure} from '@/lib/student/contracts';
import {workspaceRequest} from '@/lib/workspace/server';
export const dynamic='force-dynamic';
async function handler(request:NextRequest,{params}:{params:Promise<{path:string[]}>}){let ctx:ReturnType<typeof createAuthContext>|undefined;try{ctx=createAuthContext(request);return ctx.response(await workspaceRequest(ctx,(await params).path,request.method));}catch(e){const error=e instanceof StudentFailure?e:e instanceof AuthFailure?new StudentFailure(e.code==='notConfigured'?'notConfigured':e.code==='csrf'?'forbidden':e.code==='invalidCredentials'?'unauthorized':'unavailable',e.status):new StudentFailure('unavailable',503);return ctx?ctx.response({code:error.code},error.status):NextResponse.json({code:error.code},{status:error.status,headers:privateHeaders()});}}
export {handler as GET,handler as POST,handler as PUT};
