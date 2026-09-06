import { supabase } from '../lib/supabase';

export const PASSWORD_RESET_NATIVE_REDIRECT_URL =
  'internmatch://reset-password';

export const PASSWORD_RESET_WEB_REDIRECT_URL =
  'https://internmatch.college/auth/reset-password';

export const PASSWORD_RESET_REDIRECT_URL =
  __DEV__
    ? PASSWORD_RESET_NATIVE_REDIRECT_URL
    : PASSWORD_RESET_WEB_REDIRECT_URL;

export type PasswordRecoveryStatus =
  | 'not_recovery'
  | 'success'
  | 'expired_or_invalid'
  | 'session_error';

export interface PasswordRecoveryResult {
  status: PasswordRecoveryStatus;
  error?: string;
}

/**
 * Checks whether the incoming URL is an InternMatch password recovery deep-link target.
 * Safely accepts both internmatch://reset-password and internmatch:///reset-password targets.
 */
export function isPasswordRecoveryUrl(url: string | null | undefined): boolean {
  if (!url || typeof url !== 'string') {
    return false;
  }

  const normalizedUrl = url.trim().toLowerCase();

  if (!normalizedUrl) {
    return false;
  }

  const expectedUrls = [
    PASSWORD_RESET_NATIVE_REDIRECT_URL,
    PASSWORD_RESET_WEB_REDIRECT_URL,
  ].map((value) => value.toLowerCase());

  return expectedUrls.some(
    (expectedUrl) =>
      normalizedUrl === expectedUrl ||
      normalizedUrl.startsWith(`${expectedUrl}?`) ||
      normalizedUrl.startsWith(`${expectedUrl}#`)
  );
}

/**
 * Extracts query and fragment parameters from a deep-link URL.
 */
function extractUrlParams(url: string): { [key: string]: string } {
  const params: { [key: string]: string } = {};

  try {
    const queryIndex = url.indexOf('?');
    const hashIndex = url.indexOf('#');

    let queryString = '';
    let hashString = '';

    if (queryIndex !== -1) {
      if (hashIndex !== -1 && hashIndex > queryIndex) {
        queryString = url.substring(queryIndex + 1, hashIndex);
      } else {
        queryString = url.substring(queryIndex + 1);
      }
    }

    if (hashIndex !== -1) {
      hashString = url.substring(hashIndex + 1);
      const hashQueryIndex = hashString.indexOf('?');
      if (hashQueryIndex !== -1) {
        hashString = hashString.substring(0, hashQueryIndex);
      }
    }

    const parseParamString = (str: string) => {
      if (!str) return;
      const searchParams = new URLSearchParams(str);
      searchParams.forEach((value, key) => {
        if (key && !params[key]) {
          params[key] = value;
        }
      });
    };

    parseParamString(queryString);
    parseParamString(hashString);
  } catch {
    const matchPairs = url.matchAll(/([?#&])([^=&?#]+)=([^&#]*)/g);
    for (const match of matchPairs) {
      const key = decodeURIComponent(match[2]);
      const value = decodeURIComponent(match[3]);
      if (key && !params[key]) {
        params[key] = value;
      }
    }
  }

  return params;
}

/**
 * Consumes an InternMatch password recovery deep-link URL.
 * Exchanges PKCE auth code or implicit tokens for an authenticated Supabase session.
 * Never logs or persists tokens or recovery URLs.
 */
export async function consumePasswordRecoveryUrl(
  url: string | null | undefined
): Promise<PasswordRecoveryResult> {
  if (!isPasswordRecoveryUrl(url)) {
    return { status: 'not_recovery' };
  }

  const rawUrl = url!.trim();
  const params = extractUrlParams(rawUrl);

  const errorParam = params.error || params.error_code;
  const errorDescription = params.error_description || params.error;

  // 1. Detect auth error parameters before attempting session creation
  if (errorParam) {
    return {
      status: 'expired_or_invalid',
      error: typeof errorDescription === 'string' ? errorDescription : undefined,
    };
  }

  const tokenHash = params.token_hash;
  const recoveryType = params.type;
  const code = params.code;
  const accessToken = params.access_token;
  const refreshToken = params.refresh_token;

  // 2. Token-hash recovery flow: verify the one-time credential
  // directly with Supabase and establish an authenticated session.
  if (tokenHash) {
    if (recoveryType !== 'recovery') {
      return {
        status: 'expired_or_invalid',
        error: 'Invalid recovery type',
      };
    }

    try {
      const { data, error } = await supabase.auth.verifyOtp({
        token_hash: tokenHash,
        type: 'recovery',
      });

      if (error) {
        const errorMsg = error.message?.toLowerCase() || '';

        if (
          errorMsg.includes('expired') ||
          errorMsg.includes('invalid') ||
          errorMsg.includes('token') ||
          errorMsg.includes('otp')
        ) {
          return {
            status: 'expired_or_invalid',
            error: error.message,
          };
        }

        return {
          status: 'session_error',
          error: error.message,
        };
      }

      if (data?.session?.access_token && data?.user) {
        return { status: 'success' };
      }

      return {
        status: 'session_error',
        error: 'Missing session or user after recovery verification',
      };
    } catch {
      return { status: 'session_error' };
    }
  }

  // 3. PKCE recovery flow: code present
  if (code) {
    try {
      const { data, error } = await supabase.auth.exchangeCodeForSession(code);
      if (error) {
        const errorMsg = error.message?.toLowerCase() || '';
        if (
          errorMsg.includes('expired') ||
          errorMsg.includes('invalid') ||
          errorMsg.includes('grant') ||
          errorMsg.includes('pkce')
        ) {
          return { status: 'expired_or_invalid', error: error.message };
        }
        return { status: 'session_error', error: error.message };
      }

      if (data?.session?.access_token && data?.user) {
        return { status: 'success' };
      }

      return { status: 'session_error', error: 'Missing session or user after code exchange' };
    } catch {
      return { status: 'session_error' };
    }
  }

  // 4. Implicit recovery flow: access_token + refresh_token
  if (accessToken) {
    // Never accept an access token without a refresh token
    if (!refreshToken) {
      return { status: 'expired_or_invalid', error: 'Missing refresh token' };
    }

    try {
      const { data, error } = await supabase.auth.setSession({
        access_token: accessToken,
        refresh_token: refreshToken,
      });

      if (error) {
        const errorMsg = error.message?.toLowerCase() || '';
        if (
          errorMsg.includes('expired') ||
          errorMsg.includes('invalid') ||
          errorMsg.includes('jwt')
        ) {
          return { status: 'expired_or_invalid', error: error.message };
        }
        return { status: 'session_error', error: error.message };
      }

      if (data?.session?.access_token && data?.user) {
        return { status: 'success' };
      }

      return { status: 'session_error', error: 'Missing session or user after setSession' };
    } catch {
      return { status: 'session_error' };
    }
  }

  // No code and no tokens in recovery URL
  return { status: 'expired_or_invalid', error: 'Missing recovery credentials in URL' };
}
