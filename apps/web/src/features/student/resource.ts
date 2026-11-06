'use client';
import { useEffect, useState } from 'react';
import { StudentFailure, type StudentCode } from '@/lib/student/contracts';
const codes:StudentCode[]=['unavailable','notFound','unauthorized','forbidden','invalid','conflict','rateLimited','uncertain','notConfigured'];
export async function studentFetch<T>(url:string,method='GET',body?:unknown,signal?:AbortSignal):Promise<T>{
  let response:Response;
  try{response=await fetch('/app/api/student/'+url,{method,credentials:'same-origin',cache:'no-store',redirect:'error',headers:body===undefined?undefined:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body),signal:signal?AbortSignal.any([signal,AbortSignal.timeout(15000)]):AbortSignal.timeout(15000)});}
  catch(e){if(signal?.aborted)throw e;throw new StudentFailure(method==='GET'?'unavailable':'uncertain',503);}
  let value:unknown;try{value=await response.json();}catch{throw new StudentFailure(method==='GET'?'unavailable':'uncertain',503);}
  if(!response.ok){const code=value&&typeof value==='object'&&'code'in value&&codes.includes(value.code as StudentCode)?value.code as StudentCode:'unavailable';throw new StudentFailure(code,response.status);}
  return value as T;
}
export function useStudentResource<T>(url:string){
  const [revision,setRevision]=useState(0);const key=url+'|'+revision;
  const [state,setState]=useState<{key:string;data?:T;error?:StudentCode}>({key:''});
  useEffect(()=>{const abort=new AbortController();void studentFetch<T>(url,'GET',undefined,abort.signal).then(data=>{if(!abort.signal.aborted)setState({key,data});}).catch(error=>{if(!abort.signal.aborted)setState({key,error:error instanceof StudentFailure?error.code:'unavailable'});});return()=>abort.abort();},[url,key]);
  return {data:state.key===key?state.data:undefined,error:state.key===key?state.error:undefined,pending:state.key!==key,refetch:()=>setRevision(v=>v+1)};
}
