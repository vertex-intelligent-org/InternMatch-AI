import AsyncStorage from '@react-native-async-storage/async-storage';
import * as StoreReview from 'expo-store-review';

const LAST_REVIEW_REQUEST_KEY =
  '@internmatch_ai/store_review/last_request_at';

const MEANINGFUL_ACTION_COUNT_KEY =
  '@internmatch_ai/store_review/meaningful_action_count';

const MEANINGFUL_ACTION_THRESHOLD = 3;

// Prevent repeated review requests.
const REVIEW_COOLDOWN_MS =
  90 * 24 * 60 * 60 * 1000;

// Intentionally session-only.
// This prevents the review prompt from appearing unexpectedly
// after a cold launch.
let reviewCandidatePending = false;

async function getStoredNumber(key, fallback = 0) {
  try {
    const value = await AsyncStorage.getItem(key);

    if (value === null) {
      return fallback;
    }

    const parsed = Number(value);

    return Number.isFinite(parsed) ? parsed : fallback;
  } catch {
    return fallback;
  }
}

export function hasPendingReviewCandidate() {
  return reviewCandidatePending;
}

export function clearPendingReviewCandidate() {
  reviewCandidatePending = false;
}

export async function requestAppStoreReview() {
  try {
    const available = await StoreReview.isAvailableAsync();

    if (!available) {
      return false;
    }

    const lastRequestAt = await getStoredNumber(
      LAST_REVIEW_REQUEST_KEY,
      0
    );

    if (
      lastRequestAt > 0 &&
      Date.now() - lastRequestAt < REVIEW_COOLDOWN_MS
    ) {
      return false;
    }

    await StoreReview.requestReview();

    // StoreKit / Google Play controls whether the native UI
    // is actually displayed.
    await AsyncStorage.setItem(
      LAST_REVIEW_REQUEST_KEY,
      String(Date.now())
    );

    try {
      await AsyncStorage.removeItem(
        MEANINGFUL_ACTION_COUNT_KEY
      );
    } catch (storageError) {
      console.warn(
        'Failed to clear App Store review action count:',
        storageError
      );
    }

    return true;
  } catch (error) {
    // Review failures must never affect application submission.
    console.warn(
      'Failed to request App Store review:',
      error
    );

    return false;
  }
}

export async function requestAppStoreReviewIfEligible() {
  if (!hasPendingReviewCandidate()) {
    return false;
  }

  return requestAppStoreReview();
}

export async function recordMeaningfulAppAction() {
  try {
    const currentCount = await getStoredNumber(
      MEANINGFUL_ACTION_COUNT_KEY,
      0
    );

    const nextCount = currentCount + 1;

    await AsyncStorage.setItem(
      MEANINGFUL_ACTION_COUNT_KEY,
      String(nextCount)
    );

    if (nextCount >= MEANINGFUL_ACTION_THRESHOLD) {
      reviewCandidatePending = true;
    }

    return nextCount;
  } catch (error) {
    // Review telemetry is non-critical.
    // A storage failure must never turn a successful
    // application submission into a failed submission.
    console.warn(
      'Failed to record meaningful App Store review action:',
      error
    );

    return null;
  }
}