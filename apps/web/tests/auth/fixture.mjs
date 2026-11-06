import { createProcessingFixture } from './processing-fixture.mjs';
import { createStudentFixture } from './student-fixture.mjs';
import http from 'node:http';
import { randomUUID } from 'node:crypto';

export function startFixture(port = 4412) {
  const workspace = createStudentFixture();
  const processing = createProcessingFixture();
  let users, tokens, refresh, codes, events, nextSocial, failBackend, nextExpiry;
  const origins = new Set(['http://127.0.0.1:3111']);
  function reset() {
    workspace.reset();
    processing.reset();
    users = new Map(); tokens = new Map(); refresh = new Map(); codes = new Map(); events = []; nextSocial = 'social-new@example.test'; failBackend = false; nextExpiry = 3600;
    for (const [email, role, profile] of [['student@example.test','intern',true],['boss@example.test','employer',true],['pending@example.test','intern',false],['orphan@example.test',null,false],['unknown@example.test','admin',true]]) {
      users.set(email, { id: randomUUID(), email, password: 'valid-password', app_metadata: { provider: 'email', providers: ['email'] }, user_metadata: role ? { full_name: 'Çağrı الطالب', account_type: role } : {}, email_confirmed_at: new Date().toISOString(), created_at: new Date().toISOString(), aud: 'authenticated', role: 'authenticated', profile, canonicalRole: role });
    }
  }
  reset();
  function publicUser(user) { const safe = { ...user }; delete safe.password; delete safe.profile; delete safe.canonicalRole; return safe; }
  function session(user) {
    const lifetime = nextExpiry; nextExpiry = 3600; const now = Math.floor(Date.now()/1000); const sessionId = randomUUID();
    const encode = x => Buffer.from(JSON.stringify(x)).toString('base64url');
    const access = encode({alg:'HS256',typ:'JWT'})+'.'+encode({sub:user.id,exp:now+lifetime,iat:now,session_id:sessionId,role:'authenticated',aud:'authenticated'})+'.fixture';
    const token = { access_token: access, refresh_token: randomUUID(), expires_in: lifetime, expires_at: now+lifetime, token_type: 'bearer', user: publicUser(user) };
    tokens.set(access,user); refresh.set(token.refresh_token,user); return token;
  }
  function codeFor(user, kind, redirect) { const code = randomUUID(); codes.set(code,{user,kind,redirect}); return code; }
  const server = http.createServer(async (req,res) => {
    const url = new URL(req.url, 'http://127.0.0.1:'+port); let raw=''; for await (const chunk of req) raw += chunk;
    let body={}; try { body=raw?JSON.parse(raw):{}; } catch {}
    const send=(value,status=200)=>{res.writeHead(status,{'Content-Type':'application/json','Cache-Control':'no-store','X-Supabase-Api-Version':'2024-01-01'});res.end(JSON.stringify(value));};
    if(url.pathname==='/__fixture/reset'){reset();return send({ok:true});}
    if(url.pathname==='/__fixture/control'){workspace.control(body);processing.control(body);nextSocial=body.social??nextSocial;failBackend=body.failBackend??failBackend;nextExpiry=body.nextExpiry??nextExpiry;return send({ok:true});}
    if(url.pathname==='/__fixture/state')return send({processing:processing.state(),student:workspace.state(),events,codes:[...codes].map(([code,v])=>({code,kind:v.kind,email:v.user.email})),users:[...users.values()].map(u=>({email:u.email,id:u.id,profile:u.profile,role:u.canonicalRole}))});
    const bearer=req.headers.authorization?.replace(/^Bearer /,''); const user=tokens.get(bearer);
    if(url.pathname==='/auth/v1/token') {
      const grant=url.searchParams.get('grant_type');events.push({path:'token',grant,hasVerifier:Boolean(body.code_verifier)});
      if(grant==='password') { const u=users.get(body.email); if(!u||u.password!==body.password)return send({code:'invalid_credentials',msg:'Invalid login credentials'},400);return send(session(u)); }
      if(grant==='refresh_token'){const u=refresh.get(body.refresh_token);if(!u)return send({code:'refresh_token_not_found',msg:'Invalid refresh token'},400);refresh.delete(body.refresh_token);return send(session(u));}
      if(grant==='pkce'){const record=codes.get(body.auth_code);if(!record||!body.code_verifier)return send({code:'bad_code_verifier',msg:'Invalid flow'},400);codes.delete(body.auth_code);if(record.kind==='signup')record.user.email_confirmed_at=new Date().toISOString();return send(session(record.user));}
    }
    if(url.pathname==='/auth/v1/user') {
      if(!user)return send({code:'bad_jwt',msg:'Missing user'},401);
      if(req.method==='PUT'){if(typeof body.password!=='string')return send({msg:'password required'},400);user.password=body.password;events.push({path:'password-update',id:user.id});}
      return send(publicUser(user));
    }
    if(url.pathname==='/auth/v1/logout'){events.push({path:'logout'});if(user)tokens.delete(bearer);res.writeHead(204);return res.end();}
    if(url.pathname==='/auth/v1/signup') {
      events.push({path:'signup',challenge:Boolean(body.code_challenge),role:body.data?.account_type});
      if(users.has(body.email))return send({...publicUser(users.get(body.email)),identities:[]});
      const u={id:randomUUID(),email:body.email,password:body.password,app_metadata:{provider:'email',providers:['email']},user_metadata:body.data??{},email_confirmed_at:undefined,created_at:new Date().toISOString(),aud:'authenticated',role:'authenticated',profile:false,canonicalRole:null};users.set(u.email,u);
      codeFor(u,'signup',url.searchParams.get('redirect_to'));return send(publicUser(u));
    }
    if(url.pathname==='/auth/v1/recover'||url.pathname==='/auth/v1/resend'){
      const u=users.get(body.email);if(u)codeFor(u,url.pathname.endsWith('recover')?'recovery':'signup',url.searchParams.get('redirect_to'));events.push({path:url.pathname.endsWith('recover')?'recover':'resend',challenge:Boolean(body.code_challenge)});return send({});
    }
    if(url.pathname==='/auth/v1/authorize'){
      const redirect=url.searchParams.get('redirect_to');if(!redirect||!origins.has(new URL(redirect).origin)){res.writeHead(400);return res.end();}
      let u=users.get(nextSocial);if(!u){u={id:randomUUID(),email:nextSocial,app_metadata:{provider:'google',providers:['google']},user_metadata:{name:'Social Example'},identities:[{provider:'google'}],email_confirmed_at:new Date().toISOString(),created_at:new Date().toISOString(),aud:'authenticated',role:'authenticated',profile:false,canonicalRole:null};users.set(u.email,u);}else u.identities=[{provider:'google'}];
      const code=codeFor(u,'oauth',redirect);res.writeHead(302,{Location:redirect+'?code='+code});return res.end();
    }
    if(url.pathname.startsWith('/api/v1/')){
      if(!user)return send({detail:'unauthorized'},401);
      if(failBackend)return send({detail:'offline'},503);
      const path=url.pathname.slice(7);events.push({path,method:req.method,email:user.email,body});
      if(processing.handle({path,url,req,body,raw,user,send}))return;
      if(workspace.handle({path,url,req,body,user,send}))return;
      if(path==='/auth/sync')return send({user_id:user.id,email:user.email,has_profile:user.profile});
      if(path==='/profile')return user.profile?send({user_id:user.id,full_name:user.user_metadata.full_name??'Example User',preferences:{account_type:user.canonicalRole}}):send({detail:'not found'},404);
      if(path==='/auth/complete-signup'){
        if(user.profile)return send({detail:'exists'},409);
        if(!['intern','employer'].includes(body.account_type))return send({detail:'bad role'},422);
        user.profile=true;user.canonicalRole=body.account_type;user.user_metadata.full_name=body.full_name;return send({created:true,user_id:user.id,account_type:body.account_type},201);
      }
      if(path==='/auth/account'&&req.method==='DELETE'){
        if(user.profile)return send({detail:'fixture protects existing accounts'},409);
        users.delete(user.email);tokens.delete(bearer);return send({deleted:true,message:'fixture only'});
      }
    }
    return send({error:'fixture route missing',path:url.pathname},404);
  });
  return new Promise(resolve=>server.listen(port,'127.0.0.1',()=>resolve(server)));
}
