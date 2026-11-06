import 'server-only';
import { createCipheriv, createDecipheriv, createHash, randomBytes } from 'node:crypto';
import type { AccountRole } from './policy';

export const flowCookie = 'im-web-flow';
export type Flow = { intent: 'email-signup' | 'signin' | 'social-signup' | 'recovery' | 'recovery-ready'; expires: number; nonce: string; role?: AccountRole; fullName?: string; department?: string; userId?: string; tokenHash?: string };
export function tokenHash(token: string) { return createHash('sha256').update(token).digest('hex'); }
export function sealFlow(secret: string, data: Omit<Flow, 'expires' | 'nonce'>) {
  const iv = randomBytes(12); const cipher = createCipheriv('aes-256-gcm', createHash('sha256').update(secret).digest(), iv);
  const flow: Flow = { ...data, nonce: randomBytes(20).toString('base64url'), expires: Date.now() + 10 * 60_000 };
  const ciphertext = Buffer.concat([cipher.update(JSON.stringify(flow), 'utf8'), cipher.final()]);
  return Buffer.concat([iv, cipher.getAuthTag(), ciphertext]).toString('base64url');
}
export function openFlow(secret: string, value?: string): Flow | null {
  try {
    if (!value || value.length > 4096) return null;
    const bytes = Buffer.from(value, 'base64url'); const cipher = createDecipheriv('aes-256-gcm', createHash('sha256').update(secret).digest(), bytes.subarray(0, 12));
    cipher.setAuthTag(bytes.subarray(12, 28));
    const result = JSON.parse(Buffer.concat([cipher.update(bytes.subarray(28)), cipher.final()]).toString('utf8')) as Flow;
    return Number.isFinite(result.expires) && result.expires > Date.now() && typeof result.nonce === 'string' ? result : null;
  } catch { return null; }
}
