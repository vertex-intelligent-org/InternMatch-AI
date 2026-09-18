import React, {
  createContext,
  useContext,
  useState,
  useCallback,
  useEffect,
  useRef,
} from 'react';
import { Alert } from 'react-native';
import {
  getSavedInternships,
  saveInternship,
  unsaveInternship,
  ApiError,
} from '../services/api';
import { supabase } from '../lib/supabase';
import haptics from '../services/haptics';
import i18n from '../localization/i18n';

const SavedInternshipsContext = createContext(null);

export function SavedInternshipsProvider({ children, enabled = true }) {
  const [savedIds, setSavedIds] = useState(() => new Set());
  const [savedItems, setSavedItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(null);

  const currentUserIdRef = useRef(null);
  const mutatingIdsRef = useRef(new Set());
  const refreshGenerationRef = useRef(0);
  const refreshInFlightUserIdRef = useRef(null);
  const [mutatingIds, setMutatingIds] = useState(() => new Set());

  const isMutating = useCallback((internshipId) => {
    return mutatingIdsRef.current.has(internshipId);
  }, []);

  const clearSavedInternships = useCallback(() => {
    currentUserIdRef.current = null;
    refreshGenerationRef.current += 1;
    refreshInFlightUserIdRef.current = null;
    mutatingIdsRef.current.clear();
    setMutatingIds(new Set());
    setSavedIds(new Set());
    setSavedItems([]);
    setTotal(0);
    setError(null);
    setLoading(false);
    setRefreshing(false);
  }, []);

  const refreshSavedInternships = useCallback(async (isInitial = false) => {
    if (!currentUserIdRef.current) {
      return;
    }

    if (mutatingIdsRef.current.size > 0) return;

    const activeUserId = currentUserIdRef.current;

    if (refreshInFlightUserIdRef.current === activeUserId) {
      return;
    }

    refreshInFlightUserIdRef.current = activeUserId;
    const requestGeneration = ++refreshGenerationRef.current;

    if (isInitial) {
      setLoading(true);
    } else {
      setRefreshing(true);
    }
    setError(null);

    try {
      const response = await getSavedInternships({ limit: 50, offset: 0 });
      if (currentUserIdRef.current !== activeUserId || refreshGenerationRef.current !== requestGeneration) return null;
      const items = response.items || [];
      const newIds = new Set(items.map((item) => item.internship_id));

      setSavedItems(items);
      setSavedIds(newIds);
      setTotal(response.total ?? items.length);
      return response;
    } catch (err) {
      if (currentUserIdRef.current !== activeUserId || refreshGenerationRef.current !== requestGeneration) return null;
      if (err instanceof ApiError && (err.status === 401 || err.status === 403)) {
        clearSavedInternships();
        return null;
      }
      console.warn('Failed to load saved internships:', err);
      setError('SAVED_LOAD_FAILED');
      throw err;
    } finally {
      if (refreshInFlightUserIdRef.current === activeUserId) {
        refreshInFlightUserIdRef.current = null;
      }

      if (currentUserIdRef.current === activeUserId && refreshGenerationRef.current === requestGeneration) {
        if (isInitial) {
          setLoading(false);
        } else {
          setRefreshing(false);
        }
      }
    }
  }, [clearSavedInternships]);

  // Auth lifecycle synchronization
  useEffect(() => {
    if (!enabled) {
      clearSavedInternships();
      return;
    }

    let isMounted = true;

    // Check existing session on mount
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (!isMounted) return;
      if (session?.user?.id) {
        if (currentUserIdRef.current) return;
        currentUserIdRef.current = session.user.id;
        refreshSavedInternships(true).catch((err) => {
          console.warn('Initial saved internships fetch failed:', err);
        });
      } else {
        clearSavedInternships();
      }
    });

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((event, session) => {
      if (!isMounted) return;

      if (!session?.user?.id || event === 'SIGNED_OUT') {
        clearSavedInternships();
      } else if (session.user.id !== currentUserIdRef.current) {
        clearSavedInternships();
        currentUserIdRef.current = session.user.id;
        refreshSavedInternships(true).catch((err) => {
          console.warn('Saved internships fetch on auth change failed:', err);
        });
      }
    });

    return () => {
      isMounted = false;
      subscription?.unsubscribe();
    };
  }, [enabled, clearSavedInternships, refreshSavedInternships]);

  const isSaved = useCallback(
    (internshipId) => {
      if (!internshipId) return false;
      return savedIds.has(internshipId);
    },
    [savedIds]
  );

  const toggleSave = useCallback(
    async (internship) => {
      const id = internship?.id || internship?.internship_id;
      if (!id) return;

      // In-flight mutation race protection
      if (mutatingIdsRef.current.has(id)) {
        return;
      }

      if (!currentUserIdRef.current) {
        Alert.alert(
          i18n.t('auth.signInRequiredTitle', { defaultValue: 'Sign In Required' }),
          i18n.t('auth.signInRequiredMessage', { defaultValue: 'Please sign in to save internships.' })
        );
        return;
      }

      refreshGenerationRef.current += 1;
      mutatingIdsRef.current.add(id);
      setMutatingIds(new Set(mutatingIdsRef.current));

      const currentlySaved = savedIds.has(id);
      const activeUserId = currentUserIdRef.current;

      if (currentlySaved) {
        // --- Optimistic UNSAVE ---
        const removedItem = savedItems.find(
          (item) => item.internship_id === id || item.id === id
        );
        const removedIndex = savedItems.findIndex(
          (item) => item.internship_id === id || item.id === id
        );

        setSavedIds((prev) => {
          const next = new Set(prev);
          next.delete(id);
          return next;
        });
        setSavedItems((prev) =>
          prev.filter((item) => item.internship_id !== id && item.id !== id)
        );
        setTotal((prev) => Math.max(0, prev - 1));

        // Let React Native paint the optimistic state before network work.
        await new Promise((resolve) => requestAnimationFrame(resolve));

        try {
          await unsaveInternship(id);
        } catch (err) {
          // Check if session is still active and for same user before rolling back
          if (currentUserIdRef.current === activeUserId) {
            setSavedIds((prev) => new Set(prev).add(id));
            if (removedItem) {
              setSavedItems((prev) => {
                if (prev.some((item) => item.internship_id === id || item.id === id)) {
                  return prev;
                }
                const next = [...prev];
                const insertAt = Math.min(removedIndex, next.length);
                next.splice(insertAt, 0, removedItem);
                return next;
              });
            }
            setTotal((prev) => prev + 1);
            haptics.error();
            console.warn('Failed to unsave internship:', err);
            Alert.alert(
              i18n.t('savedInternships.unsaveFailedTitle', { defaultValue: 'Unable to Unsave' }),
              i18n.t('errors.savedUnsaveFailed', { defaultValue: 'Unable to remove saved internship.' })
            );
          }
        } finally {
          mutatingIdsRef.current.delete(id);
          setMutatingIds(new Set(mutatingIdsRef.current));
        }
      } else {
        // --- Optimistic SAVE ---

        const hasCompleteData = Boolean(
          internship?.title && internship?.company
        );

        let optimisticItem = null;
        if (hasCompleteData) {
          optimisticItem = {
            id: `temp-${id}-${Date.now()}`,
            internship_id: id,
            saved_at: new Date().toISOString(),
            internship: {
              id: id,
              title: internship.title,
              company: internship.company,
              location: internship.location || '',
              work_type: internship.work_type || null,
              required_skills: Array.isArray(internship.required_skills)
                ? internship.required_skills
                : [],
              preferred_skills: Array.isArray(internship.preferred_skills)
                ? internship.preferred_skills
                : [],
              posted_at: internship.posted_at || new Date().toISOString(),
            },
          };
        }

        setSavedIds((prev) => new Set(prev).add(id));
        if (optimisticItem) {
          setSavedItems((prev) => [optimisticItem, ...prev]);
          setTotal((prev) => prev + 1);
        }

        // Let React Native paint the optimistic state before network work.
        await new Promise((resolve) => requestAnimationFrame(resolve));

        try {
          const response = await saveInternship(id);
          if (currentUserIdRef.current === activeUserId) {
            if (optimisticItem && response?.id) {
              setSavedItems((prev) =>
                prev.map((item) =>
                  item.id === optimisticItem.id
                    ? {
                        ...item,
                        id: response.id,
                        saved_at: response.saved_at || item.saved_at,
                      }
                    : item
                )
              );
            } else if (!hasCompleteData) {
              // Full details were not passed; reconcile from backend
              await refreshSavedInternships(false);
            }
          }
        } catch (err) {
          if (currentUserIdRef.current === activeUserId) {
            setSavedIds((prev) => {
              const next = new Set(prev);
              next.delete(id);
              return next;
            });
            if (optimisticItem) {
              setSavedItems((prev) =>
                prev.filter((item) => item.id !== optimisticItem.id)
              );
              setTotal((prev) => Math.max(0, prev - 1));
            }
            haptics.error();
            console.warn('Failed to save internship:', err);
            Alert.alert(
              i18n.t('savedInternships.saveFailedTitle', { defaultValue: 'Unable to Save' }),
              i18n.t('errors.savedSaveFailed', { defaultValue: 'Unable to save internship.' })
            );
          }
        } finally {
          mutatingIdsRef.current.delete(id);
          setMutatingIds(new Set(mutatingIdsRef.current));
        }
      }
    },
    [savedIds, savedItems, total, refreshSavedInternships]
  );

  const value = {
    savedIds,
    savedItems,
    total,
    loading,
    refreshing,
    error,
    isSaved,
    isMutating,
    mutatingIds,
    toggleSave,
    refreshSavedInternships,
    clearSavedInternships,
  };

  return (
    <SavedInternshipsContext.Provider value={value}>
      {children}
    </SavedInternshipsContext.Provider>
  );
}

export function useSavedInternships() {
  const context = useContext(SavedInternshipsContext);
  if (!context) {
    throw new Error(
      'useSavedInternships must be used within a SavedInternshipsProvider'
    );
  }
  return context;
}

export default SavedInternshipsContext;
