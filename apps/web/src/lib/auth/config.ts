import 'server-only';
import { AuthFailure } from './policy';

export function authConfig() {
  if (process.env.WEB_AUTH_ENABLED !== '1') return null;
  const url = process.env.SUPABASE_URL ?? ''; const key = process.env.SUPABASE_PUBLISHABLE_KEY ?? '';
  const api = process.env.INTERNMATCH_API_URL ?? ''; const origin = process.env.WEB_ORIGIN ?? ''; const secret = process.env.WEB_FLOW_SECRET ?? '';
  try {
    for (const value of [url, api, origin]) {
      const parsed = new URL(value);
      if (parsed.username || parsed.password || parsed.search || parsed.hash) throw new Error();
      if (parsed.protocol !== 'https:' && !(parsed.protocol === 'http:' && ['127.0.0.1', 'localhost'].includes(parsed.hostname))) throw new Error();
    }
    if (new URL(origin).origin !== origin || new URL(url).pathname !== '/' || !new URL(api).pathname.replace(/\/$/, '').endsWith('/api/v1') || secret.length < 32) throw new Error();
    if (key.startsWith('sb_secret_') || !key) throw new Error();
    if (!key.startsWith('sb_publishable_')) { const claims = JSON.parse(Buffer.from(key.split('.')[1] ?? '', 'base64url').toString()); if (claims.role !== 'anon') throw new Error(); }
    return { url: url.replace(/\/$/, ''), key, api: api.replace(/\/$/, ''), origin, secret, secure: origin.startsWith('https:'), emailFlows: process.env.WEB_EMAIL_FLOWS_ENABLED === '1', google: process.env.WEB_GOOGLE_ENABLED === '1' };
  } catch { throw new AuthFailure('notConfigured', 503); }
}
export function requiredConfig() { const config = authConfig(); if (!config) throw new AuthFailure('notConfigured', 503); return config; }
