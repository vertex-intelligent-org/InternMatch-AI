'use client';
import Link from 'next/link';
import { useWorkspaceText } from '@/features/workspace/useWorkspaceText';
import { usePathname } from 'next/navigation';
import { useState } from 'react';
import { BrandLogo } from '@/components/mobile/BrandLogo';
import { PreferenceControls } from '@/components/PreferenceControls';
import { Icon, type IconName } from '@/components/Icon';
import { authRequest, followAuthResult } from '@/features/auth/request';
import { useStudentText } from './useStudentText';
export function StudentShell({name,children,preview=false}:{name:string;children:React.ReactNode;preview?:boolean}){
  const {t:w}=useWorkspaceText();
  const {t}=useStudentText();const pathname=usePathname();const [busy,setBusy]=useState(false);const [error,setError]=useState(false);
  const links:{href:string;label:string;icon:IconName}[]=[{href:'/student',label:t.home,icon:'home'},{href:'/student/opportunities',label:t.opportunities,icon:'briefcase'},{href:'/student/saved',label:t.saved,icon:'check'},{href:'/student/applications',label:t.applications,icon:'file'},{href:'/student/matches',label:w.matches,icon:'target'},{href:'/student/profile',label:w.profile,icon:'users'}];
  async function logout(){if(busy)return;setBusy(true);setError(false);const result=await authRequest('logout',{});if(!followAuthResult(result)){setError(true);setBusy(false);}}
  const navigation=(mobile=false)=><nav aria-label={t.navigation}>{links.filter(link=>!mobile||link.href!=='/student/saved').map(link=>{const active=link.href==='/student'?pathname==='/student':pathname.startsWith(link.href);return <Link key={link.href} href={link.href} prefetch={false} aria-current={active?'page':undefined}><Icon name={link.icon}/><span>{link.label}</span></Link>;})}</nav>;
  return <div className="student-workspace" data-testid="student-workspace"><a href="#main-content" className="skip-link">{t.navigation}</a><aside className="student-sidebar"><BrandLogo/>{navigation()}<div className="student-sidebar-footer"><Link href="/account">{t.account}</Link><button type="button" disabled={busy} onClick={()=>void logout()}>{t.logout}</button>{error?<p role="alert">{t.unavailable}</p>:null}</div></aside><div className="student-body"><header className="student-toolbar"><div><span className="student-mobile-logo"><BrandLogo/></span><span className="student-name" dir="auto">{name}</span><Link className="student-account-link" href="/account">{t.account}</Link></div><PreferenceControls/></header><main id="main-content" className="student-main">{preview?<aside className="student-note student-preview-note">{t.localPreview}</aside>:null}{children}</main></div><div className="student-bottom-nav">{navigation(true)}</div></div>;
}
