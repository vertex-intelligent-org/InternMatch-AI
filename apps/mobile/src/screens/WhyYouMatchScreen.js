import React, { useEffect, useState, useCallback, useRef } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  ActivityIndicator,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTranslation } from 'react-i18next';
import colors from '../theme/colors';
import { spacing } from '../theme/spacing';
import { typography } from '../theme/typography';
import motionTokens from '../motion/motionTokens';
import ScreenContainer from '../components/ScreenContainer';
import ScreenHeader from '../components/ScreenHeader';
import Card from '../components/Card';
import Chip from '../components/Chip';
import AnimatedScoreRing from '../components/motion/AnimatedScoreRing';
import Reveal from '../components/motion/Reveal';
import { getMatchExplanation, ApiError } from '../services/api';
import { useLocalization } from '../localization/LocalizationContext';
import { useSubscription } from '../context/SubscriptionProvider';
import useSmoothAIProgress from '../hooks/useSmoothAIProgress';
import { useCancellableAIJob } from '../hooks/useCancellableAIJob';

export default function WhyYouMatchScreen({ route, navigation }) {
  const { t } = useTranslation();
  const {
    refreshAIUsage,
  } = useSubscription();
  const { locale } = useLocalization();
  const matchId = route?.params?.matchId;
  const internshipId = route?.params?.internshipId;

  const [explanation, setExplanation] = useState(null);
  const [loading, setLoading] = useState(true);

  const aiProgress = useSmoothAIProgress(
    loading,
    8,
    94,
    18000
  );
  const [error, setError] = useState(null);
  const [isNotFound, setIsNotFound] = useState(false);
  const requestGenerationRef = useRef(0);
  const cancelPromptVisibleRef =
    useRef(false);
  const allowNavigationRef =
    useRef(false);

  const {
    isProcessing: explanationJobProcessing,
    isCancelling: explanationCancelling,
    runAIJob: runExplanationJob,
    cancelAIJob: cancelExplanationJob,
  } = useCancellableAIJob();

  const applyExplanationResult =
    useCallback(
      (result) => {
        if (
          !result ||
          typeof result !== 'object'
        ) {
          setLoading(false);
          setError(
            'MATCH_EXPLANATION_FAILED'
          );
          return false;
        }

        setExplanation(result);
        setError(null);
        setIsNotFound(false);
        setLoading(false);

        refreshAIUsage().catch(
          (usageError) => {
            console.warn(
              'AI usage refresh after match explanation failed:',
              usageError
            );
          }
        );

        return true;
      },
      [refreshAIUsage]
    );

  const fetchExplanationData =
    useCallback(async () => {
      const generation =
        ++requestGenerationRef.current;

      if (!matchId) {
        if (
          generation !==
          requestGenerationRef.current
        ) {
          return;
        }

        setIsNotFound(true);
        setLoading(false);
        return;
      }

      setLoading(true);
      setError(null);
      setIsNotFound(false);

      try {
        const outcome =
          await runExplanationJob(
            () =>
              getMatchExplanation(
                matchId,
                locale
              )
          );

        if (
          generation !==
          requestGenerationRef.current
        ) {
          return;
        }

        if (
          outcome.status ===
          'completed'
        ) {
          applyExplanationResult(
            outcome.result
          );
          return;
        }

        if (
          outcome.status ===
          'quota_exceeded'
        ) {
          setLoading(false);

          refreshAIUsage().catch(
            (usageError) => {
              console.warn(
                'AI usage refresh after match quota response failed:',
                usageError
              );
            }
          );

          navigation.navigate(
            'Plans'
          );
          return;
        }

        if (
          outcome.status ===
            'cancelled' ||
          outcome.status ===
            'superseded' ||
          outcome.status === 'busy'
        ) {
          return;
        }

        setLoading(false);
        setError(
          'MATCH_EXPLANATION_FAILED'
        );
      } catch (err) {
        if (
          generation !==
          requestGenerationRef.current
        ) {
          return;
        }

        if (
          err instanceof ApiError &&
          err.status === 402 &&
          err.code ===
            'AI_QUOTA_EXCEEDED'
        ) {
          setLoading(false);

          refreshAIUsage().catch(
            (usageError) => {
              console.warn(
                'AI usage refresh after match quota response failed:',
                usageError
              );
            }
          );

          navigation.navigate(
            'Plans'
          );
        } else if (
          err instanceof ApiError &&
          err.status === 404
        ) {
          setLoading(false);
          setIsNotFound(true);
        } else if (
          err instanceof ApiError &&
          err.status === 429
        ) {
          setLoading(false);
          setError('SERVICE_BUSY');
        } else {
          console.warn(
            'Failed to load match explanation:',
            err
          );

          setLoading(false);
          setError(
            'MATCH_EXPLANATION_FAILED'
          );
        }
      }
    }, [
      applyExplanationResult,
      locale,
      matchId,
      navigation,
      refreshAIUsage,
      runExplanationJob,
    ]);

  const leaveWhyYouMatch =
    useCallback(
      (navigationAction = null) => {
        allowNavigationRef.current =
          true;

        if (navigationAction) {
          navigation.dispatch(
            navigationAction
          );
        } else {
          navigation.goBack();
        }
      },
      [navigation]
    );

  const requestExplanationCancellation =
    useCallback(
      (options = {}) => {
        const leaveAfterCancellation =
          options?.leaveAfterCancellation ===
          true;

        const navigationAction =
          options?.navigationAction || null;

        if (
          !loading ||
          !explanationJobProcessing ||
          explanationCancelling ||
          cancelPromptVisibleRef.current
        ) {
          if (
            leaveAfterCancellation &&
            !explanationJobProcessing
          ) {
            navigation.goBack();
          }

          return;
        }

        cancelPromptVisibleRef.current =
          true;

        Alert.alert(
          t('aiCancellation.title'),
          t('aiCancellation.message'),
          [
            {
              text: t(
                'aiCancellation.continue'
              ),
              style: 'cancel',
              onPress: () => {
                // Same server job continues.
                cancelPromptVisibleRef.current =
                  false;
              },
            },
            {
              text: t(
                'aiCancellation.cancel'
              ),
              style: 'destructive',
              onPress: async () => {
                try {
                  const outcome =
                    await cancelExplanationJob();

                  cancelPromptVisibleRef.current =
                    false;

                  if (
                    outcome.status ===
                    'completed'
                  ) {
                    // Completion won the race.
                    // Keep benefit; no refund claim.
                    applyExplanationResult(
                      outcome.result
                    );
                    return;
                  }

                  if (
                    outcome.status ===
                    'quota_exceeded'
                  ) {
                    setLoading(false);

                    refreshAIUsage().catch(
                      () => {}
                    );

                    navigation.navigate(
                      'Plans'
                    );
                    return;
                  }

                  if (
                    outcome.status ===
                    'cancelled'
                  ) {
                    setLoading(false);
                    setError(null);

                    if (
                      leaveAfterCancellation
                    ) {
                      leaveWhyYouMatch(
                        navigationAction
                      );
                    }

                    return;
                  }

                  if (
                    outcome.status ===
                    'failed'
                  ) {
                    setLoading(false);
                    setError(
                      'MATCH_EXPLANATION_FAILED'
                    );

                    if (
                      leaveAfterCancellation
                    ) {
                      leaveWhyYouMatch(
                        navigationAction
                      );
                    }
                  }
                } catch (error) {
                  console.warn(
                    'Match explanation cancellation failed:',
                    error
                  );

                  cancelPromptVisibleRef.current =
                    false;

                  Alert.alert(
                    t(
                      'aiCancellation.failedTitle'
                    ),
                    t(
                      'aiCancellation.failedMessage'
                    )
                  );
                }
              },
            },
          ],
          {
            cancelable: true,
            onDismiss: () => {
              cancelPromptVisibleRef.current =
                false;
            },
          }
        );
      },
      [
        applyExplanationResult,
        cancelExplanationJob,
        explanationCancelling,
        explanationJobProcessing,
        leaveWhyYouMatch,
        loading,
        navigation,
        refreshAIUsage,
        t,
      ]
    );

  const handleProtectedBackPress =
    useCallback(() => {
      if (
        loading &&
        explanationJobProcessing
      ) {
        requestExplanationCancellation({
          leaveAfterCancellation: true,
        });
        return;
      }

      navigation.goBack();
    }, [
      explanationJobProcessing,
      loading,
      navigation,
      requestExplanationCancellation,
    ]);

  useEffect(() => {
    const unsubscribe =
      navigation.addListener(
        'beforeRemove',
        (event) => {
          if (
            allowNavigationRef.current
          ) {
            allowNavigationRef.current =
              false;
            return;
          }

          if (
            !loading ||
            !explanationJobProcessing
          ) {
            return;
          }

          event.preventDefault();

          requestExplanationCancellation({
            leaveAfterCancellation: true,
            navigationAction:
              event.data.action,
          });
        }
      );

    return unsubscribe;
  }, [
    explanationJobProcessing,
    loading,
    navigation,
    requestExplanationCancellation,
  ]);

  useEffect(() => {
    fetchExplanationData();
  }, [fetchExplanationData]);

  return (
    <ScreenContainer edges={['top', 'bottom']}>
      <ScreenHeader
        title={t('whyYouMatch.title')}
        showBack={true}
        navigation={navigation}
        onBackPress={handleProtectedBackPress}
      />

      <ScrollView
        style={styles.screen}
        contentContainerStyle={styles.content}
        showsVerticalScrollIndicator={false}
      >
        {/* Loading State */}
        {loading && (
          <View style={styles.centerContainer}>
            <ActivityIndicator
              size="large"
              color={colors.accent || colors.teal}
            />
            <Text style={styles.loadingText}>
              {t('whyYouMatch.generating')}
            </Text>
            <Text style={styles.loadingSubtext}>
              {t('whyYouMatch.analyzingRequirements')}
            </Text>
            <TouchableOpacity
              style={styles.primaryButton}
              onPress={() =>
                requestExplanationCancellation()
              }
              disabled={explanationCancelling}
              accessibilityRole="button"
              accessibilityLabel={t(
                'aiCancellation.cancel'
              )}
            >
              <Text style={styles.primaryButtonText}>
                {explanationCancelling
                  ? t('aiCancellation.cancelling')
                  : t('aiCancellation.cancel')}
              </Text>
            </TouchableOpacity>
            <View style={styles.aiProgressTrack}>
              <View
                style={[
                  styles.aiProgressFill,
                  {
                    width: `${aiProgress}%`,
                  },
                ]}
              />
            </View>
            <Text
              style={styles.aiProgressText}
              accessibilityLiveRegion="polite"
            >
              {aiProgress}%
            </Text>
          </View>
        )}

        {/* 404 Not Found State */}
        {!loading && isNotFound && (
          <Card style={styles.statusCard} padding="lg">
            <Ionicons name="alert-circle-outline" size={48} color={colors.textTertiary || colors.textMuted} />
            <Text style={styles.cardTitle}>{t('whyYouMatch.notFoundTitle')}</Text>
            <Text style={styles.cardSubtitle}>
              {t('whyYouMatch.notFoundMessage')}
            </Text>
            <TouchableOpacity
              style={styles.primaryButton}
              onPress={() => navigation.goBack()}
              accessibilityRole="button"
              accessibilityLabel={t('whyYouMatch.backToMatchups')}
            >
              <Text style={styles.primaryButtonText}>{t('whyYouMatch.backToMatchups')}</Text>
            </TouchableOpacity>
          </Card>
        )}

        {/* Error State */}
        {!loading && !isNotFound && error && (
          <Card style={styles.errorCard} padding="lg">
            <Ionicons name="alert-circle-outline" size={48} color={colors.danger || '#EF4444'} />
            <Text style={styles.cardTitle}>{t('whyYouMatch.errorTitle')}</Text>
            <Text style={styles.cardSubtitle}>
              {error === 'SERVICE_BUSY'
                ? t('whyYouMatch.serviceBusy')
                : t('errors.matchExplanationFailed', { defaultValue: t('whyYouMatch.errorTitle') })}
            </Text>
            <TouchableOpacity
              style={styles.primaryButton}
              onPress={fetchExplanationData}
              accessibilityRole="button"
              accessibilityLabel={t('common.tryAgain')}
            >
              <Text style={styles.primaryButtonText}>{t('common.tryAgain')}</Text>
            </TouchableOpacity>
          </Card>
        )}

        {/* Populated Match Breakdown with Staggered Editorial Reveal */}
        {!loading && !isNotFound && !error && explanation && (
          <>
            {/* Sequence 1: Animated Compatibility Score Hero */}
            <Reveal delay={0}>
              <View style={styles.ringWrap}>
                <AnimatedScoreRing score={explanation.overall_score} />
                <Text style={styles.scoreLabel}>{t('whyYouMatch.overallFit')}</Text>
              </View>
            </Reveal>

            {/* Sequence 2: AI Narrative Fit Assessment */}
            {explanation.why_you_match ? (
              <Reveal delay={motionTokens.stagger.fast}>
                <Card style={styles.narrativeCard} padding="md">
                  <View style={styles.narrativeHeader}>
                    <Ionicons
                      name="sparkles"
                      size={16}
                      color={colors.accentStrong || colors.tealDark}
                      style={styles.headerIcon}
                    />
                    <Text style={styles.narrativeTitle}>{t('whyYouMatch.aiFitAssessment')}</Text>
                  </View>
                  <Text style={styles.narrativeBody}>{explanation.why_you_match}</Text>
                </Card>
              </Reveal>
            ) : null}

            {/* Sequence 3: Competencies & Skill Gaps */}
            <Reveal delay={motionTokens.stagger.normal}>
              {/* Matching Competencies */}
              <Text style={styles.sectionTitle}>{t('whyYouMatch.matchingCompetencies')}</Text>
              {explanation.matching_skills && explanation.matching_skills.length > 0 ? (
                <View style={styles.chipRow}>
                  {explanation.matching_skills.map((skill) => (
                    <Chip key={skill} label={skill} variant="skill" />
                  ))}
                </View>
              ) : (
                <Text style={styles.emptySkillsNotice}>{t('whyYouMatch.noSkillOverlaps')}</Text>
              )}

              {/* Identified Skill Gaps */}
              <Text style={styles.sectionTitle}>{t('whyYouMatch.identifiedGaps')}</Text>
              {explanation.missing_skills && explanation.missing_skills.length > 0 ? (
                <View style={styles.chipRow}>
                  {explanation.missing_skills.map((skill) => (
                    <Chip key={skill} label={skill} variant="gap" />
                  ))}
                </View>
              ) : (
                <Text style={styles.emptySkillsNotice}>{t('whyYouMatch.noMajorGaps')}</Text>
              )}

              {/* Skill Gap Analysis & Recommendations */}
              {explanation.skill_gap_analysis ? (
                <View style={styles.recommendationsBox}>
                  <View style={styles.recHeaderRow}>
                    <Ionicons
                      name="bulb-outline"
                      size={18}
                      color="#B45309"
                      style={styles.headerIcon}
                    />
                    <Text style={styles.recBoxTitle}>{t('whyYouMatch.gapAnalysisAndRecs')}</Text>
                  </View>

                  {explanation.skill_gap_analysis.summary ? (
                    <Text style={styles.recSummaryText}>
                      {explanation.skill_gap_analysis.summary}
                    </Text>
                  ) : null}

                  {explanation.skill_gap_analysis.recommendations &&
                  explanation.skill_gap_analysis.recommendations.length > 0 ? (
                    <View style={styles.recommendationsList}>
                      {explanation.skill_gap_analysis.recommendations.map((rec, idx) => (
                        <View key={idx} style={styles.recItemRow}>
                          <Ionicons
                            name="checkmark-circle"
                            size={16}
                            color={colors.accent || colors.teal}
                            style={styles.recIcon}
                          />
                          <Text style={styles.recItemText}>{rec}</Text>
                        </View>
                      ))}
                    </View>
                  ) : null}
                </View>
              ) : null}
            </Reveal>

            {/* Sequence 4: Personalized Cover Letter Generation CTA */}
            <Reveal delay={motionTokens.stagger.slow}>
              <Card variant="highlight" style={styles.generateCtaCard} padding="lg">
                <View style={styles.generateCtaHeader}>
                  <Ionicons
                    name="document-text-outline"
                    size={20}
                    color={colors.accent || colors.teal}
                    style={styles.headerIcon}
                  />
                  <Text style={styles.generateCtaTitle}>{t('whyYouMatch.personalizedApp')}</Text>
                </View>
                <Text style={styles.generateCtaSubtitle}>
                  {t('whyYouMatch.personalizedSubtitle')}
                </Text>
                <TouchableOpacity
                  style={styles.generateButton}
                  onPress={() =>
                    navigation.navigate('CoverLetterDraft', {
                      matchId,
                      internshipId,
                    })
                  }
                  accessibilityRole="button"
                  accessibilityLabel={t('whyYouMatch.generateCoverLetter')}
                  activeOpacity={0.85}
                >
                  <Ionicons
                    name="sparkles"
                    size={16}
                    color={colors.textInverse || colors.white}
                    style={styles.buttonIcon}
                  />
                  <Text style={styles.generateButtonText}>{t('whyYouMatch.generateCoverLetter')}</Text>
                </TouchableOpacity>
              </Card>
            </Reveal>
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
    paddingTop: spacing.sm,
    paddingBottom: spacing.xxxl,
  },
  centerContainer: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: spacing.xxxl * 2,
  },
  loadingText: {
    ...typography.bodyEmphasis,
    color: colors.textPrimary || colors.textDark,
    marginTop: spacing.lg,
  },
  loadingSubtext: {
    ...typography.caption,
    color: colors.textSecondary || colors.textMuted,
    marginTop: spacing.xs,
    textAlign: 'center',
  },
  statusCard: {
    alignItems: 'center',
    marginTop: spacing.xl,
  },
  errorCard: {
    alignItems: 'center',
    marginTop: spacing.xl,
    borderColor: colors.dangerSoft || '#FEE2E2',
    backgroundColor: '#FEF2F2',
  },
  cardTitle: {
    ...typography.cardTitle,
    color: colors.textPrimary || colors.textDark,
    marginTop: spacing.md,
  },
  cardSubtitle: {
    ...typography.caption,
    color: colors.textSecondary || colors.textMuted,
    textAlign: 'center',
    marginTop: spacing.xs,
    lineHeight: 18,
  },
  primaryButton: {
    marginTop: spacing.lg,
    backgroundColor: colors.accent || colors.teal,
    paddingHorizontal: spacing.xl,
    paddingVertical: spacing.sm,
    borderRadius: spacing.radii.sm,
    minHeight: spacing.minimumTouchTarget,
    justifyContent: 'center',
  },
  primaryButtonText: {
    ...typography.button,
    color: colors.textInverse || colors.white,
    fontSize: 14,
  },
  ringWrap: {
    alignItems: 'center',
    marginVertical: spacing.lg,
  },
  scoreLabel: {
    ...typography.caption,
    color: colors.textSecondary || colors.textMuted,
    fontWeight: '600',
    marginTop: spacing.sm,
  },
  narrativeCard: {
    marginBottom: spacing.lg,
  },
  narrativeHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: spacing.xs,
  },
  headerIcon: {
    marginEnd: spacing.xs,
  },
  narrativeTitle: {
    ...typography.cardTitle,
    fontSize: 15,
    color: colors.textPrimary || colors.textDark,
  },
  narrativeBody: {
    ...typography.body,
    color: colors.textSecondary || colors.textDark,
    lineHeight: 22,
  },
  sectionTitle: {
    ...typography.sectionTitle,
    color: colors.textPrimary || colors.textDark,
    marginTop: spacing.md,
    marginBottom: spacing.sm,
  },
  chipRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    marginBottom: spacing.sm,
  },
  emptySkillsNotice: {
    ...typography.caption,
    color: colors.textTertiary || colors.textMuted,
    fontStyle: 'italic',
    marginBottom: spacing.md,
  },
  recommendationsBox: {
    backgroundColor: '#FFFBEB',
    borderRadius: spacing.radii.md,
    padding: spacing.md,
    marginVertical: spacing.md,
    borderWidth: 1,
    borderColor: '#FDE68A',
  },
  recHeaderRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: spacing.xs,
  },
  recBoxTitle: {
    ...typography.bodyEmphasis,
    color: '#92400E',
    fontSize: 13,
  },
  recSummaryText: {
    ...typography.caption,
    color: '#78350F',
    lineHeight: 18,
    marginTop: spacing.xxs,
  },
  recommendationsList: {
    marginTop: spacing.sm,
    gap: spacing.xs,
  },
  recItemRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
  },
  recIcon: {
    marginEnd: spacing.xs,
    marginTop: 2,
  },
  recItemText: {
    flex: 1,
    ...typography.caption,
    color: '#78350F',
    lineHeight: 18,
  },
  generateCtaCard: {
    marginTop: spacing.lg,
    marginBottom: spacing.xl,
  },
  generateCtaHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: spacing.xs,
  },
  generateCtaTitle: {
    ...typography.cardTitle,
    color: colors.textPrimary || colors.textDark,
  },
  generateCtaSubtitle: {
    ...typography.caption,
    color: colors.textSecondary || colors.textMuted,
    marginTop: spacing.xxs,
    lineHeight: 18,
  },
  generateButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.accent || colors.teal,
    paddingVertical: spacing.md,
    borderRadius: spacing.radii.md,
    marginTop: spacing.lg,
    minHeight: spacing.minimumTouchTarget,
  },
  generateButtonText: {
    ...typography.button,
    color: colors.textInverse || colors.white,
    fontSize: 14,
  },
  buttonIcon: {
    marginEnd: spacing.xs,
  },
  aiProgressTrack: {
    width: '78%',
    height: 6,
    borderRadius: 999,
    backgroundColor: colors.border || '#D7E3E8',
    overflow: 'hidden',
    marginTop: spacing.md,
  },
  aiProgressFill: {
    height: '100%',
    borderRadius: 999,
    backgroundColor: colors.accent || colors.teal,
  },
  aiProgressText: {
    marginTop: spacing.xs,
    color: colors.textSecondary || colors.textMuted,
    fontSize: 12,
    fontWeight: '600',
  },
});
