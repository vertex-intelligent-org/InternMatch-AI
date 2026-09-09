import React, { createContext, useContext, useEffect, useState, useCallback, useRef } from 'react';
import { supabase } from '../lib/supabase';
import {
  syncRevenueCatUser,
  getRevenueCatRuntimeState,
  getCandidateRevenueCatState,
  getEmployerRevenueCatState,
  purchaseProStudentMonthly,
  purchaseProEmployerMonthly,
  restorePurchases as restoreRevenueCatPurchases,
  restoreEmployerPurchases as restoreRevenueCatEmployerPurchases,
  addRevenueCatCustomerInfoListener,
  DEFAULT_CANDIDATE_REVENUECAT_STATE,
  DEFAULT_EMPLOYER_REVENUECAT_STATE,
} from '../services/revenueCatService';

const RevenueCatContext = createContext({
  runtimeState: {
    configured: false,
    identifiedUserId: null,
    restorePurchasesSupported: false,
    reason: null,
  },
  candidateState: DEFAULT_CANDIDATE_REVENUECAT_STATE,
  employerState: DEFAULT_EMPLOYER_REVENUECAT_STATE,
  isRefreshing: false,
  isPurchasing: false,
  isRestoring: false,
  refreshCandidateState: async () => DEFAULT_CANDIDATE_REVENUECAT_STATE,
  purchaseProStudent: async () => ({
    success: false,
    cancelled: false,
    proStudentActive: false,
    candidateState: DEFAULT_CANDIDATE_REVENUECAT_STATE,
    reason: 'uninitialized',
  }),
  purchaseProEmployer: async () => ({
    success: false,
    cancelled: false,
    proEmployerActive: false,
    employerState: DEFAULT_EMPLOYER_REVENUECAT_STATE,
    reason: 'uninitialized',
  }),
  restorePurchases: async () => ({
    success: false,
    proStudentActive: false,
    candidateState: DEFAULT_CANDIDATE_REVENUECAT_STATE,
    reason: 'uninitialized',
  }),
});

export function RevenueCatProvider({ children }) {
  const [runtimeState, setRuntimeState] = useState(getRevenueCatRuntimeState());
  const [candidateState, setCandidateState] = useState(DEFAULT_CANDIDATE_REVENUECAT_STATE);
  const [employerState, setEmployerState] = useState(DEFAULT_EMPLOYER_REVENUECAT_STATE);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isPurchasing, setIsPurchasing] = useState(false);
  const [isRestoring, setIsRestoring] = useState(false);

  const activeUserIdRef = useRef(null);
  const authGenerationRef = useRef(0);
  const customerInfoUnsubscribeRef = useRef(null);
  const isMountedRef = useRef(true);

  const removeCustomerInfoListener = useCallback(() => {
    if (customerInfoUnsubscribeRef.current) {
      try {
        customerInfoUnsubscribeRef.current();
      } catch {
        // Safe disposal
      }
      customerInfoUnsubscribeRef.current = null;
    }
  }, []);

  const refreshCandidateState = useCallback(async () => {
    const expectedGeneration = authGenerationRef.current;
    const expectedUserId = activeUserIdRef.current;

    if (!expectedUserId) {
      return DEFAULT_CANDIDATE_REVENUECAT_STATE;
    }

    setIsRefreshing(true);
    try {
      const state = await getCandidateRevenueCatState();
      if (
        isMountedRef.current &&
        expectedGeneration === authGenerationRef.current &&
        expectedUserId === activeUserIdRef.current
      ) {
        setCandidateState(state);
        return state;
      }
      return DEFAULT_CANDIDATE_REVENUECAT_STATE;
    } finally {
      if (
        isMountedRef.current &&
        expectedGeneration === authGenerationRef.current
      ) {
        setIsRefreshing(false);
      }
    }
  }, []);

  const purchaseProStudent = useCallback(async () => {
    const expectedGeneration = authGenerationRef.current;
    const expectedUserId = activeUserIdRef.current;

    if (!expectedUserId) {
      return {
        success: false,
        cancelled: false,
        proStudentActive: false,
        candidateState: DEFAULT_CANDIDATE_REVENUECAT_STATE,
        reason: 'unauthenticated',
      };
    }

    setIsPurchasing(true);
    try {
      const result = await purchaseProStudentMonthly();
      if (
        isMountedRef.current &&
        expectedGeneration === authGenerationRef.current &&
        expectedUserId === activeUserIdRef.current
      ) {
        if (result.candidateState) {
          setCandidateState(result.candidateState);
        }
        if (result.employerState) {
          setEmployerState(result.employerState);
        }
        return result;
      }

      return {
        success: false,
        cancelled: false,
        proStudentActive: false,
        candidateState: DEFAULT_CANDIDATE_REVENUECAT_STATE,
        reason: 'identity_changed',
      };
    } finally {
      if (
        isMountedRef.current &&
        expectedGeneration === authGenerationRef.current
      ) {
        setIsPurchasing(false);
      }
    }
  }, []);

  const purchaseProEmployer = useCallback(async () => {
    const expectedGeneration = authGenerationRef.current;
    const expectedUserId = activeUserIdRef.current;

    if (!expectedUserId) {
      return {
        success: false,
        cancelled: false,
        proEmployerActive: false,
        employerState: DEFAULT_EMPLOYER_REVENUECAT_STATE,
        reason: 'unauthenticated',
      };
    }

    setIsPurchasing(true);
    try {
      const result = await purchaseProEmployerMonthly();

      if (
        isMountedRef.current &&
        expectedGeneration === authGenerationRef.current &&
        expectedUserId === activeUserIdRef.current
      ) {
        if (result.employerState) {
          setEmployerState(result.employerState);
        }
        return result;
      }

      return {
        success: false,
        cancelled: false,
        proEmployerActive: false,
        employerState: DEFAULT_EMPLOYER_REVENUECAT_STATE,
        reason: 'identity_changed',
      };
    } finally {
      if (
        isMountedRef.current &&
        expectedGeneration === authGenerationRef.current
      ) {
        setIsPurchasing(false);
      }
    }
  }, []);

  const restorePurchases = useCallback(async (accountType = 'intern') => {
    const expectedGeneration = authGenerationRef.current;
    const expectedUserId = activeUserIdRef.current;

    if (!expectedUserId) {
      return {
        success: false,
        proStudentActive: false,
        candidateState: DEFAULT_CANDIDATE_REVENUECAT_STATE,
        reason: 'unauthenticated',
      };
    }

    setIsRestoring(true);
    try {
      const result =
        accountType === 'employer'
          ? await restoreRevenueCatEmployerPurchases()
          : await restoreRevenueCatPurchases();
      if (
        isMountedRef.current &&
        expectedGeneration === authGenerationRef.current &&
        expectedUserId === activeUserIdRef.current
      ) {
        if (result.candidateState) {
          setCandidateState(result.candidateState);
        }
        return result;
      }

      return {
        success: false,
        proStudentActive: false,
        candidateState: DEFAULT_CANDIDATE_REVENUECAT_STATE,
        reason: 'identity_changed',
      };
    } finally {
      if (
        isMountedRef.current &&
        expectedGeneration === authGenerationRef.current
      ) {
        setIsRestoring(false);
      }
    }
  }, []);

  useEffect(() => {
    isMountedRef.current = true;
    let hasObservedAuthEvent = false;
    let syncQueue = Promise.resolve();

    const enqueueSync = (targetUserId) => {
      authGenerationRef.current += 1;
      const currentGen = authGenerationRef.current;
      activeUserIdRef.current = targetUserId;

      // Remove any existing listener and reset state on identity transition
      removeCustomerInfoListener();

      if (isMountedRef.current) {
        setCandidateState(DEFAULT_CANDIDATE_REVENUECAT_STATE);
        setEmployerState(DEFAULT_EMPLOYER_REVENUECAT_STATE);
        setIsRefreshing(false);
        setIsPurchasing(false);
        setIsRestoring(false);
      }

      syncQueue = syncQueue
        .then(async () => {
          const nextRuntimeState = await syncRevenueCatUser(targetUserId);
          if (!isMountedRef.current || currentGen !== authGenerationRef.current) {
            return;
          }

          setRuntimeState(nextRuntimeState);

          if (
            targetUserId &&
            nextRuntimeState.configured &&
            nextRuntimeState.identifiedUserId === targetUserId
          ) {
            const [nextCandidateState, nextEmployerState] = await Promise.all([
              getCandidateRevenueCatState(),
              getEmployerRevenueCatState(),
            ]);

            if (isMountedRef.current && currentGen === authGenerationRef.current) {
              setCandidateState(nextCandidateState);
              setEmployerState(nextEmployerState);

              // Register CustomerInfo listener bound to this generation/user
              removeCustomerInfoListener();
              const listenerGen = currentGen;
              const listenerUserId = targetUserId;

              customerInfoUnsubscribeRef.current = addRevenueCatCustomerInfoListener((update) => {
                if (
                  !isMountedRef.current ||
                  listenerGen !== authGenerationRef.current ||
                  listenerUserId !== activeUserIdRef.current
                ) {
                  return;
                }

                setCandidateState((prev) => ({
                  ...prev,
                  providerVerified: update.providerVerified,
                  proStudentActive: update.proStudentActive,
                  activeEntitlementIds: update.activeEntitlementIds,
                }));

                setEmployerState((prev) => ({
                  ...prev,
                  providerVerified: update.providerVerified,
                  proEmployerActive: update.proEmployerActive,
                  activeEntitlementIds: update.activeEntitlementIds,
                }));
              });
            }
          } else {
            if (isMountedRef.current && currentGen === authGenerationRef.current) {
              setCandidateState(DEFAULT_CANDIDATE_REVENUECAT_STATE);
              setEmployerState(DEFAULT_EMPLOYER_REVENUECAT_STATE);
            }
            removeCustomerInfoListener();
          }
        })
        .catch(() => {
          // Prevent queue failure
        });
    };

    const { data: authListener } = supabase.auth.onAuthStateChange(
      (_event, session) => {
        hasObservedAuthEvent = true;
        const userId = session?.user?.id || null;
        enqueueSync(userId);
      }
    );

    const initInitialSession = async () => {
      try {
        const { data } = await supabase.auth.getSession();
        if (!hasObservedAuthEvent) {
          const userId = data?.session?.user?.id || null;
          enqueueSync(userId);
        }
      } catch {
        if (!hasObservedAuthEvent) {
          enqueueSync(null);
        }
      }
    };

    initInitialSession();

    return () => {
      isMountedRef.current = false;
      authListener?.subscription?.unsubscribe();
      removeCustomerInfoListener();
    };
  }, [removeCustomerInfoListener]);

  const contextValue = {
    runtimeState,
    candidateState,
    employerState,
    isRefreshing:
    isPurchasing,
    isRestoring,
    refreshCandidateState,
    purchaseProStudent,
    purchaseProEmployer,
    restorePurchases,
  };

  return (
    <RevenueCatContext.Provider value={contextValue}>
      {children}
    </RevenueCatContext.Provider>
  );
}

export function useRevenueCat() {
  return useContext(RevenueCatContext);
}
