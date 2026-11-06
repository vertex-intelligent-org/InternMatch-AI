import { AuthReview } from '@/features/mobile-parity/AuthReview';
export default async function AuthReviewPage({ searchParams }: { searchParams: Promise<{ mode?: string | string[] }> }) {
  const { mode } = await searchParams;
  return <AuthReview key={typeof mode === 'string' ? mode : 'sign-in'} initialMode={mode === 'sign-up' ? 'signUp' : 'signIn'} />;
}
