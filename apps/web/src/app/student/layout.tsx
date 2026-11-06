import { accountForPage } from '@/lib/auth/page';
import { AccountView } from '@/features/auth/AccountView';
import { StudentShell } from '@/features/student/StudentShell';
export const dynamic='force-dynamic';
export default async function StudentLayout({children}:{children:React.ReactNode}){const result=await accountForPage('intern');if(!result.account)return <AccountView {...result}/>;return <StudentShell name={result.account.fullName} preview={process.env.WEB_LOCAL_REVIEW==='1' && process.env.INTERNMATCH_API_URL==='http://127.0.0.1:4412/api/v1'}>{children}</StudentShell>;}
