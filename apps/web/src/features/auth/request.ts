import type { AuthMessage } from './useAuthText';
export type AuthResult = { code?: AuthMessage; destination?: string; oauthUrl?: string };
export async function authRequest(action: string, data: Record<string, unknown>): Promise<AuthResult> {
  try {
    const response = await fetch('/app/api/auth/' + action, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data), credentials: 'same-origin', cache: 'no-store', signal: AbortSignal.timeout(15_000) });
    const result = await response.json() as AuthResult;
    return result;
  } catch { return { code: 'unavailable' }; }
}
export function followAuthResult(result: AuthResult) {
  if (result.destination && /^\/app\/(student|employer|sign-in(?:\?notice=passwordUpdated)?)$/.test(result.destination)) { window.location.assign(result.destination); return true; }
  if (result.oauthUrl) { const url = new URL(result.oauthUrl); if (url.protocol === 'https:' || (url.protocol === 'http:' && ['127.0.0.1', 'localhost'].includes(url.hostname))) { window.location.assign(url.href); return true; } }
  return false;
}
