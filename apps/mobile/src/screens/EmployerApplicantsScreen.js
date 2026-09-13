import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  ActivityIndicator,
  RefreshControl,
  TouchableOpacity,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTranslation } from 'react-i18next';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import colors from '../theme/colors';
import { spacing } from '../theme/spacing';
import { typography } from '../theme/typography';
import { useLocalization } from '../localization/LocalizationContext';
import { formatLocalizedDate } from '../localization/formatters';
import ScreenContainer from '../components/ScreenContainer';
import ScreenHeader from '../components/ScreenHeader';
import Card from '../components/Card';
import PressableCard from '../components/PressableCard';
import MatchBadge from '../components/MatchBadge';
import Reveal from '../components/motion/Reveal';
import { getEmployerApplicants } from '../services/api';
import EmployerShortlistComparison from '../components/EmployerShortlistComparison';

function getStatusBadgeStyle(status) {
  switch (status) {
    case 'applied':
      return {
        bg: colors.infoSoft || '#E0F2FE',
        fg: colors.info || '#0284C7',
      };
    case 'interviewing':
      return {
        bg: colors.warningSoft || '#FEF3C7',
        fg: colors.warning || '#D97706',
      };
    case 'accepted':
      return {
        bg: colors.successSoft || '#DCFCE7',
        fg: colors.success || '#10B981',
      };
    case 'rejected':
      return {
        bg: colors.dangerSoft || '#FEE2E2',
        fg: colors.danger || '#EF4444',
      };
    default:
      return {
        bg: '#EDEDED',
        fg: colors.textMuted,
      };
  }
}

export default function EmployerApplicantsScreen({ route, navigation }) {
  const { t } = useTranslation();
  const { locale, isRTL } = useLocalization();
  const insets = useSafeAreaInsets();

  const { internshipId, title: opportunityTitle } = route.params || {};

  const [applicants, setApplicants] = useState([]);
  const [totalCount, setTotalCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(null);

  const fetchApplicants = useCallback(
    async (isRefresh = false) => {
      if (!internshipId) return;

      if (isRefresh) {
        setRefreshing(true);
      } else {
        setLoading(true);
      }
      setError(null);

      try {
        const res = await getEmployerApplicants(internshipId);
        setApplicants(res.items || []);
        setTotalCount(typeof res.total === 'number' ? res.total : (res.items || []).length);
      } catch (err) {
        console.warn('Failed to load employer applicants:', err);
        setError('LOAD_FAILED');
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [internshipId]
  );

  useEffect(() => {
    fetchApplicants();
  }, [fetchApplicants]);

  const handleRefresh = () => {
    fetchApplicants(true);
  };

  return (
    <ScreenContainer edges={['top', 'bottom']}>
      <ScreenHeader
        title={t('employerApplicants.title')}
        subtitle={opportunityTitle || undefined}
        showBack
        navigation={navigation}
        alignment="center"
        bordered
      />

      <ScrollView
        style={styles.screen}
        contentContainerStyle={[styles.content, { paddingBottom: insets.bottom + 32 }]}
        showsVerticalScrollIndicator={false}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={handleRefresh}
            colors={[colors.accent || colors.teal]}
            tintColor={colors.accent || colors.teal}
          />
        }
      >
        {/* Sequence 1: Summary Eyebrow */}
        <Reveal delay={0}>
          <View style={[styles.summaryHeader, isRTL && styles.rowRTL]}>
            <Text style={[styles.eyebrow, isRTL && styles.rtlText]}>
              {t('employerApplicants.eyebrow')}
            </Text>
            {!loading && !error && applicants.length > 0 && (
              <Text style={styles.totalBadge}>
                {t('employerApplicants.total', { count: totalCount })}
              </Text>
            )}
          </View>
        </Reveal>

        {/* Loading State */}
        {loading && !refreshing && (
          <View style={styles.centerLoading}>
            <ActivityIndicator size="large" color={colors.accent || colors.teal} />
            <Text style={[styles.loadingText, isRTL && styles.rtlWriting]}>
              {t('employerApplicants.loading')}
            </Text>
          </View>
        )}

        {/* Error State */}
        {error && !loading && (
          <Card style={styles.errorCard} padding="lg">
            <Ionicons name="alert-circle-outline" size={32} color={colors.danger || '#EF4444'} />
            <Text style={[styles.errorTitle, isRTL && styles.rtlWriting]}>
              {t('employerApplicants.errorTitle')}
            </Text>
            <Text style={[styles.errorSubtitle, isRTL && styles.rtlWriting]}>
              {t('employerApplicants.errorSubtitle')}
            </Text>
            <TouchableOpacity
              style={styles.retryBtn}
              onPress={() => fetchApplicants()}
              accessibilityRole="button"
              accessibilityLabel={t('employerApplicants.retry')}
            >
              <Text style={styles.retryBtnText}>{t('employerApplicants.retry')}</Text>
            </TouchableOpacity>
          </Card>
        )}

        {!loading && !error && applicants.length >= 2 && (
          <EmployerShortlistComparison
            internshipId={internshipId}
            applicants={applicants}
            navigation={navigation}
            isRTL={isRTL}
          />
        )}

        {/* Empty State */}
        {!loading && !error && applicants.length === 0 && (
          <Card style={styles.emptyCard} padding="xl">
            <View style={styles.emptyIconCircle}>
              <Ionicons name="people-outline" size={36} color={colors.accent || colors.teal} />
            </View>
            <Text style={[styles.emptyTitle, isRTL && styles.rtlWriting]}>
              {t('employerApplicants.emptyTitle')}
            </Text>
            <Text style={[styles.emptySubtitle, isRTL && styles.rtlWriting]}>
              {t('employerApplicants.emptySubtitle')}
            </Text>
          </Card>
        )}

        {/* Populated Applicants List */}
        {!loading && !error && applicants.length > 0 && (
          <View style={styles.listContainer}>
            {applicants.map((item, index) => {
              const statusStyle = getStatusBadgeStyle(item.status);
              const appliedDateStr = item.applied_date
                ? formatLocalizedDate(item.applied_date, locale)
                : '';

              const fitKey =
                typeof item.match_score !== 'number'
                  ? 'unscored'
                  : item.match_score >= 80
                    ? 'top'
                    : item.match_score >= 65
                      ? 'strong'
                      : item.match_score >= 50
                        ? 'good'
                        : 'developing';

              return (
                <Reveal key={item.application_id} delay={index * 30}>
                  <PressableCard
                    style={styles.applicantCard}
                    padding="md"
                    onPress={() =>
                      navigation.navigate('EmployerApplicantDetail', {
                        internshipId,
                        applicationId: item.application_id,
                        applicant: item,
                      })
                    }
                    accessibilityLabel={`${item.candidate?.full_name}, status: ${item.status}`}
                  >
                    <View style={[styles.rankRow, isRTL && styles.rowRTL]}>
                      {typeof item.ai_rank === 'number' ? (
                        <View style={[styles.rankBadge, item.ai_rank <= 3 && styles.rankBadgeTop]}>
                          <Ionicons
                            name={item.ai_rank === 1 ? 'sparkles' : 'analytics-outline'}
                            size={14}
                            color={
                              item.ai_rank <= 3
                                ? (colors.accentStrong || colors.tealDark)
                                : (colors.textSecondary || colors.textMuted)
                            }
                          />
                          <Text
                            style={[
                              styles.rankBadgeText,
                              item.ai_rank <= 3 && styles.rankBadgeTextTop,
                            ]}
                          >
                            {t('employerCandidateRanking.rankLabel', {
                              rank: item.ai_rank,
                            })}
                          </Text>
                        </View>
                      ) : null}

                      <Text style={[styles.fitLabel, isRTL && styles.rtlText]}>
                        {t(`employerCandidateRanking.fit.${fitKey}`)}
                      </Text>
                    </View>

                    {/* Header: Candidate Name, Status Badge, Match Badge */}
                    <View style={[styles.cardHeader, isRTL && styles.rowRTL]}>
                      <View style={styles.nameBlock}>
                        <Text style={[styles.candidateName, isRTL && styles.rtlText]} numberOfLines={1}>
                          {item.candidate?.full_name || 'Candidate'}
                        </Text>
                        {item.candidate?.headline ? (
                          <Text style={[styles.candidateHeadline, isRTL && styles.rtlText]} numberOfLines={1}>
                            {item.candidate.headline}
                          </Text>
                        ) : null}
                      </View>

                      {typeof item.match_score === 'number' && (
                        <MatchBadge score={item.match_score} />
                      )}
                    </View>

                    {(item.matching_skills?.length > 0 || item.missing_skills?.length > 0) && (
                      <View style={styles.aiEvidenceRow}>
                        <Ionicons
                          name="sparkles-outline"
                          size={14}
                          color={colors.accent || colors.teal}
                        />
                        <Text
                          style={[styles.aiEvidenceText, isRTL && styles.rtlText]}
                          numberOfLines={2}
                        >
                          {item.matching_skills?.length > 0
                            ? t('employerCandidateRanking.matchingEvidence', {
                                skills: item.matching_skills.slice(0, 3).join(', '),
                              })
                            : t('employerCandidateRanking.noMatchingEvidence')}
                        </Text>
                      </View>
                    )}

                    {/* Department / Meta */}
                    {item.candidate?.department ? (
                      <Text style={[styles.departmentText, isRTL && styles.rtlText]}>
                        {item.candidate.department}
                      </Text>
                    ) : null}

                    {/* Footer: Status Pill and Applied Date */}
                    <View style={[styles.cardFooter, isRTL && styles.rowRTL]}>
                      <View style={[styles.statusPill, { backgroundColor: statusStyle.bg }]}>
                        <Text style={[styles.statusPillText, { color: statusStyle.fg }]}>
                          {t(
                            `applicationStatusLabels.${item.status}`,
                            item.status
                          )}
                        </Text>
                      </View>

                      {appliedDateStr ? (
                        <Text style={[styles.appliedDate, isRTL && styles.rtlText]}>
                          {t('employerApplicants.appliedOn', { date: appliedDateStr })}
                        </Text>
                      ) : null}

                      <View style={[styles.viewDetailLink, isRTL && styles.rowRTL]}>
                        <Ionicons
                          name={isRTL ? 'chevron-back' : 'chevron-forward'}
                          size={16}
                          color={colors.textTertiary || colors.textMuted}
                        />
                      </View>
                    </View>
                  </PressableCard>
                </Reveal>
              );
            })}
          </View>
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
    paddingTop: spacing.md,
  },
  summaryHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: spacing.md,
  },
  eyebrow: {
    ...typography.eyebrow,
    color: colors.accentStrong || colors.tealDark,
    letterSpacing: 0.6,
  },
  totalBadge: {
    ...typography.caption,
    fontWeight: '600',
    color: colors.textSecondary || colors.textMuted,
  },
  centerLoading: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: spacing.xxl,
  },
  loadingText: {
    ...typography.caption,
    color: colors.textSecondary || colors.textMuted,
    marginTop: spacing.sm,
  },
  errorCard: {
    alignItems: 'center',
    marginTop: spacing.md,
    backgroundColor: '#FEF2F2',
    borderColor: colors.dangerSoft || '#FEE2E2',
  },
  errorTitle: {
    ...typography.cardTitle,
    color: colors.danger || '#EF4444',
    marginTop: spacing.sm,
  },
  errorSubtitle: {
    ...typography.caption,
    color: colors.textSecondary || colors.textMuted,
    marginTop: spacing.xxs,
    textAlign: 'center',
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
    marginTop: spacing.lg,
  },
  emptyIconCircle: {
    width: 64,
    height: 64,
    borderRadius: 32,
    backgroundColor: colors.accentSoft || '#E6F4F6',
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: spacing.md,
  },
  emptyTitle: {
    ...typography.cardTitle,
    fontSize: 18,
    color: colors.textPrimary || colors.textDark,
    textAlign: 'center',
  },
  emptySubtitle: {
    ...typography.caption,
    color: colors.textSecondary || colors.textMuted,
    textAlign: 'center',
    marginTop: spacing.xs,
    lineHeight: 18,
    maxWidth: 300,
  },
  listContainer: {
    gap: spacing.sm,
  },
  applicantCard: {
    marginBottom: spacing.sm,
  },
  rankRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: spacing.sm,
    gap: spacing.sm,
  },
  rankBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    paddingHorizontal: spacing.sm,
    paddingVertical: 4,
    borderRadius: spacing.radii.pill,
    backgroundColor: colors.surfaceMuted || '#F1F5F9',
  },
  rankBadgeTop: {
    backgroundColor: colors.accentSoft || '#E6F4F6',
  },
  rankBadgeText: {
    ...typography.badge,
    fontSize: 11,
    color: colors.textSecondary || colors.textMuted,
    fontWeight: '700',
  },
  rankBadgeTextTop: {
    color: colors.accentStrong || colors.tealDark,
  },
  fitLabel: {
    ...typography.caption,
    fontSize: 12,
    fontWeight: '600',
    color: colors.textSecondary || colors.textMuted,
  },
  aiEvidenceRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 6,
    marginTop: spacing.xs,
    marginBottom: spacing.sm,
  },
  aiEvidenceText: {
    ...typography.caption,
    flex: 1,
    color: colors.textSecondary || colors.textMuted,
    lineHeight: 17,
  },
  cardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: spacing.xxs,
  },
  nameBlock: {
    flex: 1,
    marginEnd: spacing.sm,
  },
  candidateName: {
    ...typography.cardTitle,
    fontSize: 16,
    color: colors.textPrimary || colors.textDark,
  },
  candidateHeadline: {
    ...typography.caption,
    color: colors.textSecondary || colors.textMuted,
    marginTop: 2,
  },
  departmentText: {
    ...typography.caption,
    color: colors.accentStrong || colors.tealDark,
    marginBottom: spacing.sm,
  },
  cardFooter: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.borderSubtle || colors.border,
    paddingTop: spacing.xs,
    marginTop: spacing.xs,
  },
  statusPill: {
    paddingHorizontal: spacing.sm,
    paddingVertical: 2,
    borderRadius: spacing.radii.pill,
  },
  statusPillText: {
    ...typography.badge,
    fontSize: 11,
    textTransform: 'capitalize',
    fontWeight: '600',
  },
  appliedDate: {
    ...typography.caption,
    fontSize: 12,
    color: colors.textTertiary || colors.textMuted,
  },
  viewDetailLink: {
    paddingStart: spacing.xs,
  },
  rowRTL: {
    flexDirection: 'row-reverse',
  },
  rtlText: {
    writingDirection: 'rtl',
    textAlign: 'right',
  },
  rtlWriting: {
    writingDirection: 'rtl',
  },
});
