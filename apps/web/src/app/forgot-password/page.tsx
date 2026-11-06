import { PasswordForm } from '@/features/auth/PasswordForm';
import { publicAuthSettings } from '@/lib/auth/page';
export const dynamic = 'force-dynamic';
export default function ForgotPasswordPage() { return <PasswordForm reset={false} enabled={publicAuthSettings().emailFlows} />; }
