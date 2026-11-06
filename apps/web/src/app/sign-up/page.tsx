import { AuthForm } from '@/features/auth/AuthForm';
import { publicAuthSettings } from '@/lib/auth/page';
export const dynamic = 'force-dynamic';
export default function SignUpPage() { return <AuthForm mode="signup" settings={publicAuthSettings()} />; }
