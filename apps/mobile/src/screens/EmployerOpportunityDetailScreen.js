import React, {
  useCallback,
  useState,
} from 'react';
import {
  ActivityIndicator,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import {
  useFocusEffect,
} from '@react-navigation/native';
import { useTranslation } from 'react-i18next';

import ScreenContainer from '../components/ScreenContainer';
import ScreenHeader from '../components/ScreenHeader';
import Card from '../components/Card';
import Chip from '../components/Chip';
import colors from '../theme/colors';
import { spacing } from '../theme/spacing';
import { typography } from '../theme/typography';
import {
  useLocalization,
} from '../localization/LocalizationContext';
import {
  getEmployerInternshipDetail,
} from '../services/api';


function statusText(t, status) {
  switch (status) {
    case 'published':
      return t(
        'employerOpportunities.statusPublished',
        'Published'
      );

    case 'under_review':
      return t(
        'employerOpportunities.statusPending',
        'Under review'
      );

    case 'closed':
      return t(
        'employerOpportunities.statusClosed',
        'Closed'
      );

    default:
      return t(
        'employerOpportunities.statusDraft',
        'Changes required'
      );
  }
}


function DetailField({
  label,
  value,
  isRTL,
}) {
  if (
    value === null
    || value === undefined
    || String(value).trim() === ''
  ) {
    return null;
  }

  return (
    <View style={styles.field}>
      <Text
        style={[
          styles.label,
          isRTL && styles.rtlText,
        ]}
      >
        {label}
      </Text>

      <Text
        selectable
        style={[
          styles.value,
          isRTL && styles.rtlText,
        ]}
      >
        {String(value)}
      </Text>
    </View>
  );
}


export default function EmployerOpportunityDetailScreen({
  navigation,
  route,
}) {
  const { t } = useTranslation();
  const { isRTL } = useLocalization();

  const internshipId =
    route?.params?.internshipId || null;

  const [detail, setDetail] =
    useState(null);

  const [loading, setLoading] =
    useState(true);

  const [error, setError] =
    useState(false);


  const loadDetail =
    useCallback(async () => {
      if (!internshipId) {
        setError(true);
        setLoading(false);
        return;
      }

      setLoading(true);
      setError(false);

      try {
        const result =
          await getEmployerInternshipDetail(
            internshipId
          );

        setDetail(result);
      } catch (loadError) {
        console.warn(
          'Failed to load employer opportunity detail:',
          loadError
        );

        setError(true);
      } finally {
        setLoading(false);
      }
    }, [internshipId]);


  useFocusEffect(
    useCallback(() => {
      void loadDetail();

      return undefined;
    }, [loadDetail])
  );


  return (
    <ScreenContainer
      edges={['top', 'bottom']}
    >
      <ScreenHeader
        title={t(
          'employerOpportunities.detailsTitle',
          'Opportunity Details'
        )}
        showBack
        navigation={navigation}
        alignment="center"
        bordered
      />

      {loading ? (
        <View style={styles.center}>
          <ActivityIndicator
            size="large"
            color={
              colors.accent
              || colors.teal
            }
          />
        </View>
      ) : error || !detail ? (
        <View style={styles.center}>
          <Text
            style={[
              styles.errorText,
              isRTL && styles.rtlText,
            ]}
          >
            {t(
              'employerOpportunities.detailsLoadError',
              'Could not load this opportunity. Please try again.'
            )}
          </Text>

          <TouchableOpacity
            onPress={loadDetail}
            style={styles.retryButton}
            accessibilityRole="button"
          >
            <Text
              style={styles.retryText}
            >
              {t(
                'employerOpportunities.retry',
                'Retry'
              )}
            </Text>
          </TouchableOpacity>
        </View>
      ) : (
        <ScrollView
          style={styles.screen}
          contentContainerStyle={
            styles.content
          }
          showsVerticalScrollIndicator={
            false
          }
        >
          <Card
            padding="lg"
            style={styles.heroCard}
          >
            <Text
              selectable
              style={[
                styles.title,
                isRTL && styles.rtlText,
              ]}
            >
              {detail.title}
            </Text>

            <View
              style={[
                styles.statusPill,
                isRTL && styles.rowRTL,
              ]}
            >
              <View
                style={styles.statusDot}
              />
              <Text
                style={styles.statusText}
              >
                {statusText(
                  t,
                  detail.publication_status
                )}
              </Text>
            </View>

            <DetailField
              label={t(
                'createOpportunity.company'
              )}
              value={detail.company}
              isRTL={isRTL}
            />

            <DetailField
              label={t(
                'createOpportunity.location'
              )}
              value={detail.location}
              isRTL={isRTL}
            />

            <DetailField
              label={t(
                'createOpportunity.workType'
              )}
              value={detail.work_type}
              isRTL={isRTL}
            />

            <DetailField
              label={t(
                'createOpportunity.description'
              )}
              value={detail.description}
              isRTL={isRTL}
            />
          </Card>

          {detail.publication_status === 'draft' ? (
            <Card
              padding="lg"
              style={styles.feedbackCard}
            >
              <Text
                style={[
                  styles.feedbackTitle,
                  isRTL && styles.rtlText,
                ]}
              >
                {t(
                  'employerOpportunities.changesRequestedTitle'
                )}
              </Text>

              <Text
                style={[
                  styles.feedbackBody,
                  isRTL && styles.rtlText,
                ]}
              >
                {t(
                  'employerOpportunities.changesRequestedBody'
                )}
              </Text>

              {detail.employer_visible_feedback ? (
                <View style={styles.feedbackBox}>
                  <Text
                    style={[
                      styles.feedbackLabel,
                      isRTL && styles.rtlText,
                    ]}
                  >
                    {t(
                      'employerOpportunities.reviewFeedback'
                    )}
                  </Text>

                  <Text
                    selectable
                    style={[
                      styles.feedbackText,
                      isRTL && styles.rtlText,
                    ]}
                  >
                    {detail.employer_visible_feedback}
                  </Text>
                </View>
              ) : null}

              <TouchableOpacity
                style={styles.editResubmitButton}
                onPress={() => {
                  navigation.navigate(
                    'CreateOpportunity',
                    {
                      internshipId: detail.id,
                      opportunity: detail,
                    }
                  );
                }}
                accessibilityRole="button"
                accessibilityLabel={t(
                  'employerOpportunities.editAndResubmit'
                )}
              >
                <Text style={styles.editResubmitText}>
                  {t(
                    'employerOpportunities.editAndResubmit'
                  )}
                </Text>
              </TouchableOpacity>
            </Card>
          ) : null}

          {(detail.required_skills?.length > 0
            || detail.preferred_skills?.length > 0) ? (
            <Card
              padding="lg"
              style={styles.sectionCard}
            >
              {detail.required_skills?.length > 0 ? (
                <>
                  <Text
                    style={[
                      styles.sectionTitle,
                      isRTL && styles.rtlText,
                    ]}
                  >
                    {t(
                      'createOpportunity.requiredSkills'
                    )}
                  </Text>

                  <View
                    style={[
                      styles.chips,
                      isRTL && styles.rowRTL,
                    ]}
                  >
                    {detail.required_skills.map(
                      (skill, index) => (
                        <Chip
                          key={`required-${index}-${skill}`}
                          label={skill}
                          variant="skill"
                        />
                      )
                    )}
                  </View>
                </>
              ) : null}

              {detail.preferred_skills?.length > 0 ? (
                <>
                  <Text
                    style={[
                      styles.sectionTitle,
                      isRTL && styles.rtlText,
                    ]}
                  >
                    {t(
                      'createOpportunity.preferredSkills'
                    )}
                  </Text>

                  <View
                    style={[
                      styles.chips,
                      isRTL && styles.rowRTL,
                    ]}
                  >
                    {detail.preferred_skills.map(
                      (skill, index) => (
                        <Chip
                          key={`preferred-${index}-${skill}`}
                          label={skill}
                          variant="neutral"
                        />
                      )
                    )}
                  </View>
                </>
              ) : null}
            </Card>
          ) : null}

          <Card
            padding="lg"
            style={styles.sectionCard}
          >
            <DetailField
              label={t(
                'createOpportunity.language'
              )}
              value={
                detail.languages?.join(', ')
              }
              isRTL={isRTL}
            />

            <DetailField
              label={t(
                'createOpportunity.educationRequirements'
              )}
              value={detail.min_education}
              isRTL={isRTL}
            />

            <DetailField
              label={t(
                'createOpportunity.experienceRequirements'
              )}
              value={
                detail.experience_requirements
              }
              isRTL={isRTL}
            />
          </Card>
        </ScrollView>
      )}
    </ScreenContainer>
  );
}


const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor:
      colors.background
      || colors.screenBg,
  },

  content: {
    padding:
      spacing.screenHorizontalPadding,
    paddingBottom: spacing.xxl,
  },

  center: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: spacing.xl,
  },

  heroCard: {
    marginBottom: spacing.md,
  },

  sectionCard: {
    marginBottom: spacing.md,
  },

  title: {
    ...typography.cardTitle,
    fontSize: 20,
    lineHeight: 27,
    color:
      colors.textPrimary
      || colors.textDark,
  },

  statusPill: {
    alignSelf: 'flex-start',
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: spacing.sm,
    marginBottom: spacing.md,
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xxs,
    borderRadius: spacing.radii.pill,
    backgroundColor:
      colors.accentSoft
      || '#E6F4F6',
  },

  statusDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    marginEnd: 5,
    backgroundColor:
      colors.accentStrong
      || colors.tealDark,
  },

  statusText: {
    ...typography.badge,
    color:
      colors.accentStrong
      || colors.tealDark,
  },

  field: {
    marginTop: spacing.md,
    minWidth: 0,
  },

  label: {
    ...typography.caption,
    fontWeight: '700',
    color:
      colors.textSecondary
      || colors.textMuted,
    marginBottom: spacing.xxs,
  },

  value: {
    ...typography.body,
    color:
      colors.textPrimary
      || colors.textDark,
    lineHeight: 22,
    flexShrink: 1,
  },

  sectionTitle: {
    ...typography.bodyMedium,
    color:
      colors.textPrimary
      || colors.textDark,
    marginBottom: spacing.sm,
  },

  chips: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    minWidth: 0,
  },

  feedbackCard: {
    marginBottom: spacing.md,
  },

  feedbackTitle: {
    ...typography.bodyMedium,
    color: colors.textPrimary || colors.textDark,
    marginBottom: spacing.xs,
  },

  feedbackBody: {
    ...typography.body,
    color: colors.textSecondary || colors.textMuted,
    lineHeight: 22,
  },

  feedbackBox: {
    marginTop: spacing.md,
    padding: spacing.md,
    borderRadius: spacing.radii.md,
    backgroundColor: colors.surface || '#FFFFFF',
  },

  feedbackLabel: {
    ...typography.caption,
    fontWeight: '700',
    color: colors.textSecondary || colors.textMuted,
    marginBottom: spacing.xxs,
  },

  feedbackText: {
    ...typography.body,
    color: colors.textPrimary || colors.textDark,
    lineHeight: 22,
  },

  editResubmitButton: {
    marginTop: spacing.md,
    minHeight: 48,
    borderRadius: spacing.radii.md,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: spacing.lg,
    backgroundColor:
      colors.accentStrong || colors.tealDark,
  },

  editResubmitText: {
    ...typography.button,
    color: '#FFFFFF',
    textAlign: 'center',
  },

  errorText: {
    ...typography.body,
    color:
      colors.textSecondary
      || colors.textMuted,
    textAlign: 'center',
  },

  retryButton: {
    marginTop: spacing.md,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
  },

  retryText: {
    ...typography.button,
    color:
      colors.accentStrong
      || colors.tealDark,
  },

  rowRTL: {
    flexDirection: 'row-reverse',
  },

  rtlText: {
    textAlign: 'right',
    writingDirection: 'rtl',
  },
});
