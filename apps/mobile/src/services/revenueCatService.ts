import { Platform } from 'react-native';
import Purchases, {
  CustomerInfo,
  PurchasesOfferings,
  PurchasesPackage,
  PURCHASES_ERROR_CODE,
} from 'react-native-purchases';

export const REVENUECAT_ENTITLEMENT_ID = 'pro_student';
export const REVENUECAT_OFFERING_ID = 'default';
export const REVENUECAT_MONTHLY_PACKAGE_ID = '$rc_monthly';
export const REVENUECAT_PRODUCT_ID = 'internmatch_pro_student_monthly';

export interface RevenueCatRuntimeState {
  configured: boolean;
  identifiedUserId: string | null;
  restorePurchasesSupported: boolean;
  reason?: string | null;
}

export interface CandidateRevenueCatState {
  providerVerified: boolean;
  purchasesAvailable: boolean;
  proStudentActive: boolean;
  activeEntitlementIds: string[];
  offeringIdentifier: string | null;
  packageIdentifier: string | null;
  productIdentifier: string | null;
  priceString: string | null;
  reason: string | null;
}

export interface PurchaseActionResult {
  success: boolean;
  cancelled: boolean;
  proStudentActive: boolean;
  candidateState: CandidateRevenueCatState;
  reason: string | null;
}

export interface RestoreActionResult {
  success: boolean;
  proStudentActive: boolean;
  candidateState: CandidateRevenueCatState;
  reason: string | null;
}

export const DEFAULT_CANDIDATE_REVENUECAT_STATE: CandidateRevenueCatState = {
  providerVerified: false,
  purchasesAvailable: false,
  proStudentActive: false,
  activeEntitlementIds: [],
  offeringIdentifier: null,
  packageIdentifier: null,
  productIdentifier: null,
  priceString: null,
  reason: null,
};

let isConfigured = false;
let currentIdentifiedUserId: string | null = null;
let configurationReason: string | null = null;
let lastResolvedPackage: PurchasesPackage | null = null;

function normalizePublicApiKey(
  value: string | undefined
): string {
  return typeof value === 'string'
    ? value.trim()
    : '';
}

function getPublicApiKey(): string {
  const developmentKey = normalizePublicApiKey(
    process.env.EXPO_PUBLIC_REVENUECAT_API_KEY
  );

  if (__DEV__ && developmentKey) {
    return developmentKey;
  }

  const platformKey =
    Platform.OS === 'ios'
      ? normalizePublicApiKey(
          process.env.EXPO_PUBLIC_REVENUECAT_IOS_API_KEY
        )
      : Platform.OS === 'android'
        ? normalizePublicApiKey(
            process.env.EXPO_PUBLIC_REVENUECAT_ANDROID_API_KEY
          )
        : '';

  if (!platformKey || platformKey.startsWith('test_')) {
    return '';
  }

  return platformKey;
}

/**
 * Returns true if the configured RevenueCat API key supports store-level purchase restoration.
 * RevenueCat Test Store keys (prefixed with "test_") do not support restorePurchases.
 */
export function isRestorePurchasesSupported(): boolean {
  if (!isConfigured) {
    return false;
  }
  const apiKey = getPublicApiKey();
  if (!apiKey || apiKey.startsWith('test_')) {
    return false;
  }
  return true;
}

/**
 * Matches the canonical Pro Student product across supported stores.
 *
 * Test Store and App Store use the canonical product identifier directly.
 * Modern Google Play subscriptions append the base-plan identifier:
 * <subscription-id>:<base-plan-id>.
 */
export function matchesCanonicalRevenueCatProductIdentifier(
  productIdentifier: string | null | undefined
): boolean {
  const normalizedIdentifier =
    typeof productIdentifier === 'string'
      ? productIdentifier.trim()
      : '';

  if (normalizedIdentifier === REVENUECAT_PRODUCT_ID) {
    return true;
  }

  return (
    Platform.OS === 'android' &&
    normalizedIdentifier.startsWith(
      `${REVENUECAT_PRODUCT_ID}:`
    ) &&
    normalizedIdentifier.length >
      REVENUECAT_PRODUCT_ID.length + 1
  );
}

/**
 * Resolves the canonical candidate package ($rc_monthly / internmatch_pro_student_monthly)
 * from the default offering.
 */
export function resolveCanonicalCandidatePackage(
  offerings: PurchasesOfferings | null | undefined
): { package: PurchasesPackage | null; reason: string | null } {
  if (!offerings) {
    return { package: null, reason: 'offerings_empty' };
  }

  let offering = offerings.all?.[REVENUECAT_OFFERING_ID];
  if (!offering && offerings.current?.identifier === REVENUECAT_OFFERING_ID) {
    offering = offerings.current;
  }

  if (!offering || offering.identifier !== REVENUECAT_OFFERING_ID) {
    return { package: null, reason: 'offering_not_found' };
  }

  const availablePackages = offering.availablePackages || [];
  let matchingPackage: PurchasesPackage | null = null;

  for (const pkg of availablePackages) {
    if (
      pkg.identifier === REVENUECAT_MONTHLY_PACKAGE_ID &&
      matchesCanonicalRevenueCatProductIdentifier(pkg.product?.identifier)
    ) {
      matchingPackage = pkg;
      break;
    }
  }

  if (
    !matchingPackage &&
    offering.monthly?.identifier === REVENUECAT_MONTHLY_PACKAGE_ID &&
    matchesCanonicalRevenueCatProductIdentifier(offering.monthly?.product?.identifier)
  ) {
    matchingPackage = offering.monthly;
  }

  if (
    !matchingPackage ||
    matchingPackage.identifier !== REVENUECAT_MONTHLY_PACKAGE_ID ||
    !matchesCanonicalRevenueCatProductIdentifier(matchingPackage.product?.identifier)
  ) {
    return { package: null, reason: 'package_not_found' };
  }

  lastResolvedPackage = matchingPackage;
  return { package: matchingPackage, reason: null };
}

/**
 * Normalizes CustomerInfo and package details into an application-facing state object.
 */
export function normalizeCandidateState(
  customerInfo: CustomerInfo | null,
  resolvedPackage: PurchasesPackage | null,
  baseReason?: string | null
): CandidateRevenueCatState {
  const providerVerified = customerInfo !== null;
  const purchasesAvailable = resolvedPackage !== null;

  let activeEntitlementIds: string[] = [];
  let proStudentActive = false;

  if (customerInfo) {
    activeEntitlementIds = Object.keys(customerInfo.entitlements?.active || {});
    proStudentActive = Boolean(
      customerInfo.entitlements?.active?.[REVENUECAT_ENTITLEMENT_ID]?.isActive ??
        customerInfo.entitlements?.active?.[REVENUECAT_ENTITLEMENT_ID]
    );
  }

  const reason =
    baseReason ||
    (!providerVerified
      ? 'customer_info_fetch_failed'
      : !purchasesAvailable
      ? 'purchases_unavailable'
      : null);

  return {
    providerVerified,
    purchasesAvailable,
    proStudentActive,
    activeEntitlementIds,
    offeringIdentifier:
      resolvedPackage?.offeringIdentifier ||
      (resolvedPackage ? REVENUECAT_OFFERING_ID : null),
    packageIdentifier: resolvedPackage?.identifier || null,
    productIdentifier: resolvedPackage?.product?.identifier || null,
    priceString: resolvedPackage?.product?.priceString || null,
    reason,
  };
}

/**
 * Initializes the RevenueCat SDK exactly once using the public API key.
 * If an authenticated user ID is provided, configures with that ID; otherwise configures anonymously.
 * If already configured, delegates synchronization to syncRevenueCatUser.
 */
export async function initializeRevenueCat(
  appUserId?: string | null
): Promise<RevenueCatRuntimeState> {
  if (isConfigured) {
    return await syncRevenueCatUser(appUserId);
  }

  const apiKey = getPublicApiKey();
  if (!apiKey) {
    configurationReason = 'missing_api_key';
    return getRevenueCatRuntimeState();
  }

  const normalizedUserId =
    typeof appUserId === 'string' && appUserId.trim() ? appUserId.trim() : null;

  try {
    Purchases.configure({
      apiKey,
      appUserID: normalizedUserId || undefined,
    });
    isConfigured = true;
    currentIdentifiedUserId = normalizedUserId;
    configurationReason = null;
  } catch {
    isConfigured = false;
    currentIdentifiedUserId = null;
    configurationReason = 'configuration_failed';
  }

  return getRevenueCatRuntimeState();
}

/**
 * Synchronizes the RevenueCat identified user with the active Supabase auth state.
 */
export async function syncRevenueCatUser(
  appUserId?: string | null
): Promise<RevenueCatRuntimeState> {
  if (!isConfigured) {
    return await initializeRevenueCat(appUserId);
  }

  const normalizedUserId =
    typeof appUserId === 'string' && appUserId.trim() ? appUserId.trim() : null;

  if (normalizedUserId) {
    if (currentIdentifiedUserId === normalizedUserId) {
      return getRevenueCatRuntimeState();
    }

    try {
      await Purchases.logIn(normalizedUserId);
      currentIdentifiedUserId = normalizedUserId;
      configurationReason = null;
    } catch {
      configurationReason = 'identity_sync_failed';
    }
  } else {
    if (currentIdentifiedUserId === null) {
      return getRevenueCatRuntimeState();
    }

    try {
      await Purchases.logOut();
      currentIdentifiedUserId = null;
      configurationReason = null;
    } catch {
      configurationReason = 'identity_sync_failed';
    }
  }

  return getRevenueCatRuntimeState();
}

/**
 * Returns the current RevenueCat runtime configuration and user identification state.
 */
export function getRevenueCatRuntimeState(): RevenueCatRuntimeState {
  return {
    configured: isConfigured,
    identifiedUserId: currentIdentifiedUserId,
    restorePurchasesSupported: isRestorePurchasesSupported(),
    reason: configurationReason,
  };
}

/**
 * Fetches current CustomerInfo and Offerings to produce the normalized candidate state.
 */
export async function getCandidateRevenueCatState(): Promise<CandidateRevenueCatState> {
  if (!isConfigured) {
    return {
      ...DEFAULT_CANDIDATE_REVENUECAT_STATE,
      reason: 'unconfigured',
    };
  }

  if (!currentIdentifiedUserId) {
    return {
      ...DEFAULT_CANDIDATE_REVENUECAT_STATE,
      reason: 'unauthenticated',
    };
  }

  let customerInfo: CustomerInfo | null = null;
  let customerInfoFailed = false;

  try {
    customerInfo = await Purchases.getCustomerInfo();
  } catch {
    customerInfoFailed = true;
  }

  let resolvedPackage: PurchasesPackage | null = null;
  let offeringsReason: string | null = null;

  try {
    const offerings = await Purchases.getOfferings();
    const resolved = resolveCanonicalCandidatePackage(offerings);
    resolvedPackage = resolved.package;
    offeringsReason = resolved.reason;
  } catch {
    offeringsReason = 'offerings_fetch_failed';
  }

  const baseReason = customerInfoFailed
    ? 'customer_info_fetch_failed'
    : !resolvedPackage
    ? offeringsReason || 'purchases_unavailable'
    : null;

  return normalizeCandidateState(customerInfo, resolvedPackage, baseReason);
}

/**
 * Purchases the canonical Pro Student monthly package.
 */
export async function purchaseProStudentMonthly(): Promise<PurchaseActionResult> {
  if (!isConfigured) {
    return {
      success: false,
      cancelled: false,
      proStudentActive: false,
      candidateState: {
        ...DEFAULT_CANDIDATE_REVENUECAT_STATE,
        reason: 'unconfigured',
      },
      reason: 'unconfigured',
    };
  }

  if (!currentIdentifiedUserId) {
    return {
      success: false,
      cancelled: false,
      proStudentActive: false,
      candidateState: {
        ...DEFAULT_CANDIDATE_REVENUECAT_STATE,
        reason: 'unauthenticated',
      },
      reason: 'unauthenticated',
    };
  }

  let pkg = lastResolvedPackage;

  if (!pkg) {
    try {
      const offerings = await Purchases.getOfferings();
      const resolved = resolveCanonicalCandidatePackage(offerings);
      pkg = resolved.package;
    } catch {
      // Handled below if pkg remains null
    }
  }

  if (!pkg) {
    const fallbackState = await getCandidateRevenueCatState();
    return {
      success: false,
      cancelled: false,
      proStudentActive: fallbackState.proStudentActive,
      candidateState: fallbackState,
      reason: 'package_not_found',
    };
  }

  try {
    const purchaseResult = await Purchases.purchasePackage(pkg);
    const updatedCustomerInfo = purchaseResult.customerInfo;
    const candidateState = normalizeCandidateState(updatedCustomerInfo, pkg, null);

    if (candidateState.proStudentActive) {
      return {
        success: true,
        cancelled: false,
        proStudentActive: true,
        candidateState,
        reason: null,
      };
    }

    return {
      success: false,
      cancelled: false,
      proStudentActive: false,
      candidateState,
      reason: 'entitlement_not_active',
    };
  } catch (error: unknown) {
    const errorCode =
      typeof error === 'object' &&
      error !== null &&
      'code' in error
        ? error.code
        : undefined;

    const userCancelled =
      typeof error === 'object' &&
      error !== null &&
      'userCancelled' in error
        ? error.userCancelled
        : undefined;

    const isCancelled = Boolean(
      errorCode === PURCHASES_ERROR_CODE.PURCHASE_CANCELLED_ERROR ||
        errorCode === '1' ||
        errorCode === 1 ||
        userCancelled === true
    );

    const fallbackState = await getCandidateRevenueCatState();

    return {
      success: false,
      cancelled: isCancelled,
      proStudentActive: fallbackState.proStudentActive,
      candidateState: fallbackState,
      reason: isCancelled ? 'purchase_cancelled' : 'purchase_failed',
    };
  }
}

/**
 * Restores previous purchases for the authenticated user.
 */
export async function restorePurchases(): Promise<RestoreActionResult> {
  if (!isConfigured) {
    return {
      success: false,
      proStudentActive: false,
      candidateState: {
        ...DEFAULT_CANDIDATE_REVENUECAT_STATE,
        reason: 'unconfigured',
      },
      reason: 'unconfigured',
    };
  }

  if (!currentIdentifiedUserId) {
    return {
      success: false,
      proStudentActive: false,
      candidateState: {
        ...DEFAULT_CANDIDATE_REVENUECAT_STATE,
        reason: 'unauthenticated',
      },
      reason: 'unauthenticated',
    };
  }

  if (!isRestorePurchasesSupported()) {
    const fallbackState = await getCandidateRevenueCatState();
    return {
      success: false,
      proStudentActive: fallbackState.proStudentActive,
      candidateState: fallbackState,
      reason: 'restore_unsupported_test_store',
    };
  }

  try {
    const customerInfo = await Purchases.restorePurchases();
    const candidateState = normalizeCandidateState(
      customerInfo,
      lastResolvedPackage,
      null
    );

    return {
      success: true,
      proStudentActive: candidateState.proStudentActive,
      candidateState,
      reason: null,
    };
  } catch {
    const fallbackState = await getCandidateRevenueCatState();
    return {
      success: false,
      proStudentActive: fallbackState.proStudentActive,
      candidateState: fallbackState,
      reason: 'restore_failed',
    };
  }
}

export type CustomerInfoCallback = (state: {
  providerVerified: boolean;
  proStudentActive: boolean;
  activeEntitlementIds: string[];
}) => void;

/**
 * Registers a listener for RevenueCat CustomerInfo updates.
 * Returns an unsubscribe function.
 */
export function addRevenueCatCustomerInfoListener(
  callback: CustomerInfoCallback
): () => void {
  const listener = (customerInfo: CustomerInfo) => {
    const activeEntitlementIds = Object.keys(customerInfo.entitlements?.active || {});
    const proStudentActive = Boolean(
      customerInfo.entitlements?.active?.[REVENUECAT_ENTITLEMENT_ID]?.isActive ??
        customerInfo.entitlements?.active?.[REVENUECAT_ENTITLEMENT_ID]
    );

    callback({
      providerVerified: true,
      proStudentActive,
      activeEntitlementIds,
    });
  };

  Purchases.addCustomerInfoUpdateListener(listener);

  return () => {
    Purchases.removeCustomerInfoUpdateListener(listener);
  };
}
