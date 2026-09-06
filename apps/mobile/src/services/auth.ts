import {
  AuthResponse,
  AuthTokenResponsePassword,
  UserResponse,
} from '@supabase/supabase-js';
import { supabase } from '../lib/supabase';

export const EMAIL_CONFIRMATION_NATIVE_REDIRECT_URL =
  'internmatch://auth-confirmed';

export const EMAIL_CONFIRMATION_WEB_REDIRECT_URL =
  'https://internmatch.college/auth/confirmed';

export const EMAIL_CONFIRMATION_REDIRECT_URL =
  __DEV__
    ? EMAIL_CONFIRMATION_NATIVE_REDIRECT_URL
    : EMAIL_CONFIRMATION_WEB_REDIRECT_URL;

function decodeAuthCallbackValue(value: string): string {
  try {
    return decodeURIComponent(value.replace(/\+/g, ' '));
  } catch {
    return value;
  }
}

function extractAuthCallbackParams(url: string): Record<string, string> {
  const params: Record<string, string> = {};
  const queryIndex = url.indexOf('?');
  const hashIndex = url.indexOf('#');
  const segments: string[] = [];

  if (queryIndex >= 0) {
    const queryEnd =
      hashIndex > queryIndex ? hashIndex : url.length;

    segments.push(
      url.slice(queryIndex + 1, queryEnd)
    );
  }

  if (hashIndex >= 0) {
    segments.push(
      url.slice(hashIndex + 1)
    );
  }

  for (const segment of segments) {
    for (const pair of segment.split('&')) {
      if (!pair) continue;

      const separatorIndex = pair.indexOf('=');

      const rawKey =
        separatorIndex >= 0
          ? pair.slice(0, separatorIndex)
          : pair;

      const rawValue =
        separatorIndex >= 0
          ? pair.slice(separatorIndex + 1)
          : '';

      const key = decodeAuthCallbackValue(rawKey);

      if (key && !params[key]) {
        params[key] = decodeAuthCallbackValue(rawValue);
      }
    }
  }

  return params;
}

/**
 * Establish a persisted Supabase session from a native auth callback.
 * Supports implicit access/refresh tokens and PKCE authorization codes.
 * Never logs or persists callback URLs or raw credentials.
 */
export async function establishSessionFromAuthCallbackUrl(
  url: string
): Promise<boolean> {
  if (!url || typeof url !== 'string') {
    return false;
  }

  const params = extractAuthCallbackParams(url.trim());

  if (params.error || params.error_description) {
    return false;
  }

  const accessToken = params.access_token;
  const refreshToken = params.refresh_token;

  if (accessToken || refreshToken) {
    if (!accessToken || !refreshToken) {
      return false;
    }

    const { data, error } = await supabase.auth.setSession({
      access_token: accessToken,
      refresh_token: refreshToken,
    });

    return (
      !error &&
      Boolean(data.session?.access_token)
    );
  }

  if (params.code) {
    const { data, error } =
      await supabase.auth.exchangeCodeForSession(
        params.code
      );

    return (
      !error &&
      Boolean(data.session?.access_token)
    );
  }

  return false;
}

export type SignUpMetadata = {
  full_name?: string;
  department?: string;
  account_type?: string;
  [key: string]: unknown;
};

/**
 * Classifies whether an auth error represents an unconfirmed email error.
 */
export function isEmailNotConfirmedError(error: unknown): boolean {
  if (!error) return false;
  if (typeof error === 'object') {
    const errObj = error as Record<string, unknown>;
    if (errObj.code === 'email_not_confirmed') {
      return true;
    }
    const message = typeof errObj.message === 'string' ? errObj.message.toLowerCase() : '';
    if (message.includes('email not confirmed')) {
      return true;
    }
  }
  return false;
}

/**
 * Classifies whether an auth error represents a rate limit / throttling error.
 */
export function isAuthRateLimitError(error: unknown): boolean {
  if (!error) return false;
  if (typeof error === 'object') {
    const errObj = error as Record<string, unknown>;
    if (errObj.status === 429) {
      return true;
    }
    if (
      errObj.code === 'over_email_send_rate_limit' ||
      errObj.code === 'rate_limit'
    ) {
      return true;
    }
    const message = typeof errObj.message === 'string' ? errObj.message.toLowerCase() : '';
    if (
      message.includes('over_email_send_rate_limit') ||
      message.includes('rate limit') ||
      message.includes('rate_limit') ||
      message.includes('too many requests')
    ) {
      return true;
    }
  }
  return false;
}

/**
 * Sign up a new user using email and password credentials via Supabase Auth.
 * Accepts optional user metadata (e.g. full_name, department, account_type) for bootstrap.
 */
export async function signUpWithEmail(
  email: string,
  password: string,
  metadata?: SignUpMetadata
): Promise<AuthResponse> {
  return await supabase.auth.signUp({
    email,
    password,
    options: {
      ...(metadata ? { data: metadata } : {}),
      emailRedirectTo: EMAIL_CONFIRMATION_REDIRECT_URL,
    },
  });
}

/**
 * Resend the signup confirmation email to the specified user email address.
 * Uses the canonical InternMatch signup confirmation redirect.
 */
export async function resendSignupConfirmation(email: string) {
  return await supabase.auth.resend({
    type: 'signup',
    email,
    options: {
      emailRedirectTo: EMAIL_CONFIRMATION_REDIRECT_URL,
    },
  });
}

/**
 * Sign in an existing user using email and password credentials via Supabase Auth.
 */
export async function signInWithEmail(
  email: string,
  password: string
): Promise<AuthTokenResponsePassword> {
  return await supabase.auth.signInWithPassword({ email, password });
}

/**
 * Sign out the currently authenticated user and clear session tokens.
 */
export async function signOut(): Promise<{ error: Error | null }> {
  return await supabase.auth.signOut();
}

/**
 * Retrieve the current active Supabase authentication session object.
 */
export async function getCurrentSession() {
  return await supabase.auth.getSession();
}

/**
 * Retrieve the current authenticated user identity details from Supabase Auth.
 */
export async function getCurrentUser(): Promise<UserResponse> {
  return await supabase.auth.getUser();
}

/**
 * Send a password-reset email to the specified user email address.
 */
export async function sendPasswordResetEmail(
  email: string,
  redirectTo?: string
) {
  return await supabase.auth.resetPasswordForEmail(
    email,
    redirectTo ? { redirectTo } : undefined
  );
}

/**
 * Update the password credential for the currently authenticated active session.
 */
export async function updatePassword(password: string): Promise<UserResponse> {
  return await supabase.auth.updateUser({ password });
}
