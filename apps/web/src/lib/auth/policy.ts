export type AccountRole = 'intern' | 'employer';
export type AuthCode = 'notConfigured' | 'unavailable' | 'invalidCredentials' | 'confirmEmail' | 'checkEmail' | 'roleRequired' | 'invalidFields' | 'existingAccount' | 'noAccount' | 'roleUnavailable' | 'csrf' | 'flowExpired' | 'passwordUpdated' | 'signedOut' | 'providerUnavailable' | 'sessionExists' | 'rateLimited';
export class AuthFailure extends Error { constructor(public code: AuthCode, public status = 400) { super(code); } }
export function roleOf(value: unknown): AccountRole | null { return value === 'intern' || value === 'employer' ? value : null; }
export function stringValue(value: unknown, max = 200) { return typeof value === 'string' && value.length <= max ? value.trim() : ''; }
export function emailValue(value: unknown) { const email = stringValue(value, 254).toLowerCase(); return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) ? email : ''; }
export function accountDestination(role: AccountRole) { return role === 'employer' ? '/app/employer' : '/app/student'; }
export function checkOrigin(origin: string | null, expected: string, site: string | null) { if (origin !== expected || site === 'cross-site') throw new AuthFailure('csrf', 403); }
export function emailSignupIntent(user: { email_confirmed_at?: string; app_metadata?: Record<string, unknown>; user_metadata?: Record<string, unknown> }) {
  // Metadata is only the user's original signup input. Authorization NEVER uses it.
  if (user.app_metadata?.provider !== 'email' || !user.email_confirmed_at) return null;
  const data = user.user_metadata ?? {}; const role = roleOf(data.account_type); const name = stringValue(data.full_name);
  return role && name ? { account_type: role, full_name: name, department: stringValue(data.department) || null } : null;
}
