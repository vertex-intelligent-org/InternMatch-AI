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
import ScreenContainer from '../components/ScreenContainer';
import ScreenHeader from '../components/ScreenHeader';
import Card from '../components/Card';
import Chip from '../components/Chip';
import BookmarkButton from '../components/BookmarkButton';
import { getInternshipDetail, ApiError } from '../services/api';
import { useSavedInternships } from '../context/SavedInternshipsContext';
import { useLocalization } from '../localization/LocalizationContext';
import { formatLocalizedDate } from '../localization/formatters';

export default function InternshipDetailScreen({ route, navigation }) {
  const { t } = useTranslation();
  const { locale, isRTL } = useLocalization();
  const internshipId =
    route?.params?.internshipId ||
    route?.params?.internship?.id ||
    route?.params?.id;

  const [internship, setInternship] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [isNotFound, setIsNotFound] = useState(false);
  const requestGenerationRef = useRef(0);

  const fetchDetail = useCallback(async () => {
    const generation = ++requestGenerationRef.current;

    if (!internshipId) {
      if (generation !== requestGenerationRef.current) return;
      setIsNotFound(true);
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);
    setIsNotFound(false);

    try {
      const data = await getInternshipDetail(internshipId, locale);
      if (generation !== requestGenerationRef.current) return;
      setInternship(data);
    } catch (err) {
      if (generation !== requestGenerationRef.current) return;
      if (err instanceof ApiError && err.status === 404) {
        setIsNotFound(true);
      } else {
        console.warn('Failed to fetch internship detail:', err);
        setError('INTERNSHIP_LOAD_FAILED');
      }
    } finally {
      if (generation === requestGenerationRef.current) {
        setLoading(false);
      }
    }
  }, [internshipId, locale]);

  useEffect(() => {
    fetchDetail();
  }, [fetchDetail]);

  const formatWorkType = (workType) => {
    if (!workType) return '';
    const lower = workType.toLowerCase();
    return t(`internships.workTypes.${lower}`, {
      defaultValue: workType.charAt(0).toUpperCase() + workType.slice(1).toLowerCase(),
    });
  };

  const formatDateString = (isoString) => {
    if (!isoString) return null;
    const formatted = formatLocalizedDate(isoString, locale);
    return formatted ? t('internshipDetail.postedDate', { date: formatted }) : null;
  };

  const { isSaved, toggleSave, isMutating } = useSavedInternships();

  const renderHeaderBookmark = () => {
    if (!internshipId) return null;
    return (
      <BookmarkButton
        isSaved={isSaved(internshipId)}
        disabled={!internship || isMutating(internshipId)}
        onPress={() => toggleSave(internship)}
        size={22}
      />
    );
  };

  return (
    <ScreenContainer edges={['top', 'bottom']}>
      <ScreenHeader
        title={t('internshipDetail.title')}
        showBack={true}
        navigation={navigation}
        rightAction={renderHeaderBookmark()}
      />

      <ScrollView
        style={styles.screen}
        contentContainerStyle={styles.content}
        showsVerticalScrollIndicator={false}
      >
        {/* Loading State */}
        {loading && (
          <View style={styles.centerContainer}>
            <ActivityIndicator size="large" color={colors.accent || colors.teal} />
            <Text style={[styles.loadingText, isRTL && styles.rtlText]}>{t('internshipDetail.loading')}</Text>
          </View>
        )}

        {/* 404 Not Found State */}
        {!loading && isNotFound && (
          <Card style={styles.statusCard} padding="lg">
            <Ionicons name="document-text-outline" size={48} color={colors.textTertiary || colors.textMuted} />
            <Text style={[styles.cardTitle, isRTL && styles.rtlText]}>{t('internshipDetail.notFoundTitle')}</Text>
            <Text style={styles.cardSubtitle}>
              {t('internshipDetail.notFoundMessage')}
            </Text>
            <TouchableOpacity
              style={styles.primaryButton}
              onPress={() => navigation.goBack()}
              accessibilityRole="button"
              accessibilityLabel={t('internshipDetail.backToInternships')}
            >
              <Text style={[styles.primaryButtonText, isRTL && styles.rtlText]}>{t('internshipDetail.backToInternships')}</Text>
            </TouchableOpacity>
          </Card>
        )}

        {/* Error State */}
        {!loading && !isNotFound && error && (
          <Card style={styles.errorCard} padding="lg">
            <Ionicons name="alert-circle-outline" size={48} color={colors.danger || '#EF4444'} />
            <Text style={[styles.cardTitle, isRTL && styles.rtlText]}>{t('internshipDetail.errorTitle')}</Text>
            <Text style={styles.cardSubtitle}>
              {t('errors.internshipLoadFailed', { defaultValue: t('internshipDetail.errorSubtitle', { defaultValue: t('internshipDetail.errorTitle') }) })}
            </Text>
            <TouchableOpacity
              style={styles.primaryButton}
              onPress={fetchDetail}
              accessibilityRole="button"
              accessibilityLabel={t('common.tryAgain')}
            >
              <Text style={[styles.primaryButtonText, isRTL && styles.rtlText]}>{t('common.tryAgain')}</Text>
            </TouchableOpacity>
          </Card>
        )}

        {/* Populated Listing */}
        {!loading && !isNotFound && !error && internship && (
          <>
            {/* Role Header Card */}
            <Card style={styles.heroCard} padding="md">
              <View style={[styles.headerRow, isRTL && styles.rowRTL]}>
                <Text style={styles.companyLocation}>
                  {internship.company} - {internship.location}
                </Text>
                {internship.work_type ? (
                  <View style={styles.workTypeBadge}>
                    <Text style={styles.workTypeText}>{formatWorkType(internship.work_type)}</Text>
                  </View>
                ) : null}
              </View>

              <Text style={styles.roleTitle}>{internship.title}</Text>

              {internship.posted_at ? (
                <Text style={styles.postedDate}>
                  {formatDateString(internship.posted_at)}
                </Text>
              ) : null}
            </Card>

            {/* Description Section */}
            <Text style={[styles.sectionTitle, isRTL && styles.rtlText]}>{t('internshipDetail.aboutRole')}</Text>
            <Card style={styles.descriptionCard} padding="md">
              <Text style={styles.descriptionText}>{internship.description}</Text>
            </Card>

            {/* Required Skills */}
            {internship.required_skills && internship.required_skills.length > 0 && (
              <>
                <Text style={[styles.sectionTitle, isRTL && styles.rtlText]}>{t('internshipDetail.requiredSkills')}</Text>
                <View style={[styles.chipRow, isRTL && styles.rowRTL]}>
                  {internship.required_skills.map((skill) => (
                    <Chip key={skill} label={skill} variant="skill" />
                  ))}
                </View>
              </>
            )}

            {/* Preferred Skills */}
            {internship.preferred_skills && internship.preferred_skills.length > 0 && (
              <>
                <Text style={[styles.sectionTitle, isRTL && styles.rtlText]}>{t('internshipDetail.preferredSkills')}</Text>
                <View style={[styles.chipRow, isRTL && styles.rowRTL]}>
                  {internship.preferred_skills.map((skill) => (
                    <Chip key={skill} label={skill} variant="neutral" />
                  ))}
                </View>
              </>
            )}

            {/* Languages & Education */}
            {(internship.languages?.length > 0 || internship.min_education) && (
              <>
                <Text style={[styles.sectionTitle, isRTL && styles.rtlText]}>{t('internshipDetail.requirementsAndBackground')}</Text>
                <Card style={styles.detailsCard} padding="md">
                  {internship.languages && internship.languages.length > 0 && (
                    <View style={[styles.detailItem, isRTL && styles.rowRTL]}>
                      <Ionicons
                        name="language-outline"
                        size={18}
                        color={colors.accent || colors.teal}
                        style={styles.detailIcon}
                      />
                      <View style={styles.detailTextContainer}>
                        <Text style={[styles.detailLabel, isRTL && styles.rtlText]}>{t('internshipDetail.workingLanguages')}</Text>
                        <Text style={styles.detailValue}>{internship.languages.join(', ')}</Text>
                      </View>
                    </View>
                  )}

                  {internship.min_education && (
                    <View style={[styles.detailItem, isRTL && styles.rowRTL, internship.languages?.length > 0 && { marginTop: spacing.md }]}>
                      <Ionicons
                        name="school-outline"
                        size={18}
                        color={colors.accent || colors.teal}
                        style={styles.detailIcon}
                      />
                      <View style={styles.detailTextContainer}>
                        <Text style={[styles.detailLabel, isRTL && styles.rtlText]}>{t('internshipDetail.educationLevel')}</Text>
                        <Text style={styles.detailValue}>{internship.min_education}</Text>
                      </View>
                    </View>
                  )}
                </Card>
              </>
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
    color: colors.textSecondary || colors.textMuted,
    marginTop: spacing.md,
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
    paddingVertical: spacing.sm + spacing.xxs,
    borderRadius: spacing.radii.sm,
    minHeight: spacing.minimumTouchTarget,
    alignItems: 'center',
    justifyContent: 'center',
  },
  primaryButtonText: {
    ...typography.button,
    color: colors.textInverse || colors.white,
  },
  heroCard: {
    marginBottom: spacing.lg,
  },
  headerRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: spacing.xs,
  },
  companyLocation: {
    ...typography.caption,
    color: colors.textSecondary || colors.textMuted,
    flex: 1,
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
  roleTitle: {
    ...typography.screenTitle,
    color: colors.textPrimary || colors.textDark,
    marginTop: spacing.xs,
  },
  postedDate: {
    ...typography.caption,
    color: colors.textTertiary || colors.textMuted,
    marginTop: spacing.xs,
  },
  sectionTitle: {
    ...typography.sectionTitle,
    color: colors.textPrimary || colors.textDark,
    marginTop: spacing.lg,
    marginBottom: spacing.sm,
  },
  descriptionCard: {
    marginBottom: spacing.xs,
  },
  descriptionText: {
    ...typography.body,
    color: colors.textPrimary || colors.textDark,
    lineHeight: 22,
  },
  chipRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    marginBottom: spacing.xs,
  },
  detailsCard: {
    marginBottom: spacing.lg,
  },
  detailItem: {
    flexDirection: 'row',
    alignItems: 'flex-start',
  },
  detailIcon: {
    marginEnd: spacing.md,
    marginTop: spacing.xxs,
  },
  detailTextContainer: {
    flex: 1,
  },
  detailLabel: {
    ...typography.caption,
    color: colors.textSecondary || colors.textMuted,
    fontWeight: '500',
  },
  detailValue: {
    ...typography.bodyEmphasis,
    color: colors.textPrimary || colors.textDark,
    marginTop: spacing.xxs,
  },
  rowRTL: {
    flexDirection: 'row-reverse',
  },
  rtlText: {
    writingDirection: 'rtl',
    textAlign: 'right',
  },
});
