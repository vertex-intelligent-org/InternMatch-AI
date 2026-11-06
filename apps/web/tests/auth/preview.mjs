// Explicit loopback-only sample-data preview. Never uses production auth or data.
import { spawn } from 'node:child_process';
import { startFixture } from './fixture.mjs';
const fixture=await startFixture();
const next=spawn(process.execPath,['node_modules/next/dist/bin/next','start','--hostname','127.0.0.1','--port','3111'],{stdio:'inherit',env:{...process.env,NEXT_TELEMETRY_DISABLED:'1',WEB_LOCAL_REVIEW:'1',WEB_AUTH_ENABLED:'1',SUPABASE_URL:'http://127.0.0.1:4412',SUPABASE_PUBLISHABLE_KEY:'sb_publishable_FIXTURE_ONLY_NOT_A_PRODUCTION_KEY',INTERNMATCH_API_URL:'http://127.0.0.1:4412/api/v1',WEB_ORIGIN:'http://127.0.0.1:3111',WEB_FLOW_SECRET:'fixture-only-012345678901234567890123456789',WEB_EMAIL_FLOWS_ENABLED:'1',WEB_GOOGLE_ENABLED:'0'}});
console.log('\nLOCAL SAMPLE PREVIEW ONLY — NO REAL ACCOUNTS OR DATABASE\nhttp://127.0.0.1:3111/app/sign-in\nSample email: student@example.test\nSample password: valid-password\nCtrl+C stops the preview. Sample changes reset on restart.\n');
let stopping=false;
function stop(){if(stopping)return;stopping=true;next.kill();fixture.close();}
process.on('SIGINT',stop);process.on('SIGTERM',stop);
next.on('error',error=>{console.error(error.message);process.exitCode=1;stop();});
next.on('exit',code=>{if(!stopping&&code)process.exitCode=code;stop();});
