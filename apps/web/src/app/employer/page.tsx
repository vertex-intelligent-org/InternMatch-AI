import { accountForPage } from '@/lib/auth/page';
import { AccountView } from '@/features/auth/AccountView';
export const dynamic = 'force-dynamic';
export default async function EmployerPage() { return <AccountView {...await accountForPage('employer')} />; }
