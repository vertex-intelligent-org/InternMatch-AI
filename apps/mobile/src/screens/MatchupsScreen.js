import React, { useEffect, useState, useCallback, useRef } from 'react';
import {
  Alert,
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
import { useIsFocused, useScrollToTop } from '@react-navigation/native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import colors from '../theme/colors';
import { spacing } from '../theme/spacing';
import { typography } from '../theme/typography';
import { getTabScreenBottomPadding } from '../theme/tabBarLayout';
import motionTokens from '../motion/motionTokens';
import ScreenContainer from '../components/ScreenContainer';
import ScreenHeader from '../components/ScreenHeader';
import AuthenticatedAppChromeHeader from '../components/AuthenticatedAppChromeHeader';
import Card from '../components/Card';
import PressableCard from '../components/PressableCard';
import PressableScale from '../components/PressableScale';
import MatchBadge from '../components/MatchBadge';
import GradientButton from '../components/GradientButton';
import Reveal from '../components/motion/Reveal';
import AIPulse from '../components/motion/AIPulse';
import BrandedAILoader from '../components/motion/BrandedAILoader';
import { getMatches } from '../services/api';
import { useProfile } from '../context/ProfileContext';
import { useMatchCalculation } from '../hooks/useMatchCalculation';
import { useTabScroll, useTabScrollReporter } from '../context/TabScrollContext';
import { useLocalization } from '../localization/LocalizationContext';
import { getLocalizedErrorMessage } from '../localization/errorMessages';

export default function MatchupsScreen({ navigation }) {
  const { t } = useTranslation();
  const { isRTL } = useLocalization();
  const insets = useSafeAreaInsets();
  const bottomPadding = getTabScreenBottomPadding(insets.bottom);
  const scrollViewRef = useRef(null);
  useTabScroll('Matchups', scrollViewRef);
  useScrollToTop(scrollViewRef);
  const onScroll = useTabScrollReporter(20);

  const { profile } = useProfile();
  const [matches, setMatches] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const isFocused = useIsFocused();
  const passiveFetchTriggeredRef = useRef(false);
  const cancelPromptVisibleRef = useRef(false);
  const allowNavigationRef = useRef(false);

  const {
    isCalculating,
    isCancelling,
    progressPercent,
    calculationError,
    startCalculation,
    cancelCalculation,
  } = useMatchCalculation();

  const handleStopChecking = useCallback((options = {}) => {
    const leaveAfterCancellation =
      options?.leaveAfterCancellation === true;
    const navigationAction =
      options?.navigationAction || null;

    if (
      !isCalculating ||
      isCancelling ||
      cancelPromptVisibleRef.current
    ) {
      return;
    }

    cancelPromptVisibleRef.current = true;

    Alert.alert(
      t('aiCancellation.title'),
      t('aiCancellation.message'),
      [
        {
          text: t('aiCancellation.continue'),
          style: 'cancel',
          onPress: () => {
            // Keep the exact server job and polling state alive.
            cancelPromptVisibleRef.current = false;
          },
        },
        {
          text: t('aiCancellation.cancel'),
          style: 'destructive',
          onPress: async () => {
            cancelPromptVisibleRef.current = false;

            try {
              const cancelled =
                await cancelCalculation();

              if (!cancelled) {
                throw new Error(
                  'SERVER_CANCEL_NOT_YET_AVAILABLE'
                );
              }

              if (leaveAfterCancellation) {
                allowNavigationRef.current = true;

                if (navigationAction) {
                  navigation.dispatch(
                    navigationAction
                  );
                } else {
                  navigation.goBack();
                }
              }
            } catch (error) {
              console.warn(
                'Match calculation cancellation failed:',
                error
              );

              Alert.alert(
                t('aiCancellation.failedTitle'),
                t('aiCancellation.failedMessage')
              );
            }
          },
        },
      ],
      {
        cancelable: true,
        onDismiss: () => {
          cancelPromptVisibleRef.current = false;
        },
      }
    );
  }, [
    cancelCalculation,
    isCalculating,
    isCancelling,
    navigation,
    t,
  ]);

  useEffect(() => {
    const unsubscribe = navigation.addListener(
      'beforeRemove',
      (event) => {
        if (allowNavigationRef.current) {
          allowNavigationRef.current = false;
          return;
        }

        if (!isCalculating) {
          return;
        }

        event.preventDefault();

        handleStopChecking({
          leaveAfterCancellation: true,
          navigationAction: event.data.action,
        });
      }
    );

    return unsubscribe;
  }, [
    navigation,
    isCalculating,
    handleStopChecking,
  ]);

  const hasAnalyZV = Boolean(
    profile?.has_cv ||
      (profile?.skills && profile.skills.length > 0) ||
      (profile?.education && profile.education.length > 0) ||
      (profile?.experience && profile.experience.length > 0) ||
      (profile?.projects && profile.projects.length > 0)
  );

  const fetchMatchesData = useCallback(async ({ silent = false } = {}) => {
    if (!hasAnalyZV) {
      setMatches([]);
      setError(null);
      setLoading(false);
      return;
    }

    if (!silent) {
      setLoading(true);
      setError(null);
    }

    try {
      const res = await getMatches();
      setMatches(res.matches || []);
      setError(null);
    } catch (err) {
      console.warn('Failed to load matchups:', err);

      // A background refresh must never hide already rendered results.
      if (!silent) {
        setError('MATCHES_LOAD_FAILED');
      }
    } finally {
      if (!silent) {
        setLoading(false);
      }
    }
  }, [hasAnalyZV]);

  useEffect(() => {
    if (!hasAnalyZV) {
      passiveFetchTriggeredRef.current = false;
      return;
    }

    // MainTabs eagerly mounts Matchups before the user opens this tab.
    // Use that hidden time to preload the latest persisted matches.
    if (!passiveFetchTriggeredRef.current) {
      passiveFetchTriggeredRef.current = true;
      fetchMatchesData();
      return;
    }

    // When the user opens Matchups later, keep rendered data visible
    // and quietly check for fresher background-calculated matches.
    if (isFocused) {
      fetchMatchesData({ silent: true });
    }
  }, [
    hasAnalyZV,
    isFocused,
    fetchMatchesData,
  ]);

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      await fetchMatchesData({ silent: true });
    } finally {
      setRefreshing(false);
    }
  };

  const handleRecalculate = () => {
    startCalculation(() => {
      fetchMatchesData({ silent: true });
    });
  };

  const [top, ...rest] = matches;

  const renderRecalculateAction = () => {
    if (!hasAnalyZV || matches.length === 0 || isCalculating) return null;
    return (
      <PressableScale
        style={styles.recalculateHeaderBtn}
        onPress={handleRecalculate}
        disabled={isCalculating}
        haptic="light"
        accessibilityRole="button"
        accessibilityLabel={t('matchups.recalculate')}
        hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
      >
        <Ionicons
          name="refresh"
          size={14}
          color={colors.accentStrong || colors.tealDark}
          style={styles.recalcIcon}
        />
        <Text style={styles.recalculateHeaderText}>{t('matchups.recalculate')}</Text>
      </PressableScale>
    );
  };

  return (
    <ScreenContainer edges={['top']}>
      <AuthenticatedAppChromeHeader />
      <ScreenHeader
        title={t('matchups.title')}
        alignment="start"
        rightAction={renderRecalculateAction()}
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
        {/* Calculating Status Banner with Ambient AIPulse */}
        {isCalculating && (
          <AIPulse active={isCalculating} style={styles.calculatingPulseWrap}>
            <Card style={styles.calculatingCard} padding="md">
              <BrandedAILoader
                size={28}
                color={colors.accent || colors.teal}
                active={isCalculating}
                style={{ marginBottom: spacing.xs }}
              />
              <Text style={styles.calculatingTitle}>{t('matchups.recalculating')}</Text>
              <Text style={styles.calculatingSubtitle}>
                {t('matchups.calculatingSubtitle', { progress: progressPercent })}
              </Text>
              <View style={styles.progressTrack}>
                <View style={[styles.progressFill, { width: `${progressPercent}%` }]} />
              </View>
              <TouchableOpacity
                style={styles.cancelCalcBtn}
                onPress={handleStopChecking}
                disabled={isCancelling}
                accessibilityRole="button"
                accessibilityLabel={t('matchups.stopChecking')}
                accessibilityState={{
                  disabled: isCancelling,
                  busy: isCancelling,
                }}
              >
                {isCancelling && (
                  <ActivityIndicator
                    size="small"
                    color={colors.accent || colors.teal}
                    style={{ marginRight: spacing.sm }}
                  />
                )}
                <Text style={styles.cancelCalcText}>{t('matchups.stopChecking')}</Text>
              </TouchableOpacity>
            </Card>
          </AIPulse>
        )}

        {/* Match Calculation Error */}
        {calculationError && (
          <Card style={styles.errorCard} padding="md">
            <Ionicons name="alert-circle-outline" size={24} color={colors.danger || '#EF4444'} />
            <Text style={styles.errorText}>{getLocalizedErrorMessage(calculationError, t)}</Text>
            <TouchableOpacity
              style={styles.retryBtn}
              onPress={handleRecalculate}
              accessibilityRole="button"
              accessibilityLabel={t('common.tryAgain')}
            >
              <Text style={styles.retryBtnText}>{t('common.tryAgain')}</Text>
            </TouchableOpacity>
          </Card>
        )}

        {/* Initial Loading */}
        {loading && hasAnalyZV && !refreshing && !isCalculating && (
          <View style={styles.centerContainer}>
            <ActivityIndicator size="large" color={colors.accent || colors.teal} />
            <Text style={styles.loadingText}>{t('matchups.loading')}</Text>
          </View>
        )}

        {/* API / Network Error */}
        {!loading && hasAnalyZV && error && !isCalculating && (
          <Card style={styles.errorCard} padding="lg">
            <Ionicons name="alert-circle-outline" size={36} color={colors.danger || '#EF4444'} />
            <Text style={styles.errorTitle}>{t('matchups.errorTitle')}</Text>
            <Text style={styles.errorText}>
              {t('errors.matchesLoadFailed', { defaultValue: t('matchups.errorTitle') })}
            </Text>
            <TouchableOpacity
              style={styles.retryBtn}
              onPress={fetchMatchesData}
              accessibilityRole="button"
              accessibilityLabel={t('matchups.retry')}
            >
              <Text style={styles.retryBtnText}>{t('matchups.retry')}</Text>
            </TouchableOpacity>
          </Card>
        )}

        {/* Empty State: No CV Analyzed */}
        {!isCalculating && !hasAnalyZV && (
          <Reveal delay={0}>
            <Card style={styles.emptyCard} padding="lg">
              <Ionicons name="document-text-outline" size={48} color={colors.accent || colors.teal} />
              <Text style={styles.emptyTitle}>{t('matchups.cvRequiredTitle')}</Text>
              <Text style={styles.emptySubtitle}>
                {t('matchups.cvRequiredSubtitle')}
              </Text>
              <GradientButton
                title={t('matchups.uploadCV')}
                color={colors.accent || colors.teal}
                onPress={() => navigation.navigate('CVUpload')}
                style={{ marginTop: spacing.xl, width: '100%' }}
              />
            </Card>
          </Reveal>
        )}

        {/* Empty State: CV Analyzed but No Matches Calculated */}
        {!loading && !error && !isCalculating && hasAnalyZV && matches.length === 0 && (
          <Reveal delay={0}>
            <Card style={styles.emptyCard} padding="lg">
              <Ionicons name="sparkles-outline" size={48} color={colors.accent || colors.teal} />
              <Text style={styles.emptyTitle}>{t('matchups.noMatchesTitle')}</Text>
              <Text style={styles.emptySubtitle}>
                {t('matchups.noMatchesSubtitle')}
              </Text>
              <GradientButton
                title={t('matchups.calculateMatches')}
                color={colors.accent || colors.teal}
                onPress={handleRecalculate}
                style={{ marginTop: spacing.xl, width: '100%' }}
              />
            </Card>
          </Reveal>
        )}

        {/* Populated Matchups List with Staggered Reveal */}
        {!loading && !error && !isCalculating && top && (
          <>
            {/* Top Highlight Card */}
            <Reveal delay={0}>
              <Card variant="highlight" style={styles.highlightCard} padding="md">
                <PressableScale
                  onPress={() =>
                    navigation.navigate('InternshipDetail', {
                      internshipId: top.internship.id,
                    })
                  }
                  scaleTo={0.985}
                  activeOpacity={0.85}
                  accessibilityRole="button"
                  accessibilityLabel={t('matchups.cardA11y', {
                    title: top.internship.title,
                    company: top.internship.company,
                  })}
                >
                  <View style={styles.highlightTop}>
                    <Ionicons name="flame" size={16} color="#F2812B" style={styles.flameIcon} />
                    <Text style={styles.highlightLabel}>{t('matchups.highestCompatibility')}</Text>
                  </View>

                  <View style={styles.highlightTitleRow}>
                    <Text style={styles.highlightTitle}>{top.internship.title}</Text>
                    <MatchBadge score={top.overall_score} />
                  </View>

                  <Text style={styles.highlightMeta}>
                    {top.internship.company} {'\u00b7'} {top.internship.location}
                  </Text>

                  <View style={styles.scoresSubRow}>
                    <Text style={styles.scoresSubText}>
                      {t('matchups.scoresSub', { skills: top.skill_score, vector: top.vector_score })}
                    </Text>
                  </View>
                </PressableScale>

                <PressableScale
                  style={styles.whyLinkWrap}
                  onPress={() =>
                    navigation.navigate('WhyYouMatch', {
                      matchId: top.match_id,
                      internshipId: top.internship.id,
                    })
                  }
                  scaleTo={0.98}
                  activeOpacity={0.8}
                  accessibilityRole="button"
                  accessibilityLabel={t('matchups.whyYouMatch')}
                >
                  <Text style={styles.whyLink}>{t('matchups.whyYouMatch')}</Text>
                  <Ionicons
                    name={isRTL ? "chevron-back" : "chevron-forward"}
                    size={14}
                    color={colors.primaryBlue}
                    style={styles.chevronIcon}
                  />
                </PressableScale>
              </Card>
            </Reveal>

            {/* Remaining Matches */}
            {rest.map((item, index) => (
              <Reveal key={item.match_id} delay={motionTokens.stagger.fast * (index + 1)}>
                <Card
                  style={[
                    styles.plainRowCard,
                    index === rest.length - 1 && { marginBottom: spacing.md },
                  ]}
                  padding="sm"
                >
                  <PressableScale
                    style={styles.plainRow}
                    onPress={() =>
                      navigation.navigate('InternshipDetail', {
                        internshipId: item.internship.id,
                      })
                    }
                    scaleTo={0.985}
                    activeOpacity={0.85}
                    accessibilityRole="button"
                    accessibilityLabel={t('matchups.cardA11y', {
                      title: item.internship.title,
                      company: item.internship.company,
                    })}
                  >
                    <View style={styles.plainRowMain}>
                      <Text style={styles.plainTitle}>{item.internship.title}</Text>
                      <Text style={styles.plainMeta}>
                        {item.internship.company} {'\u00b7'} {item.internship.location}
                      </Text>
                      <PressableScale
                        style={styles.plainWhyWrap}
                        onPress={() =>
                          navigation.navigate('WhyYouMatch', {
                            matchId: item.match_id,
                            internshipId: item.internship.id,
                          })
                        }
                        scaleTo={0.98}
                        activeOpacity={0.8}
                        accessibilityRole="button"
                        accessibilityLabel={t('matchups.whyYouMatchA11y', { title: item.internship.title })}
                      >
                        <Text style={styles.plainWhyLink}>{t('matchups.whyYouMatch')}</Text>
                        <Ionicons
                          name={isRTL ? "chevron-back" : "chevron-forward"}
                          size={12}
                          color={colors.primaryBlue}
                          style={styles.chevronIcon}
                        />
                      </PressableScale>
                    </View>
                    <MatchBadge score={item.overall_score} />
                  </PressableScale>
                </Card>
              </Reveal>
            ))}
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
  recalculateHeaderBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.accentSoft || '#E6F4F6',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs + 2,
    borderRadius: spacing.radii.sm,
    minHeight: 34,
  },
  recalcIcon: {
    marginEnd: spacing.xs,
  },
  recalculateHeaderText: {
    ...typography.caption,
    fontWeight: '600',
    color: colors.accentStrong || colors.tealDark,
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
  calculatingPulseWrap: {
    marginBottom: spacing.md,
  },
  calculatingCard: {
    alignItems: 'center',
  },
  calculatingTitle: {
    ...typography.cardTitle,
    color: colors.textPrimary || colors.textDark,
    marginTop: spacing.sm,
  },
  calculatingSubtitle: {
    ...typography.caption,
    color: colors.textSecondary || colors.textMuted,
    marginTop: spacing.xs,
    textAlign: 'center',
  },
  progressTrack: {
    width: '100%',
    height: 6,
    borderRadius: 3,
    backgroundColor: colors.borderSubtle || '#E2E8F0',
    overflow: 'hidden',
    marginTop: spacing.md,
  },
  progressFill: {
    height: 6,
    backgroundColor: colors.accent || colors.teal,
  },
  cancelCalcBtn: {
    marginTop: spacing.md,
    minHeight: spacing.minimumTouchTarget,
    justifyContent: 'center',
  },
  cancelCalcText: {
    ...typography.caption,
    color: colors.textSecondary || colors.textMuted,
    textDecorationLine: 'underline',
  },
  errorCard: {
    alignItems: 'center',
    marginBottom: spacing.md,
    borderColor: colors.dangerSoft || '#FEE2E2',
    backgroundColor: '#FEF2F2',
  },
  errorTitle: {
    ...typography.cardTitle,
    color: colors.danger || '#EF4444',
    marginTop: spacing.sm,
  },
  errorText: {
    ...typography.caption,
    color: colors.danger || '#EF4444',
    textAlign: 'center',
    marginTop: spacing.xs,
  },
  retryBtn: {
    marginTop: spacing.md,
    backgroundColor: colors.accent || colors.teal,
    paddingHorizontal: spacing.xl,
    paddingVertical: spacing.sm,
    borderRadius: spacing.radii.sm,
    minHeight: spacing.minimumTouchTarget,
    justifyContent: 'center',
  },
  retryBtnText: {
    ...typography.button,
    color: colors.textInverse || colors.white,
    fontSize: 13,
  },
  emptyCard: {
    alignItems: 'center',
    marginTop: spacing.md,
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
    marginTop: spacing.sm,
    lineHeight: 18,
  },
  highlightCard: {
    marginBottom: spacing.md,
  },
  highlightTop: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  flameIcon: {
    marginEnd: spacing.xs,
  },
  highlightLabel: {
    ...typography.eyebrow,
    color: '#D97706',
  },
  highlightTitleRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginTop: spacing.sm,
  },
  highlightTitle: {
    flex: 1,
    ...typography.cardTitle,
    color: colors.textPrimary || colors.textDark,
    marginEnd: spacing.sm,
  },
  highlightMeta: {
    ...typography.caption,
    color: colors.textSecondary || colors.textMuted,
    marginTop: spacing.xs,
  },
  scoresSubRow: {
    marginTop: spacing.sm,
  },
  scoresSubText: {
    ...typography.caption,
    color: colors.textTertiary || colors.textMuted,
    fontWeight: '500',
  },
  whyLinkWrap: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: spacing.md,
    paddingTop: spacing.sm,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.borderSubtle || colors.border,
    minHeight: spacing.minimumTouchTarget,
  },
  whyLink: {
    ...typography.bodyEmphasis,
    color: colors.info || colors.primaryBlue,
    fontSize: 13,
  },
  chevronIcon: {
    marginStart: spacing.xxs,
  },
  plainRowCard: {
    marginBottom: spacing.sm,
  },
  plainRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: spacing.xs,
    minHeight: spacing.minimumTouchTarget,
  },
  plainRowMain: {
    flex: 1,
    marginEnd: spacing.md,
  },
  plainTitle: {
    ...typography.cardTitle,
    fontSize: 14,
    color: colors.textPrimary || colors.textDark,
  },
  plainMeta: {
    ...typography.caption,
    color: colors.textSecondary || colors.textMuted,
    marginTop: spacing.xxs,
  },
  plainWhyWrap: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: spacing.xs,
    minHeight: 28,
  },
  plainWhyLink: {
    ...typography.caption,
    color: colors.info || colors.primaryBlue,
    fontWeight: '600',
  },
});
