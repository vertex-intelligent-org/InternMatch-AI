import { AuthForm } from '@/features/auth/AuthForm';
import { publicAuthSettings } from '@/lib/auth/page';
export const dynamic = 'force-dynamic';
export default async function SignInPage({ searchParams }: { searchParams: Promise<{ error?: string; notice?: string }> }) {
  const params = await searchParams;
  return <AuthForm mode="signin" settings={publicAuthSettings()} initialCode={params.error ?? params.notice} />;
}
