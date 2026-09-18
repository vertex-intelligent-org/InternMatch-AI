import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { AppState } from 'react-native';
import { supabase } from '../lib/supabase';
import {
  getMyAIUsage,
  getMySubscription,
  reconcileMySubscription,
} from '../services/api';

const SubscriptionContext = createContext({
  backendSubscription: null,
  aiUsage: null,
  loading: true,
  error: null,
  refreshSubscriptionState: async () => null,
  refreshAIUsage: async () => null,
  checkAIQuotaAvailable: async () => true,
  reconcileSubscription: async () => null,
});

export function SubscriptionProvider({ children, enabled = true }) {
  const [backendSubscription, setBackendSubscription] = useState(null);
  const [aiUsage, setAIUsage] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const mountedRef = useRef(true);
  const generationRef = useRef(0);
  const currentUserIdRef = useRef(null);

  const isCurrentGeneration = useCallback((generation, userId) => {
    return (
      mountedRef.current &&
      generation === generationRef.current &&
      userId === currentUserIdRef.current
    );
  }, []);

  const loadAllForUser = useCallback(
    async (userId, generation, silent = false) => {
      if (!userId) {
        return null;
      }

      if (!silent && isCurrentGeneration(generation, userId)) {
        setLoading(true);
      }

      try {
        const [subscription, usage] = await Promise.all([
          getMySubscription(),
          getMyAIUsage(),
        ]);

        if (!isCurrentGeneration(generation, userId)) {
          return null;
        }

        setBackendSubscription(subscription);
        setAIUsage(usage);
        setError(null);

        return {
          subscription,
          aiUsage: usage,
        };
      } catch (loadError) {
        if (isCurrentGeneration(generation, userId)) {
          // Fail safe: never infer paid access when backend authority
          // cannot be established.
          setBackendSubscription(null);
          setAIUsage(null);
          setError('SUBSCRIPTION_STATE_UNAVAILABLE');
        }

        throw loadError;
      } finally {
        if (
          !silent &&
          isCurrentGeneration(generation, userId)
        ) {
          setLoading(false);
        }
      }
    },
    [isCurrentGeneration]
  );

  const refreshSubscriptionState = useCallback(
    async (options = {}) => {
      const userId = currentUserIdRef.current;

      if (!userId) {
        return null;
      }

      const generation = generationRef.current;
      const silent = options?.silent === true;

      return loadAllForUser(
        userId,
        generation,
        silent
      );
    },
    [loadAllForUser]
  );

  const refreshAIUsage = useCallback(async () => {
    const userId = currentUserIdRef.current;

    if (!userId) {
      return null;
    }

    const generation = generationRef.current;

    try {
      const usage = await getMyAIUsage();

      if (isCurrentGeneration(generation, userId)) {
        setAIUsage(usage);
        setError(null);
      }

      return usage;
    } catch (usageError) {
      if (isCurrentGeneration(generation, userId)) {
        setError('AI_USAGE_STATE_UNAVAILABLE');
      }

      throw usageError;
    }
  }, [isCurrentGeneration]);

  const checkAIQuotaAvailable = useCallback(
    async (featureKey) => {
      const cachedFeature =
        aiUsage?.features?.find(
          (feature) =>
            feature.feature_key ===
            featureKey
        );

      // Known zero quota is authoritative enough for
      // UX routing. Do not open a picker or wait for
      // another network round-trip before showing Plans.
      if (
        cachedFeature?.remaining === 0
      ) {
        return false;
      }

      try {
        // Positive or unknown cached state can be stale,
        // so refresh before starting expensive AI work.
        const latestUsage =
          await refreshAIUsage();

        const latestFeature =
          latestUsage?.features?.find(
            (feature) =>
              feature.feature_key ===
              featureKey
          );

        if (
          !latestFeature ||
          typeof latestFeature.remaining !==
            'number'
        ) {
          // Missing quota state is not proof of
          // exhaustion. The feature endpoint remains
          // the final authoritative boundary.
          return true;
        }

        return latestFeature.remaining > 0;
      } catch (usageError) {
        console.warn(
          'AI quota preflight refresh failed:',
          usageError
        );

        // A network failure must not create a false
        // paywall. Continue to the authoritative
        // feature endpoint.
        return true;
      }
    },
    [
      aiUsage,
      refreshAIUsage,
    ]
  );

  const reconcileSubscription = useCallback(async () => {
    const userId = currentUserIdRef.current;

    if (!userId) {
      return null;
    }

    const generation = generationRef.current;

    try {
      const result = await reconcileMySubscription();

      if (!isCurrentGeneration(generation, userId)) {
        return result;
      }

      setBackendSubscription(result.subscription);
      setError(null);

      // A plan transition can change all feature periods/limits.
      try {
        const usage = await getMyAIUsage();

        if (isCurrentGeneration(generation, userId)) {
          setAIUsage(usage);
        }
      } catch (_usageRefreshError) {
        if (isCurrentGeneration(generation, userId)) {
          setAIUsage(null);
          setError('AI_USAGE_STATE_UNAVAILABLE');
        }
      }

      return result;
    } catch (reconcileError) {
      if (isCurrentGeneration(generation, userId)) {
        setError('SUBSCRIPTION_RECONCILIATION_FAILED');
      }

      throw reconcileError;
    }
  }, [isCurrentGeneration]);

  useEffect(() => {
    mountedRef.current = true;

    if (!enabled) {
      generationRef.current += 1;
      currentUserIdRef.current = null;
      setBackendSubscription(null);
      setAIUsage(null);
      setLoading(false);
      setError(null);

      return () => {
        mountedRef.current = false;
      };
    }

    let active = true;

    const applySession = (session) => {
      if (!active || !mountedRef.current) {
        return;
      }

      const nextUserId = session?.user?.id || null;

      if (
        nextUserId &&
        nextUserId === currentUserIdRef.current
      ) {
        return;
      }

      const generation = generationRef.current + 1;
      generationRef.current = generation;
      currentUserIdRef.current = nextUserId;

      setBackendSubscription(null);
      setAIUsage(null);
      setError(null);

      if (!nextUserId) {
        setLoading(false);
        return;
      }

      setLoading(true);

      loadAllForUser(
        nextUserId,
        generation,
        false
      ).catch(() => {
        // Error state is already recorded by loadAllForUser.
      });
    };

    const {
      data: authListenerData,
    } = supabase.auth.onAuthStateChange(
      (_event, session) => {
        applySession(session);
      }
    );

    supabase.auth
      .getSession()
      .then(({ data }) => {
        applySession(data?.session || null);
      })
      .catch(() => {
        if (!active || !mountedRef.current) {
          return;
        }

        generationRef.current += 1;
        currentUserIdRef.current = null;
        setBackendSubscription(null);
        setAIUsage(null);
        setLoading(false);
        setError('SUBSCRIPTION_STATE_UNAVAILABLE');
      });

    return () => {
      active = false;
      mountedRef.current = false;
      generationRef.current += 1;
      currentUserIdRef.current = null;
      authListenerData?.subscription?.unsubscribe?.();
    };
  }, [enabled, loadAllForUser]);

  useEffect(() => {
    const appStateSubscription = AppState.addEventListener(
      'change',
      (nextState) => {
        if (
          nextState === 'active' &&
          currentUserIdRef.current
        ) {
          refreshSubscriptionState({
            silent: true,
          }).catch(() => {
            // Best-effort foreground refresh.
          });
        }
      }
    );

    return () => {
      appStateSubscription?.remove?.();
    };
  }, [refreshSubscriptionState]);

  const value = useMemo(
    () => ({
      backendSubscription,
      aiUsage,
      loading,
      error,
      refreshSubscriptionState,
      refreshAIUsage,
      checkAIQuotaAvailable,
      reconcileSubscription,
    }),
    [
      backendSubscription,
      aiUsage,
      loading,
      error,
      refreshSubscriptionState,
      refreshAIUsage,
      checkAIQuotaAvailable,
      reconcileSubscription,
    ]
  );

  return (
    <SubscriptionContext.Provider value={value}>
      {children}
    </SubscriptionContext.Provider>
  );
}

export function useSubscription() {
  return useContext(SubscriptionContext);
}
