import { PasswordForm } from '@/features/auth/PasswordForm';
import { publicAuthSettings } from '@/lib/auth/page';
export const dynamic = 'force-dynamic';
export default function ResetPasswordPage() { return <PasswordForm reset enabled={publicAuthSettings().emailFlows} />; }
