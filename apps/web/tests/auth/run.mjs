import { spawn } from 'node:child_process';
import { startFixture } from './fixture.mjs';
const origin='http://127.0.0.1:3111';
const fixture=await startFixture();
const next=spawn(process.execPath,['node_modules/next/dist/bin/next','start','--hostname','127.0.0.1','--port','3111'],{stdio:['ignore','ignore','pipe'],env:{...process.env,NEXT_TELEMETRY_DISABLED:'1',WEB_AUTH_ENABLED:'1',SUPABASE_URL:'http://127.0.0.1:4412',SUPABASE_PUBLISHABLE_KEY:'sb_publishable_FIXTURE_ONLY_NOT_A_PRODUCTION_KEY',INTERNMATCH_API_URL:'http://127.0.0.1:4412/api/v1',WEB_ORIGIN:origin,WEB_FLOW_SECRET:'fixture-only-012345678901234567890123456789',WEB_EMAIL_FLOWS_ENABLED:'1',WEB_GOOGLE_ENABLED:'1'}});
next.stderr.on('data',data=>process.stderr.write(data));
let tests;
try{
 let ready=false;for(let i=0;i<100;i++){try{const r=await fetch(origin+'/app/sign-in');if(r.ok){ready=true;break;}}catch{}await new Promise(r=>setTimeout(r,200));}
 if(!ready)throw new Error('Isolated Next fixture did not start');
 tests=spawn(process.execPath,['node_modules/@playwright/test/cli.js','test','--config','playwright.auth.config.ts',...process.argv.slice(2)],{stdio:'inherit',env:{...process.env,WEB_AUTH_ENABLED:'0'}});
 const code=await new Promise(resolve=>tests.on('exit',resolve));process.exitCode=typeof code==='number'?code:1;
}finally{tests?.kill();next.kill();await new Promise(resolve=>fixture.close(resolve));}
