import React, { useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import {
  ApiError,
  compareEmployerShortlist,
  getEmployerProductPolicy,
} from '../services/api';
import Card from './Card';
import { useTranslation } from 'react-i18next';
import colors from '../theme/colors';
import { spacing } from '../theme/spacing';


function createRequestKey(internshipId, applicationIds) {
  return [
    'shortlist-comparison',
    internshipId,
    applicationIds.join('-'),
    Date.now().toString(36),
    Math.random().toString(36).slice(2, 10),
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
    <View style={{ gap: 5, marginTop: 6 }}>
      {items.map((item, index) => (
        <View
          key={`${index}:${item}`}
          style={{
            flexDirection: isRTL
              ? 'row-reverse'
              : 'row',
            gap: 7,
          }}
        >
          <Text
            style={{
              color: colors.accentStrong || colors.tealDark,
            }}
          >
            ?
          </Text>

          <Text
            style={{
              color: colors.textSecondary,
              flex: 1,
              fontSize: 13,
              lineHeight: 19,
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


export default function EmployerShortlistComparison({
  internshipId,
  applicants,
  navigation,
  isRTL = false,
}) {
  const { t } = useTranslation();

  const [selectedIds, setSelectedIds] = useState([]);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const keyRef = useRef(null);

  const candidatesById = useMemo(() => {
    const mapping = {};

    for (const item of applicants || []) {
      mapping[item.application_id] = item;
    }

    return mapping;
  }, [applicants]);

  function toggleApplicant(applicationId) {
    setResult(null);
    setError(null);

    setSelectedIds((current) => {
      if (current.includes(applicationId)) {
        return current.filter(
          (value) => value !== applicationId
        );
      }

      if (current.length >= 5) {
        return current;
      }

      return [
        ...current,
        applicationId,
      ];
    });
  }

  async function handleCompare() {
    if (
      selectedIds.length < 2
      || selectedIds.length > 5
    ) {
      setError(
        t('employerProduct.shortlist.selectRange')
      );
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const policy = await getEmployerProductPolicy();

      if (!policy.shortlist_comparison_available) {
        setError(
          t('employerProduct.shortlist.proOnly')
        );
        return;
      }

      if (!keyRef.current) {
        keyRef.current = createRequestKey(
          internshipId,
          selectedIds
        );
      }

      const nextResult = await compareEmployerShortlist(
        internshipId,
        selectedIds,
        keyRef.current
      );

      if (
        nextResult.ranked !== false
        || nextResult.recommendation_provided !== false
        || nextResult.human_decision_required !== true
      ) {
        throw new Error(
          t('employerProduct.shortlist.unexpectedContract')
        );
      }

      setResult(nextResult);
      keyRef.current = null;
    } catch (compareError) {
      if (compareError instanceof ApiError) {
        if (compareError.status === 403) {
          setError(
            t('employerProduct.shortlist.proOnly')
          );
        } else if (compareError.status === 409) {
          setError(
            t('employerProduct.shortlist.matchRequired')
          );
        } else if (compareError.status === 429) {
          setError(
            t('employerProduct.shortlist.quotaUsed')
          );
        } else if (compareError.status === 503) {
          setError(
            t('employerProduct.shortlist.unavailable')
          );
        } else {
          setError(compareError.message);
        }
      } else {
        setError(
          compareError instanceof Error
            ? compareError.message
            : t('employerProduct.shortlist.unavailable')
        );
      }
    } finally {
      setLoading(false);
    }
  }

  if (!Array.isArray(applicants) || applicants.length < 2) {
    return null;
  }

  return (
    <Card padding="md">
      <View
        style={{
          flexDirection: isRTL
            ? 'row-reverse'
            : 'row',
          gap: spacing.sm,
        }}
      >
        <Ionicons
          name="git-compare-outline"
          size={22}
          color={colors.accent || colors.teal}
        />

        <View style={{ flex: 1 }}>
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
            {t('employerProduct.shortlist.title')}
          </Text>

          <Text
            style={{
              color: colors.textSecondary,
              fontSize: 13,
              lineHeight: 19,
              marginTop: 3,
              textAlign: isRTL
                ? 'right'
                : 'left',
            }}
          >
            {t('employerProduct.shortlist.subtitle')}
          </Text>
        </View>
      </View>

      <View
        style={{
          gap: 7,
          marginTop: spacing.md,
        }}
      >
        {(applicants || []).map((item) => {
          const id = item.application_id;
          const selected = selectedIds.includes(id);

          return (
            <TouchableOpacity
              key={id}
              onPress={() => toggleApplicant(id)}
              accessibilityRole="checkbox"
              accessibilityState={{ checked: selected }}
              style={{
                alignItems: 'center',
                borderColor: selected
                  ? (colors.accent || colors.teal)
                  : (colors.border || '#E5E7EB'),
                borderRadius: 12,
                borderWidth: 1,
                flexDirection: isRTL
                  ? 'row-reverse'
                  : 'row',
                gap: 10,
                padding: 11,
              }}
            >
              <Ionicons
                name={
                  selected
                    ? 'checkbox'
                    : 'square-outline'
                }
                size={21}
                color={
                  selected
                    ? (colors.accent || colors.teal)
                    : colors.textSecondary
                }
              />

              <View style={{ flex: 1 }}>
                <Text
                  style={{
                    color: colors.textPrimary,
                    fontWeight: '700',
                    textAlign: isRTL
                      ? 'right'
                      : 'left',
                  }}
                  numberOfLines={1}
                >
                  {item.candidate?.full_name || t('employerProduct.common.candidate')}
                </Text>

                {typeof item.match_score === 'number' ? (
                  <Text
                    style={{
                      color: colors.textSecondary,
                      fontSize: 12,
                      marginTop: 2,
                      textAlign: isRTL
                        ? 'right'
                        : 'left',
                    }}
                  >
                    {t('employerProduct.shortlist.matchScore')}: {item.match_score}
                  </Text>
                ) : null}
              </View>
            </TouchableOpacity>
          );
        })}
      </View>

      <Text
        style={{
          color: colors.textSecondary,
          fontSize: 12,
          marginTop: spacing.sm,
          textAlign: isRTL
            ? 'right'
            : 'left',
        }}
      >
        {selectedIds.length} / 5 {t('employerProduct.shortlist.selected')}
      </Text>

      <TouchableOpacity
        onPress={handleCompare}
        disabled={
          loading
          || selectedIds.length < 2
          || selectedIds.length > 5
        }
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
          opacity:
            selectedIds.length < 2
              ? 0.45
              : 1,
        }}
      >
        {loading ? (
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
          {loading
            ? t('employerProduct.shortlist.comparing')
            : t('employerProduct.shortlist.compareSelected')}
        </Text>
      </TouchableOpacity>

      {error ? (
        <>
          <Text
            style={{
              color: colors.textSecondary,
              fontSize: 13,
              lineHeight: 19,
              marginTop: spacing.sm,
              textAlign: isRTL
                ? 'right'
                : 'left',
            }}
          >
            {error}
          </Text>

          {error.includes('Employer Pro') ? (
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

      {result ? (
        <View
          style={{
            marginTop: spacing.lg,
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
            {t('employerProduct.shortlist.summary')}
          </Text>

          <Text
            style={{
              color: colors.textSecondary,
              lineHeight: 20,
              marginTop: 6,
              textAlign: isRTL
                ? 'right'
                : 'left',
            }}
          >
            {result.comparison_summary}
          </Text>

          <BulletList
            items={result.shared_role_requirements}
            colors={colors}
            isRTL={isRTL}
          />

          <View
            style={{
              gap: spacing.md,
              marginTop: spacing.md,
            }}
          >
            {result.candidates.map(
              (candidate) => {
                const source =
                  candidatesById[
                    candidate.application_id
                  ];

                return (
                  <View
                    key={candidate.application_id}
                    style={{
                      borderColor:
                        colors.border
                        || '#E5E7EB',
                      borderRadius: 12,
                      borderWidth: 1,
                      padding: spacing.md,
                    }}
                  >
                    <Text
                      style={{
                        color: colors.textPrimary,
                        fontWeight: '800',
                        textAlign: isRTL
                          ? 'right'
                          : 'left',
                      }}
                    >
                      {source?.candidate?.full_name || t('employerProduct.common.candidate')}
                    </Text>

                    <Text
                      style={{
                        color: colors.textSecondary,
                        fontSize: 12,
                        marginTop: 3,
                        textAlign: isRTL
                          ? 'right'
                          : 'left',
                      }}
                    >
                      {t('employerProduct.shortlist.canonicalScore')}: {candidate.match_score}
                    </Text>

                    <Text
                      style={{
                        color: colors.textPrimary,
                        fontSize: 13,
                        fontWeight: '700',
                        marginTop: 12,
                        textAlign: isRTL
                          ? 'right'
                          : 'left',
                      }}
                    >
                      {t('employerProduct.shortlist.evidence')}
                    </Text>

                    <BulletList
                      items={candidate.evidence_highlights}
                      colors={colors}
                      isRTL={isRTL}
                    />

                    <Text
                      style={{
                        color: colors.textPrimary,
                        fontSize: 13,
                        fontWeight: '700',
                        marginTop: 12,
                        textAlign: isRTL
                          ? 'right'
                          : 'left',
                      }}
                    >
                      {t('employerProduct.shortlist.gaps')}
                    </Text>

                    <BulletList
                      items={candidate.gaps_to_validate}
                      colors={colors}
                      isRTL={isRTL}
                    />

                    <Text
                      style={{
                        color: colors.textPrimary,
                        fontSize: 13,
                        fontWeight: '700',
                        marginTop: 12,
                        textAlign: isRTL
                          ? 'right'
                          : 'left',
                      }}
                    >
                      {t('employerProduct.shortlist.interviewFocus')}
                    </Text>

                    <BulletList
                      items={candidate.interview_focus}
                      colors={colors}
                      isRTL={isRTL}
                    />
                  </View>
                );
              }
            )}
          </View>

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
            {t('employerProduct.shortlist.disclaimer')}
          </Text>
        </View>
      ) : null}
    </Card>
  );
}
