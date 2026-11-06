import { accountForPage } from '@/lib/auth/page';
import { AccountView } from '@/features/auth/AccountView';
export const dynamic = 'force-dynamic';
export default async function AccountPage() { return <AccountView {...await accountForPage()} />; }
