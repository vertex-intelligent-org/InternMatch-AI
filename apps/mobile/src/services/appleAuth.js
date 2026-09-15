import { Platform } from 'react-native';
import * as AppleAuthentication from 'expo-apple-authentication';
import * as Crypto from 'expo-crypto';
import { supabase } from '../lib/supabase';

function normalizeMetadata(metadata) {
  const result = {};

  if (!metadata || typeof metadata !== 'object') {
    return result;
  }

  for (const [key, value] of Object.entries(metadata)) {
    if (typeof value === 'string') {
      const normalizedValue = value.trim();

      if (normalizedValue) {
        result[key] = normalizedValue;
      }
    }
  }

  return result;
}

function getAppleFullName(fullName) {
  if (!fullName) {
    return '';
  }

  return [
    fullName.givenName,
    fullName.middleName,
    fullName.familyName,
  ]
    .filter(
      value =>
        typeof value === 'string' &&
        value.trim()
    )
    .map(value => value.trim())
    .join(' ');
}

function isCancelledAppleRequest(error) {
  return (
    error &&
    typeof error === 'object' &&
    error.code === 'ERR_REQUEST_CANCELED'
  );
}

export async function signInWithApple(metadata = {}) {
  if (Platform.OS !== 'ios') {
    return {
      cancelled: false,
      unavailable: true,
      session: null,
      authorizationCode: null,
    };
  }

  const available =
    await AppleAuthentication.isAvailableAsync();

  if (!available) {
    return {
      cancelled: false,
      unavailable: true,
      session: null,
      authorizationCode: null,
    };
  }

  const rawNonce = Crypto.randomUUID();

  const hashedNonce =
    await Crypto.digestStringAsync(
      Crypto.CryptoDigestAlgorithm.SHA256,
      rawNonce
    );

  let credential;

  try {
    credential =
      await AppleAuthentication.signInAsync({
        requestedScopes: [
          AppleAuthentication.AppleAuthenticationScope.FULL_NAME,
          AppleAuthentication.AppleAuthenticationScope.EMAIL,
        ],
        nonce: hashedNonce,
      });
  } catch (error) {
    if (isCancelledAppleRequest(error)) {
      return {
        cancelled: true,
        unavailable: false,
        session: null,
      authorizationCode: null,
      };
    }

    throw error;
  }

  if (!credential.identityToken) {
    throw new Error(
      'Apple authentication did not return an identity token.'
    );
  }

  const { data, error } =
    await supabase.auth.signInWithIdToken({
      provider: 'apple',
      token: credential.identityToken,
      nonce: rawNonce,
    });

  if (error) {
    throw error;
  }

  if (!data.session?.access_token) {
    throw new Error(
      'Apple authentication did not create a valid session.'
    );
  }

  const userMetadata = normalizeMetadata(metadata);
  const appleFullName =
    getAppleFullName(credential.fullName);

  if (!userMetadata.full_name && appleFullName) {
    userMetadata.full_name = appleFullName;
  }

  const givenName =
    credential.fullName?.givenName;

  const familyName =
    credential.fullName?.familyName;

  if (
    typeof givenName === 'string' &&
    givenName.trim()
  ) {
    userMetadata.given_name =
      givenName.trim();
  }

  if (
    typeof familyName === 'string' &&
    familyName.trim()
  ) {
    userMetadata.family_name =
      familyName.trim();
  }

  if (Object.keys(userMetadata).length > 0) {
    const { error: metadataError } =
      await supabase.auth.updateUser({
        data: userMetadata,
      });

    if (metadataError) {
      await supabase.auth.signOut();
      throw metadataError;
    }
  }

  return {
    cancelled: false,
    unavailable: false,
    session: data.session,
    authorizationCode:
      credential.authorizationCode || null,
  };
}
