import React, { useEffect, useState, useCallback, useRef } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  ActivityIndicator,
  RefreshControl,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTranslation } from 'react-i18next';
import { useScrollToTop } from '@react-navigation/native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import colors from '../theme/colors';
import { spacing } from '../theme/spacing';
import { typography } from '../theme/typography';
import { getTabScreenBottomPadding } from '../theme/tabBarLayout';
import ScreenContainer from '../components/ScreenContainer';
import ScreenHeader from '../components/ScreenHeader';
import AuthenticatedAppChromeHeader from '../components/AuthenticatedAppChromeHeader';
import Card from '../components/Card';
import PressableCard from '../components/PressableCard';
import Chip from '../components/Chip';
import PressableScale from '../components/PressableScale';
import BookmarkButton from '../components/BookmarkButton';
import { getInternships } from '../services/api';
import haptics from '../services/haptics';
import { useTabScroll, useTabScrollReporter } from '../context/TabScrollContext';
import { useSavedInternships } from '../context/SavedInternshipsContext';
import { useLocalization } from '../localization/LocalizationContext';

const PAGE_SIZE = 20;

const FILTER_KEYS = [
  { key: 'all', value: undefined },
  { key: 'remote', value: 'remote' },
  { key: 'hybrid', value: 'hybrid' },
  { key: 'onsite', value: 'onsite' },
];

export default function InternshipsScreen({ navigation }) {
  const { t } = useTranslation();
  const { isRTL } = useLocalization();
  const insets = useSafeAreaInsets();
  const bottomPadding = getTabScreenBottomPadding(insets.bottom);
  const scrollViewRef = useRef(null);
  useTabScroll('Internships', scrollViewRef);
  useScrollToTop(scrollViewRef);
  const onScroll = useTabScrollReporter(20);

  const { isSaved, toggleSave, isMutating, savedIds } = useSavedInternships();

  const [selectedFilterKey, setSelectedFilterKey] = useState('all');
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(null);

  const activeFilterRef = useRef(selectedFilterKey);
  const catalogActionInFlightRef = useRef(null);
  activeFilterRef.current = selectedFilterKey;

  const getFilterValue = (filterKey) => {
    const found = FILTER_KEYS.find((f) => f.key === filterKey);
    return found ? found.value : undefined;
  };

  const fetchInitialInternships = useCallback(async (filterKey = selectedFilterKey) => {
    setLoading(true);
    setError(null);

    const workType = getFilterValue(filterKey);

    try {
      const response = await getInternships({
        work_type: workType,
        limit: PAGE_SIZE,
        offset: 0,
      });

      if (activeFilterRef.current === filterKey) {
        setItems(response.items || []);
        setTotal(response.total || 0);
      }
    } catch (err) {
      if (activeFilterRef.current === filterKey) {
        console.warn('Failed to load internships:', err);
        setError('INTERNSHIPS_LOAD_FAILED');
      }
    } finally {
      if (activeFilterRef.current === filterKey) {
        setLoading(false);
      }
    }
  }, [selectedFilterKey]);

  // Fetch on initial mount and when the selected filter changes.
  // Tab focus itself does not invalidate the already rendered catalog.
  useEffect(() => {
    setRefreshing(false);
    setLoadingMore(false);
    fetchInitialInternships(selectedFilterKey);
  }, [selectedFilterKey, fetchInitialInternships]);

  const handleRefresh = async () => {
    if (catalogActionInFlightRef.current || loading) return;

    catalogActionInFlightRef.current = 'refresh';
    const filterKey = selectedFilterKey;
    setRefreshing(true);
    setError(null);
    const workType = getFilterValue(filterKey);

    try {
      const response = await getInternships({
        work_type: workType,
        limit: PAGE_SIZE,
        offset: 0,
      });

      if (activeFilterRef.current === filterKey) {
        setItems(response.items || []);
        setTotal(response.total || 0);
      }
    } catch (err) {
      if (activeFilterRef.current === filterKey) {
        console.warn('Failed to refresh internships:', err);
        setError('INTERNSHIPS_LOAD_FAILED');
      }
    } finally {
      if (catalogActionInFlightRef.current === 'refresh') {
        catalogActionInFlightRef.current = null;
      }

      if (activeFilterRef.current === filterKey) {
        setRefreshing(false);
      }
    }
  };

  const handleLoadMore = async () => {
    if (
      catalogActionInFlightRef.current ||
      loadingMore ||
      loading ||
      items.length >= total
    ) {
      return;
    }

    catalogActionInFlightRef.current = 'load-more';

    const filterKey = selectedFilterKey;
    setLoadingMore(true);
    const workType = getFilterValue(filterKey);

    try {
      const response = await getInternships({
        work_type: workType,
        limit: PAGE_SIZE,
        offset: items.length,
      });

      if (activeFilterRef.current === filterKey) {
        setItems((prevItems) => {
          const seenIds = new Set(prevItems.map((i) => i.id));
          const newUniqueItems = (response.items || []).filter((i) => !seenIds.has(i.id));
          return [...prevItems, ...newUniqueItems];
        });
        setTotal(response.total || 0);
      }
    } catch (err) {
      if (activeFilterRef.current === filterKey) {
        console.warn('Load more error:', err);
      }
    } finally {
      if (catalogActionInFlightRef.current === 'load-more') {
        catalogActionInFlightRef.current = null;
      }

      if (activeFilterRef.current === filterKey) {
        setLoadingMore(false);
      }
    }
  };

  const handleRetry = async () => {
    if (catalogActionInFlightRef.current || loading) return;

    catalogActionInFlightRef.current = 'retry';

    try {
      await fetchInitialInternships(selectedFilterKey);
    } finally {
      if (catalogActionInFlightRef.current === 'retry') {
        catalogActionInFlightRef.current = null;
      }
    }
  };
  const handleFilterSelect = (key) => {
    if (
      catalogActionInFlightRef.current ||
      loading ||
      refreshing ||
      loadingMore
    ) return;

    if (selectedFilterKey !== key) {
      haptics.selection();
      setSelectedFilterKey(key);
    }
  };

  const formatWorkType = (wt) => {
    if (!wt) return null;
    const lower = wt.toLowerCase();
    return t(`internships.workTypes.${lower}`, {
      defaultValue: wt.charAt(0).toUpperCase() + wt.slice(1),
    });
  };

  const hasMore = items.length < total;

  const savedHeaderAction = (
    <PressableScale
      onPress={() => navigation.navigate('SavedInternships')}
      haptic="light"
      accessibilityRole="button"
      accessibilityLabel={t('internships.savedCountA11y', { count: savedIds.size })}
      hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
    >
      <View>
        <Ionicons
          name={savedIds.size > 0 ? 'bookmark' : 'bookmark-outline'}
          size={22}
          color={colors.accentStrong}
        />
        {savedIds.size > 0 ? (
          <View style={styles.savedCountBadge}>
            <Text style={styles.savedCountText}>{savedIds.size}</Text>
          </View>
        ) : null}
      </View>
    </PressableScale>
  );

  return (
    <ScreenContainer edges={['top']}>
      <AuthenticatedAppChromeHeader />
      <ScreenHeader
        title={t('internships.title')}
        rightAction={savedHeaderAction}
        alignment="start"
      />

      <ScrollView
        ref={scrollViewRef}
        style={styles.screen}
        contentContainerStyle={[styles.content, { paddingBottom: bottomPadding }]}
        showsVerticalScrollIndicator={false}
        onScroll={onScroll}
        scrollEventThrottle={16}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={handleRefresh}
            colors={[colors.accent || colors.teal]}
            tintColor={colors.accent || colors.teal}
          />
        }
      >
        {/* Work Type Filter Chips */}
        <View style={[styles.filterRow, isRTL && styles.filterRowRTL]}>
          {FILTER_KEYS.map((f) => {
            const label = t(`internships.filters.${f.key}`);
            const isSelected = selectedFilterKey === f.key;
            return (
              <TouchableOpacity
                key={f.key}
                style={[
                  styles.filterChip,
                  isSelected && styles.filterChipActive,
                ]}
                onPress={() => handleFilterSelect(f.key)}
                disabled={loading || refreshing || loadingMore}
                accessibilityRole="button"
                accessibilityLabel={t('internships.filters.filterA11y', { label })}
                accessibilityState={{
                  selected: isSelected,
                  disabled: loading || refreshing || loadingMore,
                  busy: loading || refreshing || loadingMore,
                }}
                hitSlop={{ top: 6, bottom: 6, left: 4, right: 4 }}
              >
                <Text
                  style={[
                    styles.filterText,
                    isSelected && styles.filterTextActive,
                  ]}
                >
                  {label}
                </Text>
              </TouchableOpacity>
            );
          })}
        </View>

        {/* Initial Loading State */}
        {loading && !refreshing && (
          <View style={styles.centerContainer}>
            <ActivityIndicator size="large" color={colors.accent || colors.teal} />
            <Text style={styles.loadingText}>{t('internships.loading')}</Text>
          </View>
        )}

        {/* Error State */}
        {!loading && error && (
          <Card style={styles.errorCard} padding="lg">
            <Ionicons name="alert-circle-outline" size={36} color={colors.danger || '#EF4444'} />
            <Text style={styles.errorTitle}>{t('internships.errorTitle')}</Text>
            <Text style={styles.errorMessage}>
              {t('errors.internshipsLoadFailed', { defaultValue: t('internships.errorTitle') })}
            </Text>
            <TouchableOpacity
              style={styles.retryButton}
              onPress={handleRetry}
              disabled={loading || refreshing}
              accessibilityRole="button"
              accessibilityLabel={t('common.tryAgain')}
              accessibilityState={{
                disabled: loading || refreshing,
                busy: loading || refreshing,
              }}
            >
              <Text style={styles.retryButtonText}>{t('common.tryAgain')}</Text>
            </TouchableOpacity>
          </Card>
        )}

        {/* Empty State */}
        {!loading && !error && items.length === 0 && (
          <Card style={styles.emptyCard} padding="lg">
            <Ionicons name="briefcase-outline" size={48} color={colors.textTertiary || colors.textMuted} />
            <Text style={styles.emptyTitle}>{t('internships.emptyTitle')}</Text>
            <Text style={styles.emptySubtitle}>
              {selectedFilterKey !== 'all'
                ? t('internships.emptyFiltered', { filter: t(`internships.filters.${selectedFilterKey}`) })
                : t('internships.emptyCatalog')}
            </Text>
            {selectedFilterKey !== 'all' && (
              <TouchableOpacity
                style={styles.resetFilterButton}
                onPress={() => setSelectedFilterKey('all')}
                accessibilityRole="button"
                accessibilityLabel={t('internships.showAll')}
              >
                <Text style={styles.resetFilterText}>{t('internships.showAll')}</Text>
              </TouchableOpacity>
            )}
          </Card>
        )}

        {/* Populated Listing */}
        {!loading && !error && items.length > 0 && (
          <>
            {items.map((item) => (
              <PressableCard
                key={item.id}
                style={styles.card}
                padding="md"
                onPress={() =>
                  navigation.navigate('InternshipDetail', { internshipId: item.id })
                }
                accessibilityLabel={t('internships.cardA11y', {
                  title: item.title,
                  company: item.company,
                })}
              >
                <View style={styles.cardTop}>
                  <BookmarkButton
                    isSaved={isSaved(item.id)}
                    disabled={isMutating(item.id)}
                    onPress={(event) => {
                      event?.stopPropagation?.();
                      toggleSave(item);
                    }}
                    style={styles.cardBookmark}
                  />
                  <Text style={styles.cardTitle}>{item.title}</Text>
                  {item.work_type ? (
                    <View style={styles.workTypeBadge}>
                      <Text style={styles.workTypeText}>{formatWorkType(item.work_type)}</Text>
                    </View>
                  ) : null}
                </View>

                <Text style={styles.cardMeta}>
                  {item.company} - {item.location}
                </Text>

                {item.required_skills && item.required_skills.length > 0 && (
                  <View style={styles.skillsRow}>
                    {item.required_skills.slice(0, 3).map((skill) => (
                      <Chip key={skill} label={skill} variant="skill" />
                    ))}
                    {item.required_skills.length > 3 && (
                      <Text style={styles.moreSkillsText}>
                        {t('internships.moreSkills', { count: item.required_skills.length - 3 })}
                      </Text>
                    )}
                  </View>
                )}
              </PressableCard>
            ))}

            {/* Pagination Controls */}
            {hasMore && (
              <TouchableOpacity
                style={styles.loadMoreButton}
                onPress={handleLoadMore}
                disabled={loadingMore}
                accessibilityRole="button"
                accessibilityLabel={t('internships.loadMoreA11y', {
                  count: items.length,
                  total,
                })}
              >
                {loadingMore ? (
                  <ActivityIndicator size="small" color={colors.textInverse || colors.white} />
                ) : (
                  <Text style={styles.loadMoreText}>
                    {t('internships.loadMore', { count: items.length, total })}
                  </Text>
                )}
              </TouchableOpacity>
            )}

            {!hasMore && total > 0 && (
              <Text style={styles.exhaustedText}>
                {t('internships.showingAll', { total })}
              </Text>
            )}
          </>
        )}
      </ScrollView>
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: colors.background || colors.screenBg,
  },
  content: {
    paddingHorizontal: spacing.screenHorizontalPadding,
    paddingTop: spacing.xs,
    paddingBottom: 128,
  },
  filterRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: spacing.md,
    marginTop: spacing.xs,
  },
  filterChip: {
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    borderRadius: spacing.radii.pill,
    backgroundColor: colors.surfaceSubtle || '#DCE9EC',
    marginEnd: spacing.sm,
    minHeight: 36,
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: colors.borderSubtle || colors.border,
  },
  filterChipActive: {
    backgroundColor: colors.accent || colors.teal,
    borderColor: colors.accent || colors.teal,
  },
  filterText: {
    ...typography.caption,
    fontWeight: '600',
    color: colors.textSecondary || colors.textMuted,
  },
  filterTextActive: {
    color: colors.textInverse || colors.white,
    fontWeight: '700',
  },
  centerContainer: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: spacing.xxxl * 2,
  },
  loadingText: {
    ...typography.caption,
    color: colors.textSecondary || colors.textMuted,
    marginTop: spacing.md,
  },
  card: {
    marginBottom: spacing.md,
  },
  cardTop: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
  },
  cardTitle: {
    flex: 1,
    ...typography.cardTitle,
    color: colors.textPrimary || colors.textDark,
    marginEnd: spacing.sm,
  },
  workTypeBadge: {
    backgroundColor: colors.accentSoft || '#E6F4F6',
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xxs + 1,
    borderRadius: spacing.radii.sm,
  },
  workTypeText: {
    ...typography.caption,
    fontWeight: '600',
    color: colors.accentStrong || colors.tealDark,
  },
  cardMeta: {
    ...typography.caption,
    color: colors.textSecondary || colors.textMuted,
    marginTop: spacing.xs,
  },
  skillsRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    marginTop: spacing.sm,
  },
  moreSkillsText: {
    ...typography.caption,
    color: colors.textTertiary || colors.textMuted,
    marginStart: spacing.xs,
    marginBottom: spacing.sm,
  },
  errorCard: {
    alignItems: 'center',
    marginTop: spacing.lg,
    borderColor: colors.dangerSoft || '#FEE2E2',
    backgroundColor: '#FEF2F2',
  },
  errorTitle: {
    ...typography.cardTitle,
    color: colors.danger || '#EF4444',
    marginTop: spacing.sm,
  },
  errorMessage: {
    ...typography.caption,
    color: colors.textSecondary || colors.textMuted,
    textAlign: 'center',
    marginTop: spacing.xs,
    marginBottom: spacing.lg,
  },
  retryButton: {
    backgroundColor: colors.accent || colors.teal,
    paddingHorizontal: spacing.xl,
    paddingVertical: spacing.sm + 2,
    borderRadius: spacing.radii.sm,
    minHeight: spacing.minimumTouchTarget,
    justifyContent: 'center',
  },
  retryButtonText: {
    ...typography.button,
    color: colors.textInverse || colors.white,
    fontSize: 13,
  },
  emptyCard: {
    alignItems: 'center',
    marginTop: spacing.lg,
  },
  emptyTitle: {
    ...typography.cardTitle,
    color: colors.textPrimary || colors.textDark,
    marginTop: spacing.md,
  },
  emptySubtitle: {
    ...typography.caption,
    color: colors.textSecondary || colors.textMuted,
    textAlign: 'center',
    marginTop: spacing.xs,
    lineHeight: 18,
  },
  resetFilterButton: {
    marginTop: spacing.lg,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    borderRadius: spacing.radii.sm,
    backgroundColor: colors.accentSoft || '#E6F4F6',
    minHeight: spacing.minimumTouchTarget,
    justifyContent: 'center',
  },
  resetFilterText: {
    ...typography.button,
    color: colors.accentStrong || colors.tealDark,
    fontSize: 13,
  },
  loadMoreButton: {
    backgroundColor: colors.accent || colors.teal,
    borderRadius: spacing.radii.md,
    paddingVertical: spacing.md,
    alignItems: 'center',
    marginTop: spacing.xs,
    marginBottom: spacing.md,
    minHeight: spacing.minimumTouchTarget,
    justifyContent: 'center',
  },
  loadMoreText: {
    ...typography.button,
    color: colors.textInverse || colors.white,
    fontSize: 14,
  },
  exhaustedText: {
    textAlign: 'center',
    ...typography.caption,
    color: colors.textTertiary || colors.textMuted,
    marginTop: spacing.xs,
    marginBottom: spacing.md,
  },
  savedCountBadge: {
    position: 'absolute',
    top: -6,
    right: -8,
    minWidth: 16,
    height: 16,
    paddingHorizontal: 4,
    borderRadius: 8,
    backgroundColor: colors.accentStrong,
    alignItems: 'center',
    justifyContent: 'center',
  },
  savedCountText: {
    fontSize: 10,
    fontWeight: '700',
    color: colors.textInverse,
  },
  cardBookmark: {
    marginStart: spacing.xs,
    marginTop: -spacing.xs,
  },
});
