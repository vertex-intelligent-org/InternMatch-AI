import React, { useState, useEffect, useCallback, useRef} from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  ActivityIndicator,
  TextInput,
  Alert,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTranslation } from 'react-i18next';
import colors from '../theme/colors';
import { spacing } from '../theme/spacing';
import { typography } from '../theme/typography';
import ScreenContainer from '../components/ScreenContainer';
import ScreenHeader from '../components/ScreenHeader';
import Card from '../components/Card';
import GradientButton from '../components/GradientButton';
import AIPulse from '../components/motion/AIPulse';
import Reveal from '../components/motion/Reveal';
import BrandedAILoader from '../components/motion/BrandedAILoader';
import { useApplicationGeneration } from '../hooks/useApplicationGeneration';
import { discardApplicationDraft, getApplications } from '../services/api';
import { getLocalizedErrorMessage } from '../localization/errorMessages';
import haptics from '../services/haptics';
import { useSubscription } from '../context/SubscriptionProvider';

const TONE_PRESETS = ['Professional', 'Concise', 'Enthusiastic'];
const LOCALES = [
  { code: 'en', key: 'languages.en', defaultLabel: 'English' },
  { code: 'tr', key: 'languages.tr', defaultLabel: 'Türkçe' },
  { code: 'ar', key: 'languages.ar', defaultLabel: 'العربية' },
];

export default function CoverLetterDraftScreen({ route, navigation }) {
  const { t } = useTranslation();
  const {
    aiUsage,
    refreshAIUsage,
  } = useSubscription();

  const applicationSupportUsage =
    aiUsage?.features?.find(
      (feature) =>
        feature.feature_key ===
        'application_support'
    );

  const isApplicationSupportExhausted =
    applicationSupportUsage?.remaining === 0;
  const matchId = route?.params?.matchId;
  const internshipId = route?.params?.internshipId;

  const [tone, setTone] = useState('Professional');
  const [contentLocale, setContentLocale] = useState('en');
  const [application, setApplication] = useState(null);
  const [loadingExisting, setLoadingExisting] = useState(true);
  const [resolveError, setResolveError] = useState(null);
  const [isDiscarding, setIsDiscarding] = useState(false);
  const [generationStarting, setGenerationStarting] = useState(false);
  const cancelPromptVisibleRef = useRef(false);
  const allowNavigationRef = useRef(false);
  const generationPreflightInFlightRef = useRef(false);
  const discardPromptVisibleRef = useRef(false);
  const discardInFlightRef = useRef(false);

  const {
    isGenerating,
    isCancelling,
    progressPercent,
    generationError,
    startGeneration,
    cancelGeneration,
    isGenerationActive,
  } = useApplicationGeneration();

  const requestGenerationCancellation = (options = {}) => {
    const leaveAfterCancellation =
      options?.leaveAfterCancellation === true;
    const navigationAction =
      options?.navigationAction || null;

    if (
      !isGenerating ||
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
            // Continue means exactly that: no API call, no restart,
            // no polling reset, and no progress reset.
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
                await cancelGeneration();

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
                'Application generation cancellation failed:',
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
  };

  const handleProtectedBackPress = () => {
    if (isGenerating) {
      requestGenerationCancellation({
        leaveAfterCancellation: true,
      });
      return;
    }

    navigation.goBack();
  };

  useEffect(() => {
    const unsubscribe = navigation.addListener(
      'beforeRemove',
      (event) => {
        if (allowNavigationRef.current) {
          allowNavigationRef.current = false;
          return;
        }

        if (!isGenerating) {
          return;
        }

        // Protect Android hardware back, iOS back gestures,
        // and navigator-driven screen removal.
        event.preventDefault();

        requestGenerationCancellation({
          leaveAfterCancellation: true,
          navigationAction: event.data.action,
        });
      }
    );

    return unsubscribe;
  }, [
    navigation,
    isGenerating,
    isCancelling,
  ]);

  // Check if an application with generated cover letter already exists for this internship
  const checkExistingApplication = useCallback(async () => {
    if (!internshipId) {
      setLoadingExisting(false);
      return;
    }

    try {
      const res = await getApplications();
      const existing = res.applications.find(
        (app) => app.internship_id === internshipId && Boolean(app.generated_cover_letter)
      );
      if (existing) {
        setApplication(existing);
      }
    } catch (err) {
      console.warn('Failed to check existing application:', err);
    } finally {
      setLoadingExisting(false);
    }
  }, [internshipId]);

  useEffect(() => {
    checkExistingApplication();
  }, [checkExistingApplication]);

  useEffect(() => {
    if (
      generationError !==
      'AI_QUOTA_EXCEEDED'
    ) {
      return;
    }

    refreshAIUsage().catch(
      (usageError) => {
        console.warn(
          'AI usage refresh after application quota response failed:',
          usageError
        );
      }
    );

    navigation.navigate('Plans');
  }, [
    generationError,
    navigation,
    refreshAIUsage,
  ]);

  const handleGenerate = async () => {
    if (
      generationPreflightInFlightRef.current ||
      isGenerationActive() ||
      isGenerating ||
      discardInFlightRef.current ||
      isDiscarding
    ) {
      return;
    }

    generationPreflightInFlightRef.current = true;
    setGenerationStarting(true);

    try {
    if (isApplicationSupportExhausted) {
      try {
        const latestUsage =
          await refreshAIUsage();

        const latestSupportUsage =
          latestUsage?.features?.find(
            (feature) =>
              feature.feature_key ===
              'application_support'
          );

        if (
          !latestSupportUsage ||
          latestSupportUsage.remaining === 0
        ) {
          navigation.navigate('Plans');
          return;
        }
      } catch (usageError) {
        console.warn(
          'AI usage refresh before application support failed:',
          usageError
        );
        navigation.navigate('Plans');
        return;
      }
    }

    if (!matchId) {
      setResolveError('MISSING_MATCH_REF');
      return;
    }

    setResolveError(null);

    const selectedTone = tone.trim() || 'Professional';

    startGeneration(
      {
        match_id: matchId,
        tone: selectedTone,
        content_locale: contentLocale,
      },
      async (jobResult) => {
        try {
          await refreshAIUsage();
        } catch (usageError) {
          console.warn(
            'AI usage refresh after application generation failed:',
            usageError
          );
        }

        haptics.success();
        try {
          const listRes = await getApplications();
          let resolvedApp = null;

          if (jobResult && jobResult.application_id) {
            resolvedApp = listRes.applications.find(
              (a) => a.id === jobResult.application_id
            );
          }

          if (!resolvedApp && internshipId) {
            resolvedApp = listRes.applications.find(
              (a) => a.internship_id === internshipId
            );
          }

          if (resolvedApp) {
            setApplication(resolvedApp);
          } else {
            setResolveError('SYNC_FAILED');
          }
        } catch (err) {
          console.warn('Failed to refresh applications after generation:', err);
          setResolveError('SYNC_FAILED');
        }
      }
    );
    } finally {
      generationPreflightInFlightRef.current = false;
      setGenerationStarting(false);
    }
  };

  const handleDiscardDraft = () => {
    if (
      !application ||
      application.status !== 'saved' ||
      isDiscarding ||
      discardPromptVisibleRef.current ||
      discardInFlightRef.current ||
      generationPreflightInFlightRef.current ||
      isGenerationActive() ||
      isGenerating
    ) {
      return;
    }

    discardPromptVisibleRef.current = true;

    Alert.alert(
      t('coverLetterDraft.discardTitle'),
      t('coverLetterDraft.discardMessage'),
      [
        {
          text: t('coverLetterDraft.discardCancel'),
          style: 'cancel',
          onPress: () => {
            discardPromptVisibleRef.current = false;
          },
        },
        {
          text: t('coverLetterDraft.discardConfirm'),
          style: 'destructive',
          onPress: async () => {
            discardPromptVisibleRef.current = false;

            if (
              discardInFlightRef.current ||
              generationPreflightInFlightRef.current ||
              isGenerationActive()
            ) {
              return;
            }

            discardInFlightRef.current = true;
            setIsDiscarding(true);

            try {
              await discardApplicationDraft(application.id);
              setApplication(null);
              navigation.goBack();
            } catch (error) {
              console.warn('Failed to discard application draft:', error);
              Alert.alert(
                t('coverLetterDraft.discardErrorTitle'),
                t('coverLetterDraft.discardErrorMessage')
              );
            } finally {
              discardInFlightRef.current = false;
              setIsDiscarding(false);
            }
          },
        },
      ],
      {
        cancelable: true,
        onDismiss: () => {
          discardPromptVisibleRef.current = false;
        },
      }
    );
  };

  const handleProceedToEdit = () => {
    if (!application) return;

    navigation.navigate('CoverLetter', {
      applicationId: application.id,
      draft: application.generated_cover_letter || '',
      currentStatus: application.status,
      internshipId: application.internship_id || internshipId,
      companyName: application.company_name,
      jobTitle: application.job_title,
    });
  };

  if (!matchId && !internshipId) {
    return (
      <ScreenContainer edges={['top', 'bottom']}>
        <ScreenHeader title={t('coverLetterDraft.title')} showBack={true} navigation={navigation} />
        <Card style={styles.centerScreenCard} padding="lg">
          <Ionicons name="alert-circle-outline" size={48} color={colors.textTertiary || colors.textMuted} />
          <Text style={styles.errorScreenTitle}>{t('coverLetterDraft.missingRefTitle')}</Text>
          <Text style={styles.errorScreenSubtitle}>
            {t('coverLetterDraft.missingRefSubtitle')}
          </Text>
          <TouchableOpacity
            style={styles.primaryBtn}
            onPress={() => navigation.goBack()}
            accessibilityRole="button"
            accessibilityLabel={t('coverLetterDraft.goBack')}
          >
            <Text style={styles.primaryBtnText}>{t('coverLetterDraft.goBack')}</Text>
          </TouchableOpacity>
        </Card>
      </ScreenContainer>
    );
  }

  return (
    <ScreenContainer edges={['top', 'bottom']}>
      <ScreenHeader
        title={t('coverLetterDraft.title')}
        showBack={true}
        navigation={navigation}
        onBackPress={handleProtectedBackPress}
      />

      <ScrollView
        style={styles.screen}
        contentContainerStyle={styles.content}
        showsVerticalScrollIndicator={false}
      >
        <Text style={styles.subtitle}>
          {t('coverLetterDraft.subtitle')}
        </Text>

        {/* Loading Existing Draft Check */}
        {loadingExisting && (
          <View style={styles.centerLoading}>
            <ActivityIndicator size="small" color={colors.accent || colors.teal} />
            <Text style={styles.loadingText}>{t('coverLetterDraft.checkingDrafts')}</Text>
          </View>
        )}

        {/* Configuration Section (Tone & Locale) */}
        {!loadingExisting && !isGenerating && (
          <Card style={styles.configCard} padding="md">
            <Text style={styles.sectionHeader}>{t('coverLetterDraft.settingsTitle')}</Text>

            {/* Tone Selector */}
            <Text style={styles.fieldLabel}>{t('coverLetterDraft.toneLabel')}</Text>
            <View style={styles.presetRow}>
              {TONE_PRESETS.map((preset) => {
                const localizedPreset = t(`coverLetterDraft.tones.${preset}`, { defaultValue: preset });
                return (
                  <TouchableOpacity
                    key={preset}
                    style={[
                      styles.presetChip,
                      tone === preset && styles.presetChipActive,
                    ]}
                    onPress={() => setTone(preset)}
                    accessibilityRole="button"
                    accessibilityLabel={`${t('coverLetterDraft.toneLabel')}: ${localizedPreset}`}
                    hitSlop={{ top: 4, bottom: 4, left: 4, right: 4 }}
                  >
                    <Text
                      style={[
                        styles.presetChipText,
                        tone === preset && styles.presetChipTextActive,
                      ]}
                    >
                      {localizedPreset}
                    </Text>
                  </TouchableOpacity>
                );
              })}
            </View>
            <TextInput
              style={styles.customToneInput}
              value={tone}
              onChangeText={setTone}
              placeholder={t('coverLetterDraft.tonePlaceholder')}
              placeholderTextColor={colors.textTertiary || colors.textMuted}
              maxLength={60}
            />

            {/* Locale Selector */}
            <Text style={[styles.fieldLabel, { marginTop: spacing.md }]}>{t('coverLetterDraft.languageLabel')}</Text>
            <View style={styles.presetRow}>
              {LOCALES.map((loc) => {
                const label = t(loc.key, { defaultValue: loc.defaultLabel });
                return (
                  <TouchableOpacity
                    key={loc.code}
                    style={[
                      styles.presetChip,
                      contentLocale === loc.code && styles.presetChipActive,
                    ]}
                    onPress={() => setContentLocale(loc.code)}
                    accessibilityRole="button"
                    accessibilityLabel={`${t('coverLetterDraft.languageLabel')}: ${label}`}
                    hitSlop={{ top: 4, bottom: 4, left: 4, right: 4 }}
                  >
                    <Text
                      style={[
                        styles.presetChipText,
                        contentLocale === loc.code && styles.presetChipTextActive,
                      ]}
                    >
                      {label}
                    </Text>
                  </TouchableOpacity>
                );
              })}
            </View>
          </Card>
        )}

        {/* In-Progress Generating State with Ambient AIPulse */}
        {isGenerating && (
          <AIPulse active={isGenerating} style={styles.generatingPulseWrap}>
            <Card style={styles.generatingCard} padding="lg">
              <BrandedAILoader
                size={32}
                color={colors.accent || colors.teal}
                active={isGenerating}
                style={{ marginBottom: spacing.xs }}
              />
              <Text style={styles.generatingTitle}>{t('coverLetterDraft.generatingTitle')}</Text>
              <Text style={styles.generatingSubtitle}>
                {t('coverLetterDraft.generatingSubtitle', { progress: progressPercent })}
              </Text>

              <View style={styles.progressTrack}>
                <View style={[styles.progressFill, { width: `${progressPercent}%` }]} />
              </View>
              <Text style={styles.percentText}>{progressPercent}%</Text>

              <TouchableOpacity
                style={styles.cancelBtn}
                onPress={() => requestGenerationCancellation()}
                disabled={isCancelling}
                accessibilityRole="button"
                accessibilityLabel={t('coverLetterDraft.stopChecking')}
              >
                <Text style={styles.cancelBtnText}>{t('coverLetterDraft.stopChecking')}</Text>
              </TouchableOpacity>
            </Card>
          </AIPulse>
        )}

        {/* Generation Error State */}
        {generationError && !isGenerating && (
          <Card style={styles.errorCard} padding="md">
            <Ionicons name="alert-circle-outline" size={28} color={colors.danger || '#EF4444'} />
            <Text style={styles.errorCardTitle}>{t('coverLetterDraft.generationErrorTitle')}</Text>
            <Text style={styles.errorCardMessage}>{getLocalizedErrorMessage(generationError, t)}</Text>
            <TouchableOpacity
              style={styles.retryBtn}
              onPress={handleGenerate}
              disabled={generationStarting}
              accessibilityRole="button"
              accessibilityState={{
                disabled: generationStarting,
                busy: generationStarting,
              }}
              accessibilityLabel={t('common.tryAgain')}
            >
              {generationStarting ? (
                <ActivityIndicator
                  size="small"
                  color={colors.accent || colors.teal}
                />
              ) : (
                <Text style={styles.retryBtnText}>{t('common.tryAgain')}</Text>
              )}
            </TouchableOpacity>
          </Card>
        )}

        {/* Resolution Error */}
        {resolveError && !isGenerating && (
          <Card style={styles.errorCard} padding="md">
            <Ionicons name="alert-circle-outline" size={28} color={colors.warning || '#F59E0B'} />
            <Text style={styles.errorCardTitle}>{t('coverLetterDraft.syncTitle')}</Text>
            <Text style={styles.errorCardMessage}>
              {resolveError === 'MISSING_MATCH_REF'
                ? t('coverLetterDraft.missingRefSubtitle', { defaultValue: t('coverLetterDraft.missingRefTitle') })
                : resolveError === 'SYNC_FAILED'
                  ? t('coverLetterDraft.syncFailedMsg', { defaultValue: t('errors.coverLetterGenerateFailed') })
                  : getLocalizedErrorMessage(resolveError, t)}
            </Text>
            <TouchableOpacity
              style={styles.retryBtn}
              onPress={checkExistingApplication}
              accessibilityRole="button"
              accessibilityLabel={t('coverLetterDraft.refreshApplications')}
            >
              <Text style={styles.retryBtnText}>{t('coverLetterDraft.refreshApplications')}</Text>
            </TouchableOpacity>
          </Card>
        )}

        {/* Display Generated Cover Letter with Reveal */}
        {!loadingExisting && !isGenerating && application && application.generated_cover_letter ? (
          <Reveal delay={0}>
            <View style={styles.resultSection}>
              <View style={styles.resultHeaderRow}>
                <Text style={styles.resultLabel}>{t('coverLetterDraft.generatedDraftTitle')}</Text>
                <View style={styles.savedBadge}>
                  <Ionicons
                    name="checkmark-circle"
                    size={12}
                    color={colors.accent || colors.teal}
                    style={styles.savedIcon}
                  />
                  <Text style={styles.savedBadgeText}>{t('coverLetterDraft.savedInTracker')}</Text>
                </View>
              </View>

              <Card style={styles.draftCard} padding="md">
                <Text style={styles.draftText}>{application.generated_cover_letter}</Text>
              </Card>

              <GradientButton
                title={t('coverLetterDraft.reviewEdit')}
                color={colors.accentStrong || colors.tealDark}
                onPress={handleProceedToEdit}
                style={{ marginTop: spacing.lg }}
              />

              <TouchableOpacity
                style={styles.recreateBtn}
                onPress={handleGenerate}
                disabled={generationStarting || isDiscarding}
                accessibilityRole="button"
                accessibilityState={{
                  disabled: generationStarting || isDiscarding,
                  busy: generationStarting,
                }}
                accessibilityLabel={t('coverLetterDraft.regenerate')}
              >
                {generationStarting ? (
                  <ActivityIndicator
                    size="small"
                    color={colors.accentStrong || colors.tealDark}
                    style={styles.recreateIcon}
                  />
                ) : (
                  <Ionicons
                    name="refresh-outline"
                    size={16}
                    color={colors.accentStrong || colors.tealDark}
                    style={styles.recreateIcon}
                  />
                )}
                <Text style={styles.recreateBtnText}>{t('coverLetterDraft.regenerate')}</Text>
              </TouchableOpacity>

              {application.status === 'saved' ? (
                <TouchableOpacity
                  style={styles.discardBtn}
                  onPress={handleDiscardDraft}
                  disabled={isDiscarding || generationStarting}
                  accessibilityRole="button"
                  accessibilityState={{
                    disabled: isDiscarding || generationStarting,
                    busy: isDiscarding,
                  }}
                  accessibilityLabel={t('coverLetterDraft.discardAction')}
                >
                  {isDiscarding ? (
                    <ActivityIndicator
                      size="small"
                      color={colors.error || '#B42318'}
                      style={styles.recreateIcon}
                    />
                  ) : (
                    <Ionicons
                      name="trash-outline"
                      size={16}
                      color={colors.error || '#B42318'}
                      style={styles.recreateIcon}
                    />
                  )}
                  <Text style={styles.discardBtnText}>
                    {isDiscarding
                      ? t('coverLetterDraft.discarding')
                      : t('coverLetterDraft.discardAction')}
                  </Text>
                </TouchableOpacity>
              ) : null}
            </View>
          </Reveal>
        ) : null}

        {/* Initial Generate Action (When no draft exists yet) */}
        {!loadingExisting && !isGenerating && (!application || !application.generated_cover_letter) ? (
          <GradientButton
            title={t('coverLetterDraft.generateBtn')}
            color={colors.accent || colors.teal}
            onPress={handleGenerate}
            disabled={generationStarting}
            loading={generationStarting}
            style={{ marginTop: spacing.xl }}
          />
        ) : null}
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
    paddingBottom: spacing.xxxl,
  },
  subtitle: {
    ...typography.caption,
    color: colors.textSecondary || colors.textMuted,
    textAlign: 'center',
    marginBottom: spacing.lg,
    lineHeight: 18,
  },
  centerScreenCard: {
    alignItems: 'center',
    margin: spacing.xl,
  },
  errorScreenTitle: {
    ...typography.cardTitle,
    color: colors.textPrimary || colors.textDark,
    marginTop: spacing.md,
  },
  errorScreenSubtitle: {
    ...typography.caption,
    color: colors.textSecondary || colors.textMuted,
    textAlign: 'center',
    marginTop: spacing.xs,
    lineHeight: 18,
  },
  primaryBtn: {
    marginTop: spacing.lg,
    backgroundColor: colors.accent || colors.teal,
    paddingHorizontal: spacing.xl,
    paddingVertical: spacing.sm,
    borderRadius: spacing.radii.sm,
    minHeight: spacing.minimumTouchTarget,
    justifyContent: 'center',
  },
  primaryBtnText: {
    ...typography.button,
    color: colors.textInverse || colors.white,
    fontSize: 14,
  },
  centerLoading: {
    alignItems: 'center',
    paddingVertical: spacing.xl,
  },
  loadingText: {
    ...typography.caption,
    color: colors.textSecondary || colors.textMuted,
    marginTop: spacing.sm,
  },
  configCard: {
    marginBottom: spacing.md,
  },
  sectionHeader: {
    ...typography.eyebrow,
    color: colors.textSecondary || colors.textMuted,
    marginBottom: spacing.md,
  },
  fieldLabel: {
    ...typography.bodyEmphasis,
    color: colors.textPrimary || colors.textDark,
    marginBottom: spacing.sm,
    fontSize: 13,
  },
  presetRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
  },
  presetChip: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs + 2,
    borderRadius: spacing.radii.pill,
    backgroundColor: colors.surfaceSubtle || colors.cardBg,
    borderWidth: 1,
    borderColor: colors.borderSubtle || colors.border,
    minHeight: 36,
    justifyContent: 'center',
  },
  presetChipActive: {
    backgroundColor: colors.accent || colors.teal,
    borderColor: colors.accent || colors.teal,
  },
  presetChipText: {
    ...typography.caption,
    color: colors.textPrimary || colors.textDark,
    fontWeight: '500',
  },
  presetChipTextActive: {
    color: colors.textInverse || colors.white,
    fontWeight: '700',
  },
  customToneInput: {
    borderWidth: 1,
    borderColor: colors.borderSubtle || colors.border,
    borderRadius: spacing.radii.sm,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    marginTop: spacing.sm,
    fontSize: 13,
    color: colors.textPrimary || colors.textDark,
    backgroundColor: colors.surface || colors.white,
    minHeight: 40,
  },
  generatingPulseWrap: {
    marginVertical: spacing.md,
  },
  generatingCard: {
    alignItems: 'center',
  },
  generatingTitle: {
    ...typography.cardTitle,
    color: colors.textPrimary || colors.textDark,
    marginTop: spacing.md,
  },
  generatingSubtitle: {
    ...typography.caption,
    color: colors.textSecondary || colors.textMuted,
    textAlign: 'center',
    marginTop: spacing.xs,
    lineHeight: 18,
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
  percentText: {
    ...typography.caption,
    fontWeight: '600',
    color: colors.accent || colors.teal,
    alignSelf: 'flex-end',
    marginTop: spacing.xs,
    writingDirection: 'ltr',
  },
  cancelBtn: {
    marginTop: spacing.md,
    minHeight: spacing.minimumTouchTarget,
    justifyContent: 'center',
  },
  cancelBtnText: {
    ...typography.caption,
    color: colors.textSecondary || colors.textMuted,
    textDecorationLine: 'underline',
  },
  errorCard: {
    alignItems: 'center',
    borderColor: colors.dangerSoft || '#FEE2E2',
    backgroundColor: '#FEF2F2',
    marginVertical: spacing.md,
  },
  errorCardTitle: {
    ...typography.cardTitle,
    color: colors.danger || '#EF4444',
    marginTop: spacing.sm,
  },
  errorCardMessage: {
    ...typography.caption,
    color: colors.danger || '#EF4444',
    textAlign: 'center',
    marginTop: spacing.xs,
    lineHeight: 18,
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
  resultSection: {
    marginTop: spacing.xs,
  },
  resultHeaderRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: spacing.sm,
  },
  resultLabel: {
    ...typography.eyebrow,
    color: colors.textSecondary || colors.textMuted,
  },
  savedBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.accentSoft || '#E6F4F6',
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xxs + 1,
    borderRadius: spacing.radii.sm,
  },
  savedBadgeText: {
    ...typography.caption,
    fontWeight: '600',
    color: colors.accentStrong || colors.tealDark,
    fontSize: 11,
  },
  savedIcon: {
    marginEnd: spacing.xxs + 1,
  },
  draftCard: {
    minHeight: 180,
    borderColor: colors.accent || colors.teal,
    borderWidth: 1.5,
  },
  draftText: {
    ...typography.body,
    color: colors.textPrimary || colors.textDark,
    lineHeight: 22,
  },
  recreateBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: spacing.md,
    marginTop: spacing.sm,
    backgroundColor: colors.accentSoft || '#E6F4F6',
    borderRadius: spacing.radii.md,
    minHeight: spacing.minimumTouchTarget,
  },
  recreateBtnText: {
    ...typography.button,
    color: colors.accentStrong || colors.tealDark,
    fontSize: 13,
  },
  discardBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: spacing.md,
    marginTop: spacing.sm,
    borderWidth: 1,
    borderColor: colors.error || '#B42318',
    borderRadius: spacing.radii.md,
    minHeight: spacing.minimumTouchTarget,
  },
  discardBtnText: {
    ...typography.button,
    color: colors.error || '#B42318',
    fontSize: 13,
  },
  recreateIcon: {
    marginEnd: spacing.xs,
  },
});
