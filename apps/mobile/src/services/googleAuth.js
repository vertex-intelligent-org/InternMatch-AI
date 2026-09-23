import * as WebBrowser from 'expo-web-browser';
import { supabase } from '../lib/supabase';

export const GOOGLE_OAUTH_REDIRECT_URL = 'internmatch://oauth-callback';

function decodeUrlComponent(value) {
  try {
    return decodeURIComponent(String(value || '').replace(/\+/g, ' '));
  } catch {
    return String(value || '');
  }
}

function parseOAuthParams(url) {
  const result = {};

  const queryIndex = url.indexOf('?');
  const hashIndex = url.indexOf('#');
  const segments = [];

  if (queryIndex >= 0) {
    const queryEnd =
      hashIndex > queryIndex ? hashIndex : url.length;

    segments.push(url.slice(queryIndex + 1, queryEnd));
  }

  if (hashIndex >= 0) {
    segments.push(url.slice(hashIndex + 1));
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

      const key = decodeUrlComponent(rawKey);

      if (key) {
        result[key] = decodeUrlComponent(rawValue);
      }
    }
  }

  return result;
}

async function establishOAuthSession(callbackUrl) {
  const params = parseOAuthParams(callbackUrl);

  if (params.error || params.error_description) {
    throw new Error(
      params.error_description ||
        params.error ||
        'Google authentication failed.'
    );
  }

  if (params.access_token && params.refresh_token) {
    const { data, error } = await supabase.auth.setSession({
      access_token: params.access_token,
      refresh_token: params.refresh_token,
    });

    if (error) {
      throw error;
    }

    if (!data.session?.access_token) {
      throw new Error(
        'Google authentication did not create a valid session.'
      );
    }

    return data.session;
  }

  if (params.code) {
    const { data, error } =
      await supabase.auth.exchangeCodeForSession(params.code);

    if (error) {
      throw error;
    }

    if (!data.session?.access_token) {
      throw new Error(
        'Google authentication did not create a valid session.'
      );
    }

    return data.session;
  }

  throw new Error(
    'Google authentication callback did not contain a session.'
  );
}


function resolveGoogleFullName(session) {
  const metadata =
    session?.user?.user_metadata ?? {};

  const directCandidates = [
    metadata.full_name,
    metadata.name,
    metadata.display_name,
  ];

  for (const value of directCandidates) {
    if (
      typeof value === 'string'
      && value.trim()
    ) {
      return value.trim();
    }
  }

  const combinedName = [
    metadata.given_name,
    metadata.family_name,
  ]
    .filter(
      value =>
        typeof value === 'string'
        && value.trim()
    )
    .map(value => value.trim())
    .join(' ');

  if (combinedName) {
    return combinedName;
  }

  return 'InternMatch User';
}

export async function signInWithGoogle() {
  const { data, error } = await supabase.auth.signInWithOAuth({
    provider: 'google',
    options: {
      redirectTo: GOOGLE_OAUTH_REDIRECT_URL,
      skipBrowserRedirect: true,
    },
  });

  if (error) {
    throw error;
  }

  if (!data?.url) {
    throw new Error(
      'Google authentication URL was not returned.'
    );
  }

  const result = await WebBrowser.openAuthSessionAsync(
    data.url,
    GOOGLE_OAUTH_REDIRECT_URL
  );

  if (result.type === 'cancel' || result.type === 'dismiss') {
    return {
      cancelled: true,
      session: null,
    };
  }

  if (result.type !== 'success' || !result.url) {
    throw new Error(
      'Google authentication did not complete.'
    );
  }

  const session = await establishOAuthSession(result.url);

  return {
    cancelled: false,
    session,
    fullName:
      resolveGoogleFullName(session),
  };
}

export async function signOutGoogle() {
  return;
}
