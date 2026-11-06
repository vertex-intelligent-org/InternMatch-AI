import 'server-only';
import type { AuthContext } from '@/lib/auth/context';
import { identity, canonical } from '@/lib/auth/account';
import { checkOrigin } from '@/lib/auth/policy';
import * as c from './contracts';

export async function studentIdentity(ctx: AuthContext) {
  const current = await identity(ctx); if (!current) throw new c.StudentFailure('unauthorized',401);
  const account = await canonical(ctx,current.user,current.token);
  if (!account || account.role!=='intern') throw new c.StudentFailure('forbidden',403);
  return { token:current.token, account };
}
async function upstream(ctx: AuthContext, token:string, path:string, method='GET', body?:unknown) {
  let response:Response;
  try { response=await fetch(ctx.config.api+path,{method,headers:{Authorization:'Bearer '+token,Accept:'application/json',...(body===undefined?{}:{'Content-Type':'application/json'})},body:body===undefined?undefined:JSON.stringify(body),cache:'no-store',redirect:'error',signal:AbortSignal.timeout(10000)}); }
  catch { throw new c.StudentFailure(method==='GET'?'unavailable':'uncertain',503); }
  if(!response.ok){const status=response.status;throw new c.StudentFailure(status===404?'notFound':status===401?'unauthorized':status===403?'forbidden':status===409?'conflict':status===429?'rateLimited':status===400||status===422?'invalid':method==='GET'?'unavailable':'uncertain',status>=500?503:status);}
  if(response.status===204)return null;
  try{return await response.json() as unknown;}catch{throw new c.StudentFailure(method==='GET'?'unavailable':'uncertain',503);}
}
function verified<T>(value:unknown,guard:(v:unknown)=>v is T):T { if(!guard(value))throw new c.StudentFailure('unavailable',503);return value; }
export async function studentRequest(ctx:AuthContext,parts:string[],method:string) {
  // Every route is allowlisted; IDs are UUIDs and never select another user's identity.
  const [area,id,action]=parts;
  if(parts.length>3||!['internships','saved','applications'].includes(area)|| (id && !c.uuid(id)))throw new c.StudentFailure('notFound',404);
  const search=ctx.request.nextUrl.searchParams;
  const mutation=method!=='GET';
  if(mutation)checkOrigin(ctx.request.headers.get('origin'),ctx.config.origin,ctx.request.headers.get('sec-fetch-site'));
  const {token}=await studentIdentity(ctx);
  if(!mutation){
    if(action)throw new c.StudentFailure('notFound',404);
    if(area==='internships'){
      if(id){if(search.size)throw new c.StudentFailure('invalid',400);const result=verified(await upstream(ctx,token,'/internships/'+id),c.internshipDetail);if(!result.is_active||result.publication_status!=='published')throw new c.StudentFailure('notFound',404);return result;}
      const result=verified(await upstream(ctx,token,'/internships?'+c.pagination(search)),(v):v is c.Page<c.Internship>=>c.pageOf(v,c.internship));
      if(result.items.some(i=>!i.is_active||i.publication_status!=='published'))throw new c.StudentFailure('unavailable',503);return result;
    }
    if(area==='saved'&&!id){if([...search.keys()].some(k=>!['limit','offset'].includes(k)))throw new c.StudentFailure('invalid',400);return verified(await upstream(ctx,token,'/saved-internships?'+c.pagination(search)),(v):v is c.Page<c.Saved>=>c.pageOf(v,c.saved));}
    if(search.size)throw new c.StudentFailure('invalid',400);
    if(area==='applications')return id?verified(await upstream(ctx,token,'/applications/'+id),c.applicationDetail):verified(await upstream(ctx,token,'/applications'),c.applications);
    throw new c.StudentFailure('notFound',404);
  }
  if(search.size)throw new c.StudentFailure('invalid',400);
  if(area==='saved' && id && !action && ['POST','DELETE'].includes(method)){
    const result=await upstream(ctx,token,'/saved-internships/'+id,method);
    if(!result||typeof result!=='object'|| !('internship_id' in result) || result.internship_id!==id || !('is_saved' in result)||result.is_saved!==(method==='POST'))throw new c.StudentFailure('uncertain',503);
    return { internship_id:id,is_saved:method==='POST' };
  }
  if(area==='applications'&&id&&action==='submit'&&method==='POST'){
    if(!ctx.request.headers.get('content-type')?.startsWith('application/json'))throw new c.StudentFailure('invalid',415);
    const reader=ctx.request.body?.getReader();if(!reader)throw new c.StudentFailure('invalid',400);
    const chunks:Uint8Array[]=[];let size=0;
    while(true){const part=await reader.read();if(part.done)break;size+=part.value.length;if(size>100000){await reader.cancel();throw new c.StudentFailure('invalid',413);}chunks.push(part.value);}
    let payload:unknown;try{payload=JSON.parse(Buffer.concat(chunks).toString('utf8'));}catch{throw new c.StudentFailure('invalid',400);}
    const data=c.submission(payload);
    const draft=verified(await upstream(ctx,token,'/applications/'+id),c.applicationDetail);
    if(draft.id!==id||draft.status!=='saved')throw new c.StudentFailure('conflict',409);
    const updated=await upstream(ctx,token,'/applications/'+id+'/submit','POST',data);
    if(!c.application(updated))throw new c.StudentFailure('uncertain',503);
    if(updated.id!==id||updated.status!=='applied')throw new c.StudentFailure('uncertain',503);
    return updated;
  }
  throw new c.StudentFailure('notFound',404);
}
