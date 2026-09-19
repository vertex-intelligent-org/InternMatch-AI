import React, {
  useCallback,
  useState,
} from 'react';
import {
  ActivityIndicator,
  Alert,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTranslation } from 'react-i18next';

import GlassSurface from './GlassSurface';
import GradientButton from './GradientButton';
import colors from '../theme/colors';
import { spacing } from '../theme/spacing';
import { typography } from '../theme/typography';
import {
  ApiError,
  getPromoCodeStatus,
  redeemPromoCode,
} from '../services/api';
import haptics from '../services/haptics';


function errorTranslationKey(error) {
  if (!(error instanceof ApiError)) {
    return 'plans.promo.unavailable';
  }

  switch (error.code) {
    case 'PROMO_INVALID':
      return 'plans.promo.invalid';

    case 'PROMO_ALREADY_REDEEMED':
      return 'plans.promo.alreadyUsed';

    case 'PROMO_PRO_ALREADY_ACTIVE':
      return 'plans.promo.activePro';

    case 'PROMO_IN_PROGRESS':
      return 'plans.promo.inProgress';

    default:
      return 'plans.promo.unavailable';
  }
}


export default function PromoCodePanel({
  isEmployer,
  isRTL,
  activePro,
  busy,
  reconcileSubscription,
  onInputFocus,
}) {
  const { t } = useTranslation();

  const [expanded, setExpanded] =
    useState(false);

  const [code, setCode] =
    useState('');

  const [promoStatus, setPromoStatus] =
    useState(null);

  const [statusLoaded, setStatusLoaded] =
    useState(false);

  const [loadingStatus, setLoadingStatus] =
    useState(false);

  const [submitting, setSubmitting] =
    useState(false);

  const usedOnce =
    promoStatus?.used_once === true;

  const loadStatus =
    useCallback(async () => {
      if (
        loadingStatus
        || statusLoaded
      ) {
        return;
      }

      setLoadingStatus(true);

      try {
        const result =
          await getPromoCodeStatus();

        setPromoStatus(result);
        setStatusLoaded(true);
      } catch {
        // Promo availability is optional and
        // must never break the Plans screen.
      } finally {
        setLoadingStatus(false);
      }
    }, [
      loadingStatus,
      statusLoaded,
    ]);

  const toggleExpanded =
    useCallback(() => {
      const next = !expanded;

      setExpanded(next);

      if (next) {
        void loadStatus();
      }
    }, [
      expanded,
      loadStatus,
    ]);

  const submitPromo =
    useCallback(async () => {
      if (
        submitting
        || busy
        || activePro
        || usedOnce
      ) {
        return;
      }

      const normalized =
        code.trim().toUpperCase();

      if (
        normalized.length < 16
        || normalized.length > 64
      ) {
        Alert.alert(
          t(
            'plans.promo.invalidTitle'
          ),
          t(
            'plans.promo.invalid'
          )
        );

        return;
      }

      setSubmitting(true);

      haptics.selection();

      try {
        const result =
          await redeemPromoCode(
            normalized
          );

        // Never retain an accepted private
        // code in component state.
        setCode('');

        setPromoStatus({
          audience:
            result.audience,
          used_once: true,
          status: 'redeemed',
          access_expires_at:
            result.access_expires_at,
        });

        setStatusLoaded(true);

        let syncPending =
          result.sync_pending === true;

        try {
          const reconciliation =
            await reconcileSubscription();

          const expectedPlan =
            isEmployer
              ? 'employer_pro'
              : 'pro_student';

          const confirmed =
            (
              reconciliation
                ?.subscription
                ?.plan
              === expectedPlan
            )
            && (
              reconciliation
                ?.subscription
                ?.is_active
              === true
            );

          if (!confirmed) {
            syncPending = true;
          }
        } catch {
          syncPending = true;
        }

        haptics.success();

        Alert.alert(
          t(
            'plans.promo.successTitle'
          ),
          syncPending
            ? t(
                'plans.promo.syncingMessage'
              )
            : t(
                'plans.promo.successMessage'
              )
        );
      } catch (error) {
        if (
          error instanceof ApiError
          && error.code
            === 'PROMO_ALREADY_REDEEMED'
        ) {
          setPromoStatus({
            audience:
              isEmployer
                ? 'employer'
                : 'student',
            used_once: true,
            status: 'redeemed',
            access_expires_at: null,
          });

          setStatusLoaded(true);
        }

        haptics.selection();

        Alert.alert(
          t(
            'plans.promo.errorTitle'
          ),
          t(
            errorTranslationKey(
              error
            )
          )
        );
      } finally {
        setSubmitting(false);
      }
    }, [
      activePro,
      busy,
      code,
      isEmployer,
      reconcileSubscription,
      submitting,
      t,
      usedOnce,
    ]);

  if (activePro) {
    return null;
  }

  return (
    <GlassSurface
      variant="subtle"
      style={styles.container}
    >
      <TouchableOpacity
        onPress={
          toggleExpanded
        }
        activeOpacity={0.78}
        accessibilityRole="button"
        accessibilityState={{
          expanded,
        }}
        accessibilityLabel={
          t(
            'plans.promo.title'
          )
        }
        style={[
          styles.toggleRow,
          isRTL
            && styles.rowRTL,
        ]}
      >
        <View
          style={[
            styles.titleRow,
            isRTL
              && styles.rowRTL,
          ]}
        >
          <Ionicons
            name="key-outline"
            size={17}
            color={
              colors.accentStrong
              || colors.tealDark
            }
            style={
              isRTL
                ? styles.iconRTL
                : styles.iconLTR
            }
          />

          <Text
            style={[
              styles.title,
              isRTL
                && styles.textRTL,
            ]}
          >
            {t(
              'plans.promo.title'
            )}
          </Text>
        </View>

        {loadingStatus ? (
          <ActivityIndicator
            size="small"
            color={
              colors.primaryBlue
            }
          />
        ) : (
          <Ionicons
            name={
              expanded
                ? 'chevron-up'
                : 'chevron-down'
            }
            size={18}
            color={
              colors.textSecondary
              || colors.textMuted
            }
          />
        )}
      </TouchableOpacity>

      {expanded ? (
        <View
          style={styles.body}
        >
          {usedOnce ? (
            <View
              style={[
                styles.usedRow,
                isRTL
                  && styles.rowRTL,
              ]}
            >
              <Ionicons
                name="checkmark-circle"
                size={18}
                color={
                  colors.accentStrong
                  || colors.tealDark
                }
                style={
                  isRTL
                    ? styles.iconRTL
                    : styles.iconLTR
                }
              />

              <Text
                style={[
                  styles.usedText,
                  isRTL
                    && styles.textRTL,
                ]}
              >
                {t(
                  'plans.promo.usedMessage'
                )}
              </Text>
            </View>
          ) : (
            <>
              <Text
                style={[
                  styles.subtitle,
                  isRTL
                    && styles.textRTL,
                ]}
              >
                {t(
                  'plans.promo.subtitle'
                )}
              </Text>

              <TextInput
                value={code}
                onChangeText={setCode}
                onFocus={onInputFocus}
                placeholder={
                  t(
                    'plans.promo.placeholder'
                  )
                }
                placeholderTextColor={
                  colors.textMuted
                  || '#94A3B8'
                }
                autoCapitalize="characters"
                autoCorrect={false}
                spellCheck={false}
                maxLength={64}
                editable={
                  !submitting
                  && !busy
                }
                accessibilityLabel={
                  t(
                    'plans.promo.inputLabel'
                  )
                }
                style={[
                  styles.input,
                  isRTL
                    && styles.textRTL,
                ]}
              />

              <GradientButton
                title={
                  submitting
                    ? t(
                        'plans.promo.redeeming'
                      )
                    : t(
                        'plans.promo.submit'
                      )
                }
                onPress={submitPromo}
                disabled={
                  submitting
                  || busy
                  || !code.trim()
                }
                loading={
                  submitting
                }
                color={
                  colors.primaryBlue
                }
                style={
                  styles.submitButton
                }
              />

              <Text
                style={[
                  styles.helper,
                  isRTL
                    && styles.textRTL,
                ]}
              >
                {isEmployer
                  ? t(
                      'plans.promo.employerHint'
                    )
                  : t(
                      'plans.promo.studentHint'
                    )}
              </Text>
            </>
          )}
        </View>
      ) : null}
    </GlassSurface>
  );
}


const styles = StyleSheet.create({
  container: {
    marginTop: spacing.lg,
    padding: spacing.md,
    borderRadius:
      spacing.radii.card,
    borderWidth:
      StyleSheet.hairlineWidth,
    borderColor:
      colors.borderSubtle
      || '#E2E8F0',
  },

  toggleRow: {
    minHeight: 44,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent:
      'space-between',
  },

  titleRow: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
  },

  title: {
    ...typography.bodyMedium,
    flex: 1,
    fontSize: 14,
    color:
      colors.textPrimary
      || colors.textDark,
  },

  body: {
    paddingTop: spacing.sm,
  },

  subtitle: {
    ...typography.caption,
    color:
      colors.textSecondary
      || colors.textMuted,
    lineHeight: 18,
    marginBottom: spacing.sm,
  },

  input: {
    minHeight: 46,
    borderWidth: 1,
    borderColor:
      colors.borderSubtle
      || '#CBD5E1',
    borderRadius:
      spacing.radii.button,
    backgroundColor:
      colors.surface
      || '#FFFFFF',
    color:
      colors.textPrimary
      || '#0F172A',
    paddingHorizontal:
      spacing.md,
    fontSize: 14,
    letterSpacing: 0.4,
  },

  submitButton: {
    height: 44,
    marginTop: spacing.sm,
  },

  helper: {
    ...typography.caption,
    marginTop: spacing.sm,
    color:
      colors.textSecondary
      || colors.textMuted,
    lineHeight: 17,
  },

  usedRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical:
      spacing.xs,
  },

  usedText: {
    ...typography.body,
    flex: 1,
    color:
      colors.accentStrong
      || colors.tealDark,
    fontWeight: '600',
  },

  rowRTL: {
    flexDirection: 'row-reverse',
  },

  iconLTR: {
    marginEnd: spacing.sm,
  },

  iconRTL: {
    marginStart: spacing.sm,
  },

  textRTL: {
    textAlign: 'right',
    writingDirection: 'rtl',
  },
});
