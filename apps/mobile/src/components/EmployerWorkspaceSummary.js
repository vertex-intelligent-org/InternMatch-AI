import React, { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import {
  ApiError,
  getEmployerPipelineAnalytics,
  getEmployerProductPolicy,
} from '../services/api';
import { useTranslation } from 'react-i18next';
import colors from '../theme/colors';
import { spacing } from '../theme/spacing';
import Card from './Card';


export default function EmployerWorkspaceSummary({
  navigation,
  refreshKey,
  isRTL = false,
}) {
  const { t } = useTranslation();

  const [policy, setPolicy] = useState(null);
  const [analytics, setAnalytics] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const loadWorkspaceSummary = useCallback(async () => {
    setLoading(true);
    setError(false);

    try {
      const nextPolicy = await getEmployerProductPolicy();
      setPolicy(nextPolicy);

      if (nextPolicy.pipeline_analytics_available) {
        const nextAnalytics = await getEmployerPipelineAnalytics();
        setAnalytics(nextAnalytics);
      } else {
        setAnalytics(null);
      }
    } catch (loadError) {
      if (
        loadError instanceof ApiError
        && loadError.status === 403
      ) {
        setAnalytics(null);
      } else {
        setError(true);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadWorkspaceSummary();
  }, [
    loadWorkspaceSummary,
    refreshKey,
  ]);

  if (loading && policy === null) {
    return (
      <Card padding="md">
        <View
          style={{
            alignItems: 'center',
            flexDirection: 'row',
            gap: spacing.sm,
          }}
        >
          <ActivityIndicator
            size="small"
            color={colors.accent || colors.teal}
          />
          <Text
            style={{
              color: colors.textSecondary,
              flex: 1,
              textAlign: isRTL ? 'right' : 'left',
            }}
          >
            {t('employerProduct.workspace.loading')}
          </Text>
        </View>
      </Card>
    );
  }

  if (error || policy === null) {
    return (
      <Card padding="md">
        <Text
          style={{
            color: colors.textSecondary,
            textAlign: isRTL ? 'right' : 'left',
          }}
        >
          {t('employerProduct.workspace.unavailable')}
        </Text>

        <TouchableOpacity
          onPress={loadWorkspaceSummary}
          accessibilityRole="button"
          style={{
            marginTop: spacing.sm,
          }}
        >
          <Text
            style={{
              color: colors.accentStrong || colors.tealDark,
              fontWeight: '700',
              textAlign: isRTL ? 'right' : 'left',
            }}
          >
            {t('employerProduct.workspace.retry')}
          </Text>
        </TouchableOpacity>
      </Card>
    );
  }

  const isPro = (
    policy.plan === 'employer_pro'
    || policy.is_pro === true
  );

  const publishedCount = (
    analytics?.published_listings
    ?? null
  );

  const limit = policy.active_listing_limit;

  const capacityLabel = (
    limit === null
      ? t('employerProduct.workspace.multipleActiveInternships')
      : publishedCount === null
        ? t(
            'employerProduct.workspace.activeInternshipLimit',
            { count: limit }
          )
        : t(
            'employerProduct.workspace.activeInternshipCapacity',
            {
              count: publishedCount,
              limit,
            }
          )
  );

  return (
    <View
      style={{
        gap: spacing.md,
      }}
    >
      <Card padding="md">
        <View
          style={{
            alignItems: 'center',
            flexDirection: isRTL ? 'row-reverse' : 'row',
            justifyContent: 'space-between',
            gap: spacing.sm,
          }}
        >
          <View
            style={{
              flex: 1,
            }}
          >
            <Text
              style={{
                color: colors.textSecondary,
                fontSize: 12,
                fontWeight: '700',
                letterSpacing: 0.7,
                textAlign: isRTL ? 'right' : 'left',
                textTransform: 'uppercase',
              }}
            >
              {t('employerProduct.workspace.currentPlan')}
            </Text>

            <Text
              style={{
                color: colors.textPrimary,
                fontSize: 20,
                fontWeight: '800',
                marginTop: 4,
                textAlign: isRTL ? 'right' : 'left',
              }}
            >
              {isPro ? 'Employer Pro' : 'Employer Free'}
            </Text>

            <Text
              style={{
                color: colors.textSecondary,
                marginTop: 4,
                textAlign: isRTL ? 'right' : 'left',
              }}
            >
              {capacityLabel}
            </Text>
          </View>

          <View
            style={{
              alignItems: 'center',
              backgroundColor: colors.surfaceSecondary || colors.surface,
              borderRadius: 18,
              height: 44,
              justifyContent: 'center',
              width: 44,
            }}
          >
            <Ionicons
              name={isPro ? 'sparkles' : 'briefcase-outline'}
              size={21}
              color={colors.accent || colors.teal}
            />
          </View>
        </View>

        {!isPro && (
          <TouchableOpacity
            onPress={() => navigation.navigate('Plans')}
            accessibilityRole="button"
            style={{
              alignItems: 'center',
              flexDirection: isRTL ? 'row-reverse' : 'row',
              gap: 6,
              marginTop: spacing.md,
            }}
          >
            <Text
              style={{
                color: colors.accentStrong || colors.tealDark,
                fontWeight: '700',
              }}
            >
              {t('employerProduct.common.explorePro')}
            </Text>

            <Ionicons
              name={isRTL ? 'arrow-back' : 'arrow-forward'}
              size={15}
              color={colors.accentStrong || colors.tealDark}
            />
          </TouchableOpacity>
        )}
      </Card>

      {policy.pipeline_analytics_available && analytics ? (
        <Card padding="md">
          <Text
            style={{
              color: colors.textPrimary,
              fontSize: 17,
              fontWeight: '800',
              textAlign: isRTL ? 'right' : 'left',
            }}
          >
            {t('employerProduct.workspace.pipelineTitle')}
          </Text>

          <Text
            style={{
              color: colors.textSecondary,
              fontSize: 13,
              marginTop: 4,
              textAlign: isRTL ? 'right' : 'left',
            }}
          >
            {t('employerProduct.workspace.snapshotTitle')}
          </Text>

          <View
            style={{
              flexDirection: isRTL ? 'row-reverse' : 'row',
              gap: spacing.sm,
              marginTop: spacing.md,
            }}
          >
            {[
              [
                t('employerProduct.workspace.applicants'),
                analytics.total_submitted_applications,
              ],
              [
                t('employerProduct.workspace.interviewing'),
                analytics.interviewing,
              ],
              [
                t('employerProduct.workspace.decisions'),
                analytics.accepted
                  + analytics.rejected,
              ],
            ].map(([label, value]) => (
              <View
                key={label}
                style={{
                  backgroundColor:
                    colors.surfaceSecondary
                    || colors.surface,
                  borderRadius: 14,
                  flex: 1,
                  padding: spacing.sm,
                }}
              >
                <Text
                  style={{
                    color: colors.textPrimary,
                    fontSize: 20,
                    fontWeight: '800',
                    textAlign: 'center',
                  }}
                >
                  {value}
                </Text>

                <Text
                  style={{
                    color: colors.textSecondary,
                    fontSize: 11,
                    marginTop: 3,
                    textAlign: 'center',
                  }}
                >
                  {label}
                </Text>
              </View>
            ))}
          </View>

          <Text
            style={{
              color: colors.textSecondary,
              fontSize: 12,
              marginTop: spacing.md,
              textAlign: isRTL ? 'right' : 'left',
            }}
          >
            {t('employerProduct.workspace.analyticsDisclaimer')}
          </Text>
        </Card>
      ) : (
        <Card padding="md">
          <View
            style={{
              alignItems: 'center',
              flexDirection: isRTL ? 'row-reverse' : 'row',
              gap: spacing.sm,
            }}
          >
            <Ionicons
              name="analytics-outline"
              size={22}
              color={colors.accent || colors.teal}
            />

            <View
              style={{
                flex: 1,
              }}
            >
              <Text
                style={{
                  color: colors.textPrimary,
                  fontWeight: '800',
                  textAlign: isRTL ? 'right' : 'left',
                }}
              >
                {t('employerProduct.workspace.pipelineInsights')}
              </Text>

              <Text
                style={{
                  color: colors.textSecondary,
                  fontSize: 13,
                  marginTop: 2,
                  textAlign: isRTL ? 'right' : 'left',
                }}
              >
                {t('employerProduct.workspace.proOnly')}
              </Text>
            </View>
          </View>
        </Card>
      )}
    </View>
  );
}
