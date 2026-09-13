import type {
  CandidateRevenueCatState,
  EmployerRevenueCatState,
} from './revenueCatService';

export type AccountType = 'intern' | 'employer';

export type PlanId = 'free' | 'pro_student' | 'employer' | 'employer_pro';

export interface PlanInfo {
  id: PlanId;
  accountType: AccountType;
  titleKey: string;
  badgeKey: string;
  badgeLabelKey: string;
  descriptionKey: string;
  pricingKey: string;
  features: string[];
  isCurrent: boolean;
  isPaid: boolean;
  isHighlighted?: boolean;
}

export interface PurchaseState {
  provider: 'revenuecat';
  providerVerified: boolean;
  purchasesAvailable: boolean;
  mode: 'preview' | 'revenuecat';
}

export interface SubscriptionSnapshot {
  accountType: AccountType;
  currentPlan: PlanInfo;
  availablePlans: PlanInfo[];
  entitlements: string[];
  purchaseState: PurchaseState;
  dynamicPriceString?: string | null;
}

export interface BackendSubscriptionState {
  plan: 'free' | 'pro_student' | 'employer_pro';
  is_active: boolean;
}

export const CANDIDATE_FREE_PLAN: PlanInfo = {
  id: 'free',
  accountType: 'intern',
  titleKey: 'plans.candidate.free.title',
  badgeKey: 'components.planBadgeFree',
  badgeLabelKey: 'plans.badges.free',
  descriptionKey: 'plans.candidate.free.description',
  pricingKey: 'plans.pricingPreviewFree',
  features: [
    'plans.candidate.free.feature1',
    'plans.candidate.free.feature2',
    'plans.candidate.free.feature3',
    'plans.candidate.free.feature4',
  ],
  isCurrent: true,
  isPaid: false,
  isHighlighted: false,
};

export const CANDIDATE_PRO_PLAN: PlanInfo = {
  id: 'pro_student',
  accountType: 'intern',
  titleKey: 'plans.candidate.pro.title',
  badgeKey: 'components.planBadgeProStudent',
  badgeLabelKey: 'plans.badges.proStudent',
  descriptionKey: 'plans.candidate.pro.description',
  pricingKey: 'plans.pricingPreview',
  features: [
    'plans.candidate.pro.feature1',
    'plans.candidate.pro.feature2',
    'plans.candidate.pro.feature3',
    'plans.candidate.pro.feature4',
  ],
  isCurrent: false,
  isPaid: true,
  isHighlighted: true,
};

export const EMPLOYER_STANDARD_PLAN: PlanInfo = {
  id: 'employer',
  accountType: 'employer',
  titleKey: 'plans.employer.standard.title',
  badgeKey: 'components.planBadgeEmployer',
  badgeLabelKey: 'plans.badges.employer',
  descriptionKey: 'plans.employer.standard.description',
  pricingKey: 'plans.pricingPreviewFree',
  features: [
    'plans.employer.standard.feature1',
    'plans.employer.standard.feature2',
    'plans.employer.standard.feature3',
    'plans.employer.standard.feature4',
    'plans.employer.standard.feature5',
    'plans.employer.standard.feature6',
  ],
  isCurrent: true,
  isPaid: false,
  isHighlighted: false,
};

export const EMPLOYER_PRO_PLAN: PlanInfo = {
  id: 'employer_pro',
  accountType: 'employer',
  titleKey: 'plans.employer.pro.title',
  badgeKey: 'components.planBadgeEmployerPro',
  badgeLabelKey: 'plans.badges.employerPro',
  descriptionKey: 'plans.employer.pro.description',
  pricingKey: 'plans.pricingPreview',
  features: [
    'plans.employer.pro.feature1',
    'plans.employer.pro.feature2',
    'plans.employer.pro.feature3',
    'plans.employer.pro.feature4',
    'plans.employer.pro.feature5',
    'plans.employer.pro.feature6',
    'plans.employer.pro.feature7',
    'plans.employer.pro.feature8',
    'plans.employer.pro.feature9',
  ],
  isCurrent: false,
  isPaid: true,
  isHighlighted: true,
};

/**
 * Normalizes account type input to a valid AccountType value ('intern' | 'employer').
 * Defaults to 'intern' for undefined, null, or unverified values.
 */
export function normalizeAccountType(accountType?: string | null): AccountType {
  if (!accountType || typeof accountType !== 'string') {
    return 'intern';
  }
  const clean = accountType.trim().toLowerCase();
  if (clean === 'employer') {
    return 'employer';
  }
  return 'intern';
}

/**
 * Returns baseline preview entitlements for an account type.
 */
export function getBaselineEntitlements(accountType: AccountType): string[] {
  if (accountType === 'employer') {
    return [];
  }
  return ['internship_discovery', 'candidate_profile', 'application_tracking'];
}

/**
 * Central pure domain subscription snapshot provider.
 * Maps account type, RevenueCat purchase metadata, and backend-authoritative access state into an immutable subscription snapshot.
 */
export function getSubscriptionSnapshot(
  rawAccountType?: string | null,
  candidateRevenueCatState?: CandidateRevenueCatState | null,
  backendSubscriptionState?: BackendSubscriptionState | null,
  employerRevenueCatState?: EmployerRevenueCatState | null
): SubscriptionSnapshot {
  const accountType = normalizeAccountType(rawAccountType);

  if (accountType === 'employer') {
    const providerVerified = Boolean(
      employerRevenueCatState?.providerVerified
    );
    const purchasesAvailable = Boolean(
      employerRevenueCatState?.purchasesAvailable
    );
    const isPro =
      backendSubscriptionState?.plan === 'employer_pro' &&
      backendSubscriptionState?.is_active === true;

    const purchaseState: PurchaseState = {
      provider: 'revenuecat',
      providerVerified,
      purchasesAvailable,
      mode: employerRevenueCatState ? 'revenuecat' : 'preview',
    };

    const standardPlan: PlanInfo = {
      ...EMPLOYER_STANDARD_PLAN,
      isCurrent: !isPro,
    };

    const proPlan: PlanInfo = {
      ...EMPLOYER_PRO_PLAN,
      isCurrent: isPro,
    };

    return {
      accountType: 'employer',
      currentPlan: isPro ? proPlan : standardPlan,
      availablePlans: [standardPlan, proPlan],
      entitlements: isPro ? ['pro_employer'] : [],
      purchaseState,
      dynamicPriceString:
        employerRevenueCatState?.priceString || null,
    };
  }

  // Candidate purchase availability and localized price come from RevenueCat.
  // Product authorization comes only from backend subscription state.
  const providerVerified = Boolean(
    candidateRevenueCatState?.providerVerified
  );
  const purchasesAvailable = Boolean(
    candidateRevenueCatState?.purchasesAvailable
  );
  const isPro =
    backendSubscriptionState?.plan === 'pro_student' &&
    backendSubscriptionState?.is_active === true;

  const purchaseState: PurchaseState = {
    provider: 'revenuecat',
    providerVerified,
    purchasesAvailable,
    mode: candidateRevenueCatState ? 'revenuecat' : 'preview',
  };

  const freePlan: PlanInfo = {
    ...CANDIDATE_FREE_PLAN,
    isCurrent: !isPro,
  };

  const proPlan: PlanInfo = {
    ...CANDIDATE_PRO_PLAN,
    isCurrent: isPro,
  };

  const entitlements = isPro
    ? [...getBaselineEntitlements('intern'), 'pro_student']
    : getBaselineEntitlements('intern');

  return {
    accountType: 'intern',
    currentPlan: isPro ? proPlan : freePlan,
    availablePlans: [freePlan, proPlan],
    entitlements,
    purchaseState,
    dynamicPriceString:
      candidateRevenueCatState?.priceString || null,
  };
}
