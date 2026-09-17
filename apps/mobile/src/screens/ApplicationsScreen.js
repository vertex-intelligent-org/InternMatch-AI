import React, { useEffect, useState, useCallback, useRef } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  ActivityIndicator,
  RefreshControl,
  Alert,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTranslation } from 'react-i18next';
import { useScrollToTop, useFocusEffect } from '@react-navigation/native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import colors from '../theme/colors';
import { spacing } from '../theme/spacing';
import { typography } from '../theme/typography';
import { getTabScreenBottomPadding } from '../theme/tabBarLayout';
import ScreenContainer from '../components/ScreenContainer';
import ScreenHeader from '../components/ScreenHeader';
import AuthenticatedAppChromeHeader from '../components/AuthenticatedAppChromeHeader';
import Card from '../components/Card';
import GradientButton from '../components/GradientButton';
import {
  getApplications,
  updateApplicationStatus,
  ApiError,
} from '../services/api';
import haptics from '../services/haptics';
import { useTabScroll, useTabScrollReporter } from '../context/TabScrollContext';
import { useLocalization } from '../localization/LocalizationContext';
import { formatLocalizedDate } from '../localization/formatters';

const STATUS_THEME = {
  saved: { bg: colors.surfaceMuted || '#F1F5F9', fg: colors.textSecondary || '#475569' },
  applied: { bg: colors.infoSoft || '#E0F2FE', fg: colors.info || '#0284C7' },
  interviewing: { bg: colors.warningSoft || '#FEF3C7', fg: colors.warning || '#D97706' },
  rejected: { bg: colors.dangerSoft || '#FEE2E2', fg: colors.danger || '#DC2626' },
  accepted: { bg: colors.successSoft || '#DCFCE7', fg: colors.success || '#16A34A' },
};

function StatusPill({ status }) {
  const { t } = useTranslation();
  const theme = STATUS_THEME[status] || STATUS_THEME.saved;
  const label = t(`applications.statuses.${status}`, { defaultValue: status });
  return (
    <View style={[styles.pill, { backgroundColor: theme.bg }]}>
      <Text style={[styles.pillText, { color: theme.fg }]}>{label}</Text>
    </View>
  );
}

export default function ApplicationsScreen({ navigation }) {
  const { t } = useTranslation();
  const { locale, isRTL } = useLocalization();
  const insets = useSafeAreaInsets();
  const bottomPadding = getTabScreenBottomPadding(insets.bottom);
  const scrollViewRef = useRef(null);
  useTabScroll('Applications', scrollViewRef);
  useScrollToTop(scrollViewRef);
  const onScroll = useTabScrollReporter(20);

  const [applications, setApplications] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(null);
  const [statusUpdatingIds, setStatusUpdatingIds] = useState(() => new Set());
  const requestGenerationRef = useRef(0);
  const statusUpdateInFlightRef = useRef(new Set());

  const fetchApplicationsData = useCallback(async () => {
    const generation = ++requestGenerationRef.current;
    setError(null);
    try {
      const res = await getApplications();
      if (generation !== requestGenerationRef.current) return;
      setApplications(res.applications || []);
    } catch (err) {
      if (generation !== requestGenerationRef.current) return;
      console.warn('Failed to fetch applications:', err);
      if (err instanceof ApiError && err.status === 401) {
        setError('UNAUTHENTICATED');
      } else {
        setError('APPLICATIONS_LOAD_FAILED');
      }
    } finally {
      if (generation !== requestGenerationRef.current) return;
      setLoading(false);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      fetchApplicationsData();
      return () => {
        requestGenerationRef.current += 1;
      };
    }, [fetchApplicationsData])
  );

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      await fetchApplicationsData();
    } finally {
      setRefreshing(false);
    }
  };

  const handleQuickMarkApplied = async (applicationId) => {
    if (statusUpdateInFlightRef.current.has(applicationId)) return;

    statusUpdateInFlightRef.current.add(applicationId);
    requestGenerationRef.current += 1;

    setStatusUpdatingIds((current) => {
      const next = new Set(current);
      next.add(applicationId);
      return next;
    });

    try {
      await updateApplicationStatus(applicationId, { status: 'applied' });
      haptics.success();
      await fetchApplicationsData();
      Alert.alert(t('applications.markedAppliedAlertTitle'), t('applications.markedAppliedAlertBody'));
    } catch (err) {
      console.warn('Failed to update status:', err);
      Alert.alert(t('common.error'), t('errors.applicationStatusUpdateFailed'));
    } finally {
      statusUpdateInFlightRef.current.delete(applicationId);

      setStatusUpdatingIds((current) => {
        const next = new Set(current);
        next.delete(applicationId);
        return next;
      });
    }
  };

  const formatDateString = (dateString) => {
    if (!dateString) return null;
    const formatted = formatLocalizedDate(dateString, locale);
    return formatted ? t('applications.appliedDate', { date: formatted }) : null;
  };

  const renderCountBadge = () => {
    if (applications.length === 0 || loading) return null;
    return (
      <View style={styles.countBadge}>
        <Text style={styles.countBadgeText}>{applications.length}</Text>
      </View>
    );
  };

  return (
    <ScreenContainer edges={['top']}>
      <AuthenticatedAppChromeHeader />
      <ScreenHeader
        title={t('applications.title')}
        alignment="start"
        rightAction={renderCountBadge()}
      />

      <ScrollView
        ref={scrollViewRef}
        style={styles.screen}
        contentContainerStyle={[styles.content, { paddingBottom: bottomPadding }]}
        showsVerticalScrollIndicator={false}
        onScroll={onScroll}
        scrollEventThrottle={16}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={handleRefresh}
            colors={[colors.accent || colors.teal]}
            tintColor={colors.accent || colors.teal}
          />
        }
      >
        {/* Loading State */}
        {loading && !refreshing && (
          <View style={styles.centerContainer}>
            <ActivityIndicator size="large" color={colors.accent || colors.teal} />
            <Text style={[styles.loadingText, isRTL && styles.rtlText]}>{t('applications.loading')}</Text>
          </View>
        )}

        {/* Error State */}
        {!loading && error && (
          <Card style={styles.errorCard} padding="lg">
            <Ionicons name="alert-circle-outline" size={40} color={colors.danger || '#EF4444'} />
            <Text style={[styles.errorTitle, isRTL && styles.rtlText]}>{t('applications.errorTitle')}</Text>
            <Text style={styles.errorSubtitle}>
              {error === 'UNAUTHENTICATED'
                ? t('errors.unauthenticated')
                : t('errors.applicationsLoadFailed', { defaultValue: t('applications.errorSubtitle', { defaultValue: t('applications.errorTitle') }) })}
            </Text>
            <TouchableOpacity
              style={styles.retryBtn}
              onPress={fetchApplicationsData}
              accessibilityRole="button"
              accessibilityLabel={t('common.tryAgain')}
            >
              <Text style={[styles.retryBtnText, isRTL && styles.rtlText]}>{t('common.tryAgain')}</Text>
            </TouchableOpacity>
          </Card>
        )}

        {/* Empty State */}
        {!loading && !error && applications.length === 0 && (
          <Card style={styles.emptyCard} padding="lg">
            <Ionicons name="briefcase-outline" size={48} color={colors.accent || colors.teal} />
            <Text style={[styles.emptyTitle, isRTL && styles.rtlText]}>{t('applications.emptyTitle')}</Text>
            <Text style={styles.emptySubtitle}>
              {t('applications.emptySubtitle')}
            </Text>
            <GradientButton
              title={t('applications.exploreMatchups')}
              color={colors.accent || colors.teal}
              onPress={() => navigation.navigate('MainTabs', { screen: 'Matchups' })}
              style={{ marginTop: spacing.xl, width: '100%' }}
            />
          </Card>
        )}

        {/* Real Applications List */}
        {!loading && !error && applications.length > 0 && (
          <View style={styles.listContainer}>
            {applications.map((app) => {
              const hasCoverLetter = Boolean(app.generated_cover_letter);
              const isUpdatingThis = statusUpdatingIds.has(app.id);
              const appliedDateText = formatDateString(app.applied_date);

              return (
                <Card
                  key={app.id}
                  style={styles.appCard}
                  padding="md"
                >
                  <View style={[styles.cardHeader, isRTL && styles.rowRTL]}>
                    <View style={styles.cardTitleWrap}>
                      <Text style={[styles.jobTitle, isRTL && styles.rtlText]}>
                        {app.job_title || t('applications.defaultJobTitle')}
                      </Text>
                      {app.company_name ? (
                        <Text style={styles.companyName}>{app.company_name}</Text>
                      ) : null}
                    </View>
                    <StatusPill status={app.status} />
                  </View>

                  {/* Applied Date */}
                  {appliedDateText ? (
                    <View style={[styles.metaRow, isRTL && styles.rowRTL]}>
                      <Ionicons
                        name="calendar-outline"
                        size={13}
                        color={colors.textSecondary || colors.textMuted}
                        style={styles.metaIcon}
                      />
                      <Text style={styles.metaText}>
                        {appliedDateText}
                      </Text>
                    </View>
                  ) : null}

                  {/* Notes */}
                  {app.notes ? (
                    <View style={styles.notesBox}>
                      <Text style={styles.notesText}>{app.notes}</Text>
                    </View>
                  ) : null}

                  {/* Action Buttons */}
                  <View style={[styles.cardActions, isRTL && styles.rowRTL]}>
                    <TouchableOpacity
                      style={[styles.detailBtn, isRTL && styles.rowRTL]}
                      onPress={() =>
                        navigation.navigate('ApplicationDetail', {
                          applicationId: app.id,
                        })
                      }
                      accessibilityRole="button"
                      accessibilityLabel={t('applications.timelineBtn')}
                      hitSlop={{ top: 6, bottom: 6, left: 4, right: 4 }}
                    >
                      <Ionicons
                        name="time-outline"
                        size={14}
                        color={colors.textPrimary || colors.textDark}
                        style={styles.actionIcon}
                      />
                      <Text style={styles.detailBtnText} numberOfLines={2}>{t('applications.timelineBtn')}</Text>
                    </TouchableOpacity>

                    {hasCoverLetter && (
                      <TouchableOpacity
                        style={[styles.letterBtn, isRTL && styles.rowRTL]}
                        onPress={() =>
                          navigation.navigate('CoverLetter', {
                            applicationId: app.id,
                            draft: app.generated_cover_letter,
                            currentStatus: app.status,
                            internshipId: app.internship_id,
                            companyName: app.company_name,
                            jobTitle: app.job_title,
                          })
                        }
                        accessibilityRole="button"
                        accessibilityLabel={t('applications.coverLetterBtn')}
                        hitSlop={{ top: 6, bottom: 6, left: 4, right: 4 }}
                      >
                        <Ionicons
                          name="document-text-outline"
                          size={14}
                          color={colors.accentStrong || colors.tealDark}
                          style={styles.actionIcon}
                        />
                        <Text style={styles.letterBtnText} numberOfLines={2}>{t('applications.coverLetterBtn')}</Text>
                      </TouchableOpacity>
                    )}

                    {app.internship_id && (
                      <TouchableOpacity
                        style={[styles.listingBtn, isRTL && styles.rowRTL]}
                        onPress={() =>
                          navigation.navigate('InternshipDetail', {
                            internshipId: app.internship_id,
                          })
                        }
                        accessibilityRole="button"
                        accessibilityLabel={t('applications.listingBtn')}
                        hitSlop={{ top: 6, bottom: 6, left: 4, right: 4 }}
                      >
                        <Ionicons
                          name="open-outline"
                          size={14}
                          color={colors.textSecondary || colors.textMuted}
                          style={styles.actionIcon}
                        />
                        <Text style={styles.listingBtnText} numberOfLines={2}>{t('applications.listingBtn')}</Text>
                      </TouchableOpacity>
                    )}

                    {app.status === 'saved' && (
                      <TouchableOpacity
                        style={[styles.markAppliedBtn, isRTL && styles.rowRTL]}
                        onPress={() => handleQuickMarkApplied(app.id)}
                        disabled={isUpdatingThis}
                        accessibilityRole="button"
                        accessibilityLabel={t('applications.markAppliedBtn')}
                        accessibilityState={{
                          disabled: isUpdatingThis,
                          busy: isUpdatingThis,
                        }}
                        hitSlop={{ top: 6, bottom: 6, left: 4, right: 4 }}
                      >
                        {isUpdatingThis ? (
                          <ActivityIndicator
                            size="small"
                            color={colors.textInverse || colors.white}
                          />
                        ) : (
                          <>
                            <Ionicons
                              name="checkmark"
                              size={14}
                              color={colors.textInverse || colors.white}
                              style={styles.actionIcon}
                            />
                            <Text style={styles.markAppliedBtnText} numberOfLines={2}>{t('applications.markAppliedBtn')}</Text>
                          </>
                        )}
                      </TouchableOpacity>
                    )}
                  </View>
                </Card>
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
    paddingTop: spacing.xs,
    paddingBottom: 128,
  },
  countBadge: {
    backgroundColor: colors.accentSoft || '#E6F4F6',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xxs + 2,
    borderRadius: spacing.radii.pill,
    minHeight: 28,
    justifyContent: 'center',
    alignItems: 'center',
  },
  countBadgeText: {
    ...typography.badge,
    color: colors.accentStrong || colors.tealDark,
  },
  centerContainer: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: spacing.xxxl * 2,
  },
  loadingText: {
    ...typography.caption,
    color: colors.textSecondary || colors.textMuted,
    marginTop: spacing.md,
  },
  errorCard: {
    alignItems: 'center',
    marginTop: spacing.md,
    borderColor: colors.dangerSoft || '#FEE2E2',
    backgroundColor: '#FEF2F2',
  },
  errorTitle: {
    ...typography.cardTitle,
    color: colors.danger || '#EF4444',
    marginTop: spacing.sm,
  },
  errorSubtitle: {
    ...typography.caption,
    color: colors.textSecondary || colors.textMuted,
    textAlign: 'center',
    marginTop: spacing.xs,
    lineHeight: 18,
  },
  retryBtn: {
    marginTop: spacing.lg,
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
    marginTop: spacing.md,
  },
  emptyTitle: {
    ...typography.cardTitle,
    color: colors.textPrimary || colors.textDark,
    marginTop: spacing.md,
  },
  emptySubtitle: {
    ...typography.caption,
    color: colors.textSecondary || colors.textMuted,
    textAlign: 'center',
    marginTop: spacing.sm,
    lineHeight: 18,
  },
  listContainer: {
    marginTop: spacing.xs,
  },
  appCard: {
    marginBottom: spacing.md,
  },
  cardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
  },
  cardTitleWrap: {
    flex: 1,
    marginEnd: spacing.md,
  },
  jobTitle: {
    ...typography.cardTitle,
    color: colors.textPrimary || colors.textDark,
  },
  companyName: {
    ...typography.caption,
    color: colors.textSecondary || colors.textMuted,
    marginTop: spacing.xxs,
  },
  pill: {
    paddingHorizontal: spacing.sm + 2,
    paddingVertical: spacing.xxs + 1,
    borderRadius: spacing.radii.sm,
  },
  pillText: {
    ...typography.badge,
    fontSize: 11,
  },
  metaRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: spacing.sm,
  },
  metaIcon: {
    marginEnd: spacing.xs,
  },
  metaText: {
    ...typography.caption,
    color: colors.textSecondary || colors.textMuted,
  },
  notesBox: {
    backgroundColor: colors.surfaceSubtle || colors.cardBg,
    borderRadius: spacing.radii.sm,
    padding: spacing.sm,
    marginTop: spacing.sm,
    borderWidth: 1,
    borderColor: colors.borderSubtle || colors.border,
  },
  notesText: {
    ...typography.caption,
    color: colors.textPrimary || colors.textDark,
    fontStyle: 'italic',
  },
  cardActions: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    marginTop: spacing.md,
    paddingTop: spacing.sm,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.borderSubtle || colors.border,
    gap: spacing.sm,
  },
  letterBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.accentSoft || '#E6F4F6',
    paddingHorizontal: spacing.sm + 2,
    paddingVertical: spacing.xs + 2,
    borderRadius: spacing.radii.sm,
    minHeight: 36,
    flexGrow: 1,
    flexShrink: 1,
    flexBasis: '45%',
    minWidth: 0,
  },
  letterBtnText: {
    ...typography.caption,
    fontWeight: '600',
    color: colors.accentStrong || colors.tealDark,
    textAlign: 'center',
  },
  detailBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.surface || colors.cardBg,
    paddingHorizontal: spacing.sm + 2,
    paddingVertical: spacing.xs + 2,
    borderRadius: spacing.radii.sm,
    borderWidth: 1,
    borderColor: colors.borderSubtle || colors.border,
    minHeight: 36,
    flexGrow: 1,
    flexShrink: 1,
    flexBasis: '45%',
    minWidth: 0,
  },
  detailBtnText: {
    ...typography.caption,
    fontWeight: '600',
    color: colors.textPrimary || colors.textDark,
    textAlign: 'center',
  },
  listingBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.surfaceSubtle || '#F8FAFC',
    paddingHorizontal: spacing.sm + 2,
    paddingVertical: spacing.xs + 2,
    borderRadius: spacing.radii.sm,
    borderWidth: 1,
    borderColor: colors.borderSubtle || colors.border,
    minHeight: 36,
    flexGrow: 1,
    flexShrink: 1,
    flexBasis: '45%',
    minWidth: 0,
  },
  listingBtnText: {
    ...typography.caption,
    fontWeight: '600',
    color: colors.textSecondary || colors.textMuted,
    textAlign: 'center',
  },
  markAppliedBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.accent || colors.teal,
    paddingHorizontal: spacing.sm + 2,
    paddingVertical: spacing.xs + 2,
    borderRadius: spacing.radii.sm,
    minHeight: 36,
    flexGrow: 1,
    flexShrink: 1,
    flexBasis: '45%',
    minWidth: 0,
  },
  markAppliedBtnText: {
    ...typography.caption,
    fontWeight: '600',
    color: colors.textInverse || colors.white,
    textAlign: 'center',
  },
  actionIcon: {
    marginEnd: spacing.xs,
  },
  rowRTL: {
    flexDirection: 'row-reverse',
  },
  rtlText: {
    writingDirection: 'rtl',
    textAlign: 'right',
  },
});
