import React, { useCallback, useRef, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  Alert,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTranslation } from 'react-i18next';
import colors from '../theme/colors';
import { spacing } from '../theme/spacing';
import { typography } from '../theme/typography';
import ScreenContainer from '../components/ScreenContainer';
import ScreenHeader from '../components/ScreenHeader';
import GlassSurface from '../components/GlassSurface';
import GradientButton from '../components/GradientButton';
import PlanBadge from '../components/PlanBadge';
import { useProfile } from '../context/ProfileContext';
import { useLocalization } from '../localization/LocalizationContext';
import { useRevenueCat } from '../context/RevenueCatProvider';
import { useSubscription } from '../context/SubscriptionProvider';
import { getSubscriptionSnapshot } from '../services/subscriptionService';
import haptics from '../services/haptics';

const AI_USAGE_FEATURES = [
  {
    featureKey: 'cv_analysis',
    labelKey: 'plans.aiUsage.cvAnalysis',
  },
  {
    featureKey: 'match_explanation',
    labelKey: 'plans.aiUsage.matchExplanation',
  },
  {
    featureKey: 'application_support',
    labelKey: 'plans.aiUsage.applicationSupport',
  },
  {
    featureKey: 'interview_prep',
    labelKey: 'plans.aiUsage.interviewPrep',
  },
];

export default function PlansScreen({ navigation }) {
  const { t } = useTranslation();
  const { isRTL } = useLocalization();
  const { profile } = useProfile();
  const {
    runtimeState,
    candidateState,
    isPurchasing,
    isRestoring,
    purchaseProStudent,
    restorePurchases,
  } = useRevenueCat();

  const {
    backendSubscription,
    aiUsage,
    reconcileSubscription,
  } = useSubscription();
  const subscriptionSnapshot = getSubscriptionSnapshot(
    profile?.preferences?.account_type,
    candidateState,
    backendSubscription
  );
  const {
    accountType,
    availablePlans,
    dynamicPriceString,
    purchaseState,
  } = subscriptionSnapshot;
  const isEmployer = accountType === 'employer';
  const screenSubtitle = isEmployer ? t('plans.employer.subtitle') : t('plans.subtitle');

  const isPurchaseReady = Boolean(
    purchaseState?.providerVerified === true &&
    purchaseState?.purchasesAvailable === true
  );

  const purchaseFlowInFlightRef = useRef(false);
  const [isPurchaseFlowPending, setIsPurchaseFlowPending] = useState(false);

  const isPurchaseFlowBusy =
    isPurchasing || isPurchaseFlowPending;

  const handleEmployerUpgrade = useCallback((planTitle) => {
    haptics.selection();
    Alert.alert(
      t('plans.previewAlert.title'),
      t('plans.previewAlert.message'),
      [{ text: t('common.close', { defaultValue: 'OK' }), style: 'default' }]
    );
  }, [t]);

  const handleCandidateUpgrade = useCallback(async () => {
    if (
      purchaseFlowInFlightRef.current ||
      isPurchasing ||
      isRestoring ||
      !isPurchaseReady
    ) {
      return;
    }

    purchaseFlowInFlightRef.current = true;
    setIsPurchaseFlowPending(true);
    haptics.selection();

    try {
      let result;

      try {
        result = await purchaseProStudent();
      } catch {
        Alert.alert(
          t('plans.purchaseFailed.title'),
          t('plans.purchaseFailed.message'),
          [{ text: t('common.close', { defaultValue: 'OK' }), style: 'default' }]
        );
        return;
      }

      if (result.reason === 'identity_changed') {
        return;
      }

      if (result.success) {
        let reconciliation;

        try {
          reconciliation = await reconcileSubscription();
        } catch {
          Alert.alert(
            t('plans.pendingVerification.title'),
            t('plans.pendingVerification.message'),
            [{ text: t('common.close', { defaultValue: 'OK' }), style: 'default' }]
          );
          return;
        }

        const backendConfirmedPro =
          reconciliation?.subscription?.plan === 'pro_student' &&
          reconciliation?.subscription?.is_active === true;

        if (!backendConfirmedPro) {
          Alert.alert(
            t('plans.pendingVerification.title'),
            t('plans.pendingVerification.message'),
            [{ text: t('common.close', { defaultValue: 'OK' }), style: 'default' }]
          );
          return;
        }

        haptics.success();
        Alert.alert(
          t('plans.purchaseSuccess.title'),
          t('plans.purchaseSuccess.message'),
          [{ text: t('common.close', { defaultValue: 'OK' }), style: 'default' }]
        );
      } else if (result.cancelled) {
        // Quiet dismissal for user cancellation
      } else if (result.reason === 'entitlement_not_active') {
        Alert.alert(
          t('plans.pendingVerification.title'),
          t('plans.pendingVerification.message'),
          [{ text: t('common.close', { defaultValue: 'OK' }), style: 'default' }]
        );
      } else {
        haptics.selection();
        Alert.alert(
          t('plans.purchaseFailed.title'),
          t('plans.purchaseFailed.message'),
          [{ text: t('common.close', { defaultValue: 'OK' }), style: 'default' }]
        );
      }
    } finally {
      purchaseFlowInFlightRef.current = false;
      setIsPurchaseFlowPending(false);
    }
  }, [
    isPurchasing,
    isRestoring,
    isPurchaseReady,
    purchaseProStudent,
    reconcileSubscription,
    t,
  ]);

  const handleRestore = useCallback(async () => {
    if (
      purchaseFlowInFlightRef.current ||
      isPurchasing ||
      isRestoring
    ) {
      return;
    }
    haptics.selection();

    let result;
    try {
      result = await restorePurchases();
    } catch {
      Alert.alert(
        t('plans.restoreFailed.title'),
        t('plans.restoreFailed.message'),
        [{ text: t('common.close', { defaultValue: 'OK' }), style: 'default' }]
      );
      return;
    }

    if (result.reason === 'identity_changed') {
      return;
    }

    if (result.success) {
      let reconciliation;

      try {
        reconciliation = await reconcileSubscription();
      } catch {
        Alert.alert(
          t('plans.pendingVerification.title'),
          t('plans.pendingVerification.message'),
          [{ text: t('common.close', { defaultValue: 'OK' }), style: 'default' }]
        );
        return;
      }

      const backendConfirmedPro =
        reconciliation?.subscription?.plan === 'pro_student' &&
        reconciliation?.subscription?.is_active === true;

      if (backendConfirmedPro) {
        haptics.success();
        Alert.alert(
          t('plans.restoreSuccess.title'),
          t('plans.restoreSuccess.message'),
          [{ text: t('common.close', { defaultValue: 'OK' }), style: 'default' }]
        );
      } else if (!result.proStudentActive) {
        Alert.alert(
          t('plans.nothingToRestore.title'),
          t('plans.nothingToRestore.message'),
          [{ text: t('common.close', { defaultValue: 'OK' }), style: 'default' }]
        );
      } else {
        Alert.alert(
          t('plans.pendingVerification.title'),
          t('plans.pendingVerification.message'),
          [{ text: t('common.close', { defaultValue: 'OK' }), style: 'default' }]
        );
      }
    } else {
      Alert.alert(
        t('plans.restoreFailed.title'),
        t('plans.restoreFailed.message'),
        [{ text: t('common.close', { defaultValue: 'OK' }), style: 'default' }]
      );
    }
  }, [
    isPurchasing,
    isRestoring,
    reconcileSubscription,
    restorePurchases,
    t,
  ]);

  return (
    <ScreenContainer edges={['top', 'bottom']}>
      <ScreenHeader
        title={t('plans.title')}
        showBack={true}
        navigation={navigation}
      />

      <ScrollView
        style={styles.screen}
        contentContainerStyle={styles.content}
        showsVerticalScrollIndicator={false}
      >
        {/* Intro Header */}
        <View style={styles.headerSection}>
          <Text style={[styles.screenSubtitle, isRTL && styles.textRTL]}>
            {screenSubtitle}
          </Text>
        </View>

        {/* Employer Preview Notice */}
        {isEmployer ? (
          <GlassSurface variant="subtle" style={styles.employerNoticeCard}>
            <View style={styles.noticeHeaderRow}>
              <Ionicons
                name="briefcase-outline"
                size={18}
                color={colors.accentStrong || colors.tealDark}
                style={isRTL ? styles.iconRTL : styles.iconLTR}
              />
              <Text style={[styles.employerNoticeTitle, isRTL && styles.textRTL]}>
                {t('plans.previewTag')}
              </Text>
            </View>
            <Text style={[styles.employerNoticeText, isRTL && styles.textRTL]}>
              {t('plans.employer.previewNotice')}
            </Text>
          </GlassSurface>
        ) : null}

        {!isEmployer && aiUsage?.features?.length > 0 ? (
          <GlassSurface
            variant="subtle"
            style={styles.aiUsageCard}
          >
            <View style={styles.aiUsageHeaderRow}>
              <Ionicons
                name="sparkles-outline"
                size={18}
                color={colors.primaryBlue}
                style={
                  isRTL
                    ? styles.iconRTL
                    : styles.iconLTR
                }
              />

              <Text
                style={[
                  styles.aiUsageTitle,
                  isRTL && styles.textRTL,
                ]}
              >
                {t('plans.aiUsage.title')}
              </Text>
            </View>

            <Text
              style={[
                styles.aiUsageSubtitle,
                isRTL && styles.textRTL,
              ]}
            >
              {t('plans.aiUsage.subtitle')}
            </Text>

            <View style={styles.aiUsageRows}>
              {AI_USAGE_FEATURES.map(
                ({ featureKey, labelKey }) => {
                  const feature =
                    aiUsage.features.find(
                      (item) =>
                        item.feature_key ===
                        featureKey
                    );

                  if (!feature) {
                    return null;
                  }

                  return (
                    <View
                      key={featureKey}
                      style={styles.aiUsageRow}
                    >
                      <Text
                        style={[
                          styles.aiUsageLabel,
                          isRTL && styles.textRTL,
                        ]}
                      >
                        {t(labelKey)}
                      </Text>

                      <Text
                        style={styles.aiUsageCount}
                      >
                        {t(
                          'plans.aiUsage.remainingCount',
                          {
                            remaining:
                              feature.remaining,
                            limit:
                              feature.limit,
                          }
                        )}
                      </Text>
                    </View>
                  );
                }
              )}
            </View>
          </GlassSurface>
        ) : null}

        {/* Plan Cards */}
        <View style={styles.cardsContainer}>
          {availablePlans.map((plan) => {
            const isHighlighted = plan.isHighlighted || plan.isPaid;
            const planTitle = t(plan.titleKey);

            let pricingLabel = t(plan.pricingKey);
            if (isEmployer && plan.id === 'employer') {
              pricingLabel = t('plans.employer.standard.pricingLabel', {
                defaultValue: t(plan.pricingKey),
              });
            } else if (!isEmployer && plan.id === 'pro_student' && dynamicPriceString) {
              pricingLabel = t('plans.candidate.pro.pricingDynamic', {
                price: dynamicPriceString,
                defaultValue: `${dynamicPriceString} ${t('plans.perMonth')}`,
              });
            }

            const description = t(plan.descriptionKey);

            const showUpgradeBadge = isEmployer
              ? !plan.isCurrent
              : !plan.isCurrent && plan.id === 'pro_student';

            return (
              <GlassSurface
                key={plan.id}
                variant="card"
                style={[
                  styles.planCard,
                  isHighlighted && styles.highlightedCard,
                ]}
              >
                {/* Top Badge / Tag */}
                <View style={styles.cardTopRow}>
                  {plan.isCurrent ? (
                    <View style={styles.currentBadgeContainer}>
                      <PlanBadge plan={plan.id} />
                      <View style={styles.currentIndicatorPill}>
                        <Ionicons
                          name="checkmark-circle"
                          size={13}
                          color={colors.accentStrong || colors.tealDark}
                          style={styles.indicatorIcon}
                        />
                        <Text style={styles.currentIndicatorText}>
                          {t('plans.currentPlan')}
                        </Text>
                      </View>
                    </View>
                  ) : showUpgradeBadge ? (
                    <View style={styles.upgradeBadgePill}>
                      <Ionicons
                        name="sparkles"
                        size={12}
                        color={colors.primaryBlue}
                        style={styles.indicatorIcon}
                      />
                      <Text style={styles.upgradeBadgeText}>
                        {t('plans.upgradeBadge')}
                      </Text>
                    </View>
                  ) : (
                    <View style={styles.currentBadgeContainer}>
                      <PlanBadge plan={plan.id} />
                    </View>
                  )}
                </View>

                {/* Plan Info */}
                <View style={styles.planInfoBlock}>
                  <Text style={[styles.planTitle, isRTL && styles.textRTL]}>
                    {planTitle}
                  </Text>
                  <Text style={[styles.pricingText, isRTL && styles.textRTL]}>
                    {pricingLabel}
                  </Text>
                  <Text style={[styles.planDescription, isRTL && styles.textRTL]}>
                    {description}
                  </Text>
                </View>

                <View style={styles.divider} />

                {/* Features List */}
                <View style={styles.featuresList}>
                  {plan.features.map((featKey, idx) => {
                    const isStandardEmployer = isEmployer && !plan.isPaid;
                    const iconName = isStandardEmployer
                      ? 'time-outline'
                      : plan.isPaid
                      ? 'sparkles'
                      : 'checkmark-circle';
                    const iconColor = isStandardEmployer
                      ? (colors.accentStrong || colors.tealDark)
                      : plan.isPaid
                      ? colors.primaryBlue
                      : (colors.accent || colors.teal);

                    return (
                      <View key={`${plan.id}-feat-${idx}`} style={styles.featureRow}>
                        <Ionicons
                          name={iconName}
                          size={16}
                          color={iconColor}
                          style={isRTL ? styles.featureIconRTL : styles.featureIconLTR}
                        />
                        <Text style={[styles.featureText, isRTL && styles.textRTL]}>
                          {t(featKey)}
                        </Text>
                      </View>
                    );
                  })}
                </View>

                {/* Action CTA */}
                <View style={styles.actionContainer}>
                  {plan.isCurrent ? (
                    <View
                      style={styles.currentPlanBtn}
                      accessibilityRole="text"
                      accessibilityLabel={t('plans.accessibility.currentPlanBadge', {
                        plan: planTitle,
                      })}
                    >
                      <Ionicons
                        name="checkmark"
                        size={16}
                        color={colors.accentStrong || colors.tealDark}
                        style={isRTL ? styles.btnIconRTL : styles.btnIconLTR}
                      />
                      <Text style={styles.currentPlanBtnText}>
                        {t('plans.currentPlan')}
                      </Text>
                    </View>
                  ) : isEmployer ? (
                    <GradientButton
                      title={t('plans.employerUpgradeCta')}
                      onPress={() => handleEmployerUpgrade(planTitle)}
                      color={colors.primaryBlue}
                      accessibilityLabel={t('plans.accessibility.upgradeButton', {
                        plan: planTitle,
                      })}
                      style={styles.ctaButton}
                    />
                  ) : plan.id === 'pro_student' ? (
                    <GradientButton
                      title={
                        isPurchaseFlowBusy
                          ? t('plans.purchasing')
                          : t('plans.upgradeCta')
                      }
                      onPress={handleCandidateUpgrade}
                      color={colors.primaryBlue}
                      disabled={isPurchaseFlowBusy || isRestoring || !isPurchaseReady}
                      loading={isPurchaseFlowBusy}
                      accessibilityLabel={t('plans.accessibility.upgradeButton', {
                        plan: planTitle,
                      })}
                      style={styles.ctaButton}
                    />
                  ) : null}
                </View>
              </GlassSurface>
            );
          })}
        </View>

        {/* Restore Purchases CTA (Candidate Only - supported platform stores only) */}
        {!isEmployer && runtimeState?.restorePurchasesSupported === true ? (
          <View style={styles.restoreContainer}>
            <GradientButton
              title={isRestoring ? t('plans.restoring') : t('plans.restorePurchases')}
              onPress={handleRestore}
              outline={true}
              color={colors.primaryBlue}
              disabled={isPurchasing || isRestoring}
              accessibilityLabel={t('plans.restorePurchases')}
              style={styles.restoreButton}
            />
          </View>
        ) : null}

        {/* Truthful Footer Disclosure */}
        <GlassSurface variant="subtle" style={styles.footerNoticeCard}>
          <View style={styles.footerNoticeHeader}>
            <Ionicons
              name="information-circle-outline"
              size={18}
              color={colors.textSecondary || '#64748B'}
              style={isRTL ? styles.iconRTL : styles.iconLTR}
            />
            <Text style={[styles.footerNoticeTitle, isRTL && styles.textRTL]}>
              {isEmployer
                ? t('plans.footerNoticeTitle')
                : t('plans.candidateDisclosure.title')}
            </Text>
          </View>
          <Text style={[styles.footerNoticeBody, isRTL && styles.textRTL]}>
            {isEmployer
              ? t('plans.footerNoticeMessage')
              : t('plans.candidateDisclosure.message')}
          </Text>
        </GlassSurface>
      </ScrollView>
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: colors.background || '#F8FAFC',
  },
  content: {
    paddingHorizontal: spacing.screenHorizontalPadding,
    paddingTop: spacing.sm,
    paddingBottom: spacing.xxl,
  },
  headerSection: {
    marginBottom: spacing.md,
  },
  screenSubtitle: {
    ...typography.bodySecondary,
    color: colors.textSecondary || '#64748B',
    fontSize: 14,
    lineHeight: 20,
  },
  aiUsageCard: {
    padding: spacing.md,
    borderRadius: spacing.radii.lg,
    marginBottom: spacing.lg,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor:
      colors.borderSubtle || '#E2E8F0',
  },
  aiUsageHeaderRow: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  aiUsageTitle: {
    ...typography.bodyMedium,
    flex: 1,
    fontSize: 15,
    color:
      colors.textPrimary || colors.textDark,
  },
  aiUsageSubtitle: {
    ...typography.caption,
    marginTop: spacing.xs,
    color:
      colors.textSecondary || colors.textMuted,
    lineHeight: 17,
  },
  aiUsageRows: {
    marginTop: spacing.md,
    gap: spacing.sm,
  },
  aiUsageRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing.md,
  },
  aiUsageLabel: {
    ...typography.body,
    flex: 1,
    fontSize: 13,
    color:
      colors.textPrimary || colors.textDark,
  },
  aiUsageCount: {
    ...typography.caption,
    fontWeight: '700',
    color:
      colors.accentStrong || colors.tealDark,
    writingDirection: 'ltr',
  },
  employerNoticeCard: {
    padding: spacing.md,
    borderRadius: spacing.radii.card,
    marginBottom: spacing.lg,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: 'rgba(14, 116, 144, 0.20)',
    backgroundColor: 'rgba(230, 244, 246, 0.70)',
  },
  noticeHeaderRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: spacing.xs,
  },
  employerNoticeTitle: {
    ...typography.badge,
    color: colors.accentStrong || colors.tealDark,
    fontWeight: '700',
    fontSize: 12,
    letterSpacing: 0.5,
  },
  employerNoticeText: {
    ...typography.caption,
    color: colors.textPrimary || '#1E293B',
    fontSize: 13,
    lineHeight: 18,
  },
  cardsContainer: {
    gap: spacing.lg,
  },
  planCard: {
    padding: spacing.lg,
    borderRadius: spacing.radii.card,
    backgroundColor: colors.surface || '#FFFFFF',
    borderWidth: 1,
    borderColor: colors.borderSubtle || '#E2E8F0',
  },
  highlightedCard: {
    borderColor: colors.primaryBlue,
    borderWidth: 1.5,
    shadowColor: colors.primaryBlue,
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.08,
    shadowRadius: 12,
    elevation: 3,
  },
  cardTopRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: spacing.sm,
  },
  currentBadgeContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
  },
  currentIndicatorPill: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.accentSoft || '#E6F4F6',
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xxs,
    borderRadius: spacing.radii.pill,
  },
  currentIndicatorText: {
    ...typography.badge,
    fontSize: 11,
    fontWeight: '600',
    color: colors.accentStrong || colors.tealDark,
  },
  upgradeBadgePill: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(37, 99, 235, 0.08)',
    paddingHorizontal: spacing.sm + 2,
    paddingVertical: spacing.xxs + 1,
    borderRadius: spacing.radii.pill,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: 'rgba(37, 99, 235, 0.25)',
  },
  upgradeBadgeText: {
    ...typography.badge,
    fontSize: 11,
    fontWeight: '700',
    color: colors.primaryBlue,
    letterSpacing: 0.5,
  },
  indicatorIcon: {
    marginEnd: 4,
  },
  planInfoBlock: {
    marginTop: spacing.xs,
    marginBottom: spacing.sm,
  },
  planTitle: {
    ...typography.h2,
    fontSize: 20,
    fontWeight: '700',
    color: colors.textPrimary || '#0F172A',
    marginBottom: spacing.xxs,
  },
  pricingText: {
    ...typography.caption,
    fontSize: 13,
    fontWeight: '600',
    color: colors.primaryBlue,
    marginBottom: spacing.xs,
  },
  planDescription: {
    ...typography.bodySecondary,
    fontSize: 13,
    lineHeight: 18,
    color: colors.textSecondary || '#64748B',
  },
  divider: {
    height: StyleSheet.hairlineWidth,
    backgroundColor: colors.borderSubtle || '#E2E8F0',
    marginVertical: spacing.md,
  },
  featuresList: {
    gap: spacing.sm,
    marginBottom: spacing.lg,
  },
  featureRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
  },
  featureIconLTR: {
    marginEnd: spacing.sm,
    marginTop: 2,
  },
  featureIconRTL: {
    marginStart: spacing.sm,
    marginTop: 2,
  },
  featureText: {
    ...typography.body,
    flex: 1,
    fontSize: 13,
    lineHeight: 18,
    color: colors.textPrimary || '#1E293B',
  },
  actionContainer: {
    marginTop: spacing.xs,
  },
  currentPlanBtn: {
    height: 44,
    borderRadius: spacing.radii.button,
    backgroundColor: colors.accentSoft || '#E6F4F6',
    borderWidth: 1,
    borderColor: 'rgba(14, 116, 144, 0.20)',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: spacing.md,
  },
  currentPlanBtnText: {
    ...typography.button,
    fontSize: 14,
    fontWeight: '600',
    color: colors.accentStrong || colors.tealDark,
  },
  btnIconLTR: {
    marginEnd: spacing.xs,
  },
  btnIconRTL: {
    marginStart: spacing.xs,
  },
  ctaButton: {
    height: 44,
  },
  restoreContainer: {
    marginTop: spacing.md,
    alignItems: 'center',
  },
  restoreButton: {
    height: 44,
  },
  footerNoticeCard: {
    marginTop: spacing.xl,
    padding: spacing.md,
    borderRadius: spacing.radii.card,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.borderSubtle || '#E2E8F0',
    backgroundColor: 'rgba(241, 245, 249, 0.70)',
  },
  footerNoticeHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: spacing.xs,
  },
  footerNoticeTitle: {
    ...typography.label,
    fontSize: 12,
    fontWeight: '700',
    color: colors.textSecondary || '#64748B',
    letterSpacing: 0.3,
  },
  footerNoticeBody: {
    ...typography.caption,
    fontSize: 12,
    lineHeight: 17,
    color: colors.textSecondary || '#64748B',
  },
  iconLTR: {
    marginEnd: spacing.xs,
  },
  iconRTL: {
    marginStart: spacing.xs,
  },
  textRTL: {
    textAlign: 'right',
  },
});
