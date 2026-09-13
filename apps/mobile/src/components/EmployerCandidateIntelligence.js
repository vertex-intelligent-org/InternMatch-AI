import React, { useRef, useState } from 'react';
import {
  ActivityIndicator,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import {
  ApiError,
  getEmployerCandidateInsight,
  getEmployerInterviewKit,
  getEmployerProductPolicy,
} from '../services/api';
import { useTranslation } from 'react-i18next';
import colors from '../theme/colors';
import { spacing } from '../theme/spacing';
import Card from './Card';


function createRequestKey(prefix, internshipId, applicationId) {
  const randomPart = Math.random()
    .toString(36)
    .slice(2, 10);

  return [
    prefix,
    internshipId,
    applicationId,
    Date.now().toString(36),
    randomPart,
  ].join(':');
}


function BulletList({
  items,
  colors,
  isRTL,
}) {
  if (!Array.isArray(items) || items.length === 0) {
    return null;
  }

  return (
    <View
      style={{
        gap: 8,
        marginTop: 8,
      }}
    >
      {items.map((item, index) => (
        <View
          key={`${index}:${item}`}
          style={{
            alignItems: 'flex-start',
            flexDirection: isRTL
              ? 'row-reverse'
              : 'row',
            gap: 8,
          }}
        >
          <Text
            style={{
              color: colors.accentStrong || colors.tealDark,
              fontWeight: '800',
            }}
          >
            ?
          </Text>

          <Text
            style={{
              color: colors.textSecondary,
              flex: 1,
              lineHeight: 20,
              textAlign: isRTL
                ? 'right'
                : 'left',
            }}
          >
            {item}
          </Text>
        </View>
      ))}
    </View>
  );
}


function Section({
  title,
  items,
  colors,
  isRTL,
}) {
  if (!Array.isArray(items) || items.length === 0) {
    return null;
  }

  return (
    <View
      style={{
        marginTop: 16,
      }}
    >
      <Text
        style={{
          color: colors.textPrimary,
          fontSize: 14,
          fontWeight: '800',
          textAlign: isRTL
            ? 'right'
            : 'left',
        }}
      >
        {title}
      </Text>

      <BulletList
        items={items}
        colors={colors}
        isRTL={isRTL}
      />
    </View>
  );
}


export default function EmployerCandidateIntelligence({
  internshipId,
  applicationId,
  navigation,
  isRTL = false,
}) {
  const { t } = useTranslation();

  const [policy, setPolicy] = useState(null);
  const [insight, setInsight] = useState(null);
  const [interviewKit, setInterviewKit] = useState(null);

  const [insightLoading, setInsightLoading] = useState(false);
  const [kitLoading, setKitLoading] = useState(false);

  const [insightError, setInsightError] = useState(null);
  const [kitError, setKitError] = useState(null);

  const insightKeyRef = useRef(null);
  const kitKeyRef = useRef(null);

  const canUseInterviewKit = (
    policy?.interview_kit_available === true
  );

  const humanDecisionNotice = t(
    'employerProduct.candidate.humanDecision'
  );

  async function ensurePolicy() {
    if (policy !== null) {
      return policy;
    }

    const nextPolicy = await getEmployerProductPolicy();
    setPolicy(nextPolicy);

    return nextPolicy;
  }

  async function handleGenerateInsight() {
    setInsightLoading(true);
    setInsightError(null);

    try {
      await ensurePolicy();

      if (!insightKeyRef.current) {
        insightKeyRef.current = createRequestKey(
          'candidate-insight',
          internshipId,
          applicationId
        );
      }

      const result = await getEmployerCandidateInsight(
        internshipId,
        applicationId,
        insightKeyRef.current
      );

      setInsight(result);

      // A completed request should not be reused for a later
      // intentional refresh.
      insightKeyRef.current = null;
    } catch (error) {
      if (error instanceof ApiError) {
        if (error.status === 429) {
          setInsightError(
            'Your available AI candidate insights have been used for the current period.'
          );
        } else if (error.status === 409) {
          setInsightError(
            'Candidate insight is not available until the canonical match is ready.'
          );
        } else if (error.status === 503) {
          setInsightError(
            'Candidate intelligence is temporarily unavailable.'
          );
        } else {
          setInsightError(error.message);
        }
      } else {
        setInsightError(
          'Candidate intelligence is temporarily unavailable.'
        );
      }
    } finally {
      setInsightLoading(false);
    }
  }

  async function handleGenerateInterviewKit() {
    setKitLoading(true);
    setKitError(null);

    try {
      const nextPolicy = await ensurePolicy();

      if (!nextPolicy.interview_kit_available) {
        setKitError(
          'Interview Kit is available with Employer Pro.'
        );
        return;
      }

      if (!kitKeyRef.current) {
        kitKeyRef.current = createRequestKey(
          'interview-kit',
          internshipId,
          applicationId
        );
      }

      const result = await getEmployerInterviewKit(
        internshipId,
        applicationId,
        kitKeyRef.current
      );

      setInterviewKit(result);
      kitKeyRef.current = null;
    } catch (error) {
      if (error instanceof ApiError) {
        if (error.status === 403) {
          setKitError(
            'Interview Kit is available with Employer Pro.'
          );
        } else if (error.status === 429) {
          setKitError(
            'Your available Interview Kits have been used for the current period.'
          );
        } else if (error.status === 409) {
          setKitError(
            'Interview Kit is not available until the canonical match is ready.'
          );
        } else if (error.status === 503) {
          setKitError(
            'Interview Kit is temporarily unavailable.'
          );
        } else {
          setKitError(error.message);
        }
      } else {
        setKitError(
          'Interview Kit is temporarily unavailable.'
        );
      }
    } finally {
      setKitLoading(false);
    }
  }

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
            flexDirection: isRTL
              ? 'row-reverse'
              : 'row',
            gap: spacing.sm,
          }}
        >
          <Ionicons
            name="sparkles-outline"
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
                fontSize: 17,
                fontWeight: '800',
                textAlign: isRTL
                  ? 'right'
                  : 'left',
              }}
            >
              {t('employerProduct.candidate.title')}
            </Text>

            <Text
              style={{
                color: colors.textSecondary,
                fontSize: 13,
                marginTop: 2,
                textAlign: isRTL
                  ? 'right'
                  : 'left',
              }}
            >
              {t('employerProduct.candidate.subtitle')}
            </Text>
          </View>
        </View>

        {insight === null ? (
          <TouchableOpacity
            onPress={handleGenerateInsight}
            disabled={insightLoading}
            accessibilityRole="button"
            style={{
              alignItems: 'center',
              borderRadius: 12,
              flexDirection: isRTL
                ? 'row-reverse'
                : 'row',
              gap: 8,
              justifyContent: 'center',
              marginTop: spacing.md,
              minHeight: 44,
              paddingHorizontal: spacing.md,
            }}
          >
            {insightLoading ? (
              <ActivityIndicator
                size="small"
                color={colors.accent || colors.teal}
              />
            ) : (
              <Ionicons
                name="sparkles"
                size={18}
                color={colors.accent || colors.teal}
              />
            )}

            <Text
              style={{
                color: colors.accentStrong || colors.tealDark,
                fontWeight: '800',
              }}
            >
              {insightLoading
                ? t('employerProduct.candidate.generatingInsight')
                : t('employerProduct.candidate.generateInsight')}
            </Text>
          </TouchableOpacity>
        ) : (
          <View
            style={{
              marginTop: spacing.md,
            }}
          >
            <Text
              style={{
                color: colors.textPrimary,
                fontSize: 15,
                fontWeight: '800',
                textAlign: isRTL
                  ? 'right'
                  : 'left',
              }}
            >
              {t('employerProduct.candidate.summary')}
            </Text>

            <Text
              style={{
                color: colors.textSecondary,
                lineHeight: 21,
                marginTop: 6,
                textAlign: isRTL
                  ? 'right'
                  : 'left',
              }}
            >
              {insight.executive_summary}
            </Text>

            <Section
              title={t('employerProduct.candidate.strengths')}
              items={insight.strengths}
              colors={colors}
              isRTL={isRTL}
            />

            <Section
              title={t('employerProduct.candidate.gaps')}
              items={insight.gaps_to_validate}
              colors={colors}
              isRTL={isRTL}
            />

            <Section
              title={t('employerProduct.candidate.interviewFocus')}
              items={insight.interview_focus}
              colors={colors}
              isRTL={isRTL}
            />

            <TouchableOpacity
              onPress={handleGenerateInsight}
              disabled={insightLoading}
              accessibilityRole="button"
              style={{
                marginTop: spacing.md,
              }}
            >
              <Text
                style={{
                  color: colors.accentStrong || colors.tealDark,
                  fontWeight: '700',
                  textAlign: isRTL
                    ? 'right'
                    : 'left',
                }}
              >
                {t('employerProduct.candidate.refreshInsight')}
              </Text>
            </TouchableOpacity>
          </View>
        )}

        {insightError ? (
          <Text
            style={{
              color: colors.danger || '#EF4444',
              fontSize: 13,
              marginTop: spacing.sm,
              textAlign: isRTL
                ? 'right'
                : 'left',
            }}
          >
            {insightError}
          </Text>
        ) : null}

        <Text
          style={{
            color: colors.textSecondary,
            fontSize: 12,
            lineHeight: 18,
            marginTop: spacing.md,
            textAlign: isRTL
              ? 'right'
              : 'left',
          }}
        >
          {humanDecisionNotice}
        </Text>
      </Card>

      <Card padding="md">
        <View
          style={{
            alignItems: 'center',
            flexDirection: isRTL
              ? 'row-reverse'
              : 'row',
            gap: spacing.sm,
          }}
        >
          <Ionicons
            name="chatbubbles-outline"
            size={21}
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
                fontSize: 16,
                fontWeight: '800',
                textAlign: isRTL
                  ? 'right'
                  : 'left',
              }}
            >
              {t('employerProduct.candidate.interviewKitTitle')}
            </Text>

            <Text
              style={{
                color: colors.textSecondary,
                fontSize: 13,
                marginTop: 2,
                textAlign: isRTL
                  ? 'right'
                  : 'left',
              }}
            >
              {t('employerProduct.candidate.interviewKitSubtitle')}
            </Text>
          </View>
        </View>

        {interviewKit ? (
          <View
            style={{
              gap: spacing.sm,
              marginTop: spacing.md,
            }}
          >
            {interviewKit.questions.map(
              (item, index) => (
                <View
                  key={`${item.category}:${index}`}
                  style={{
                    backgroundColor:
                      colors.surfaceSecondary
                      || colors.surface,
                    borderRadius: 12,
                    padding: spacing.sm,
                  }}
                >
                  <Text
                    style={{
                      color: colors.textSecondary,
                      fontSize: 11,
                      fontWeight: '700',
                      textAlign: isRTL
                        ? 'right'
                        : 'left',
                      textTransform: 'uppercase',
                    }}
                  >
                    {item.category.replace(
                      /_/g,
                      ' '
                    )}
                  </Text>

                  <Text
                    style={{
                      color: colors.textPrimary,
                      lineHeight: 20,
                      marginTop: 5,
                      textAlign: isRTL
                        ? 'right'
                        : 'left',
                    }}
                  >
                    {item.question}
                  </Text>
                </View>
              )
            )}
          </View>
        ) : (
          <TouchableOpacity
            onPress={handleGenerateInterviewKit}
            disabled={kitLoading}
            accessibilityRole="button"
            style={{
              alignItems: 'center',
              flexDirection: isRTL
                ? 'row-reverse'
                : 'row',
              gap: 8,
              justifyContent: 'center',
              marginTop: spacing.md,
              minHeight: 44,
            }}
          >
            {kitLoading ? (
              <ActivityIndicator
                size="small"
                color={colors.accent || colors.teal}
              />
            ) : (
              <Ionicons
                name="sparkles"
                size={17}
                color={colors.accent || colors.teal}
              />
            )}

            <Text
              style={{
                color: colors.accentStrong || colors.tealDark,
                fontWeight: '800',
              }}
            >
              {kitLoading
                ? 'Generating Interview Kit...'
                : 'Generate Interview Kit'}
            </Text>
          </TouchableOpacity>
        )}

        {kitError ? (
          <>
            <Text
              style={{
                color: colors.textSecondary,
                fontSize: 13,
                marginTop: spacing.sm,
                textAlign: isRTL
                  ? 'right'
                  : 'left',
              }}
            >
              {kitError}
            </Text>

            {kitError.includes('Employer Pro') ? (
              <TouchableOpacity
                onPress={() => navigation.navigate('Plans')}
                accessibilityRole="button"
                style={{
                  marginTop: spacing.sm,
                }}
              >
                <Text
                  style={{
                    color: colors.accentStrong || colors.tealDark,
                    fontWeight: '800',
                    textAlign: isRTL
                      ? 'right'
                      : 'left',
                  }}
                >
                  {t('employerProduct.common.explorePro')}
                </Text>
              </TouchableOpacity>
            ) : null}
          </>
        ) : null}
      </Card>
    </View>
  );
}
