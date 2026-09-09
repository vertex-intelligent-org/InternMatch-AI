import React, { useState, useCallback, useRef } from 'react';
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
import { useFocusEffect, useScrollToTop } from '@react-navigation/native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import colors from '../theme/colors';
import { spacing } from '../theme/spacing';
import { typography } from '../theme/typography';
import { getTabScreenBottomPadding } from '../theme/tabBarLayout';
import { useLocalization } from '../localization/LocalizationContext';
import { formatLocalizedDate } from '../localization/formatters';
import { useTabScroll, useTabScrollReporter } from '../context/TabScrollContext';
import ScreenContainer from '../components/ScreenContainer';
import AuthenticatedAppChromeHeader from '../components/AuthenticatedAppChromeHeader';
import Card from '../components/Card';
import PressableCard from '../components/PressableCard';
import Chip from '../components/Chip';
import GradientButton from '../components/GradientButton';
import Reveal from '../components/motion/Reveal';
import { getEmployerInternships, closeEmployerOpportunity } from '../services/api';

export default function EmployerOpportunitiesScreen({ navigation }) {
  const { t } = useTranslation();
  const { locale, isRTL } = useLocalization();
  const insets = useSafeAreaInsets();

  const scrollViewRef = useRef(null);
  useTabScroll('Opportunities', scrollViewRef);
  useScrollToTop(scrollViewRef);
  const onScroll = useTabScrollReporter(20);

  const [opportunities, setOpportunities] = useState([]);
  const [totalCount, setTotalCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [closingId, setClosingId] = useState(null);
  const [error, setError] = useState(null);

  const fetchOpportunities = useCallback(async (isRefresh = false) => {
    if (isRefresh) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    setError(null);

    try {
      const res = await getEmployerInternships({ limit: 50 });
      setOpportunities(res.items || []);
      setTotalCount(typeof res.total === 'number' ? res.total : (res.items || []).length);
    } catch (err) {
      console.warn('Failed to fetch employer opportunities:', err);
      setError('LOAD_FAILED');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  const handleCloseOpportunity = useCallback((item) => {
    Alert.alert(
      t('employerOpportunities.closeAlertTitle', 'Close Opportunity?'),
      t(
        'employerOpportunities.closeAlertMessage',
        'Closing this opportunity will remove it from candidate discovery. Candidates will no longer be able to submit new applications. Existing applications will remain accessible.'
      ),
      [
        {
          text: t('common.cancel', 'Cancel'),
          style: 'cancel',
        },
        {
          text: t('employerOpportunities.closeConfirmBtn', 'Close Opportunity'),
          style: 'destructive',
          onPress: async () => {
            try {
              setClosingId(item.id);
              await closeEmployerOpportunity(item.id);
              setOpportunities((prev) =>
                prev.map((opp) =>
                  opp.id === item.id ? { ...opp, is_active: false } : opp
                )
              );
            } catch (err) {
              console.warn('Failed to close opportunity:', err);
              Alert.alert(
                t('common.error', 'Error'),
                t('employerOpportunities.closeError', 'Failed to close opportunity. Please try again.')
              );
            } finally {
              setClosingId(null);
            }
          },
        },
      ]
    );
  }, [t]);

  useFocusEffect(
    useCallback(() => {
      fetchOpportunities();
    }, [fetchOpportunities])
  );

  const handleRefresh = () => {
    fetchOpportunities(true);
  };

  const bottomPadding = getTabScreenBottomPadding(insets.bottom);

  return (
    <ScreenContainer edges={['top']}>
      <AuthenticatedAppChromeHeader />

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
        {/* Header Row */}
        <Reveal delay={0}>
          <View style={[styles.headerRow, isRTL && styles.rowRTL]}>
            <View style={styles.headerTitleBlock}>
              <Text style={[styles.eyebrow, isRTL && styles.rtlText]}>
                {t('employerOpportunities.eyebrow')}
              </Text>
              <Text style={[styles.screenTitle, isRTL && styles.rtlText]}>
                {t('employerOpportunities.title')}
              </Text>
            </View>

            <TouchableOpacity
              style={[styles.createHeaderBtn, isRTL && styles.rowRTL]}
              onPress={() => navigation.navigate('CreateOpportunity')}
              accessibilityRole="button"
              accessibilityLabel={t('employerOpportunities.createOpportunity')}
            >
              <Ionicons name="add" size={18} color={colors.textInverse || colors.white} />
              <Text style={styles.createHeaderBtnText}>
                {t('employerOpportunities.createBtn')}
              </Text>
            </TouchableOpacity>
          </View>
        </Reveal>

        {/* Loading State */}
        {loading && !refreshing && (
          <View style={styles.centerLoading}>
            <ActivityIndicator size="large" color={colors.accent || colors.teal} />
            <Text style={[styles.loadingText, isRTL && styles.rtlWriting]}>
              {t('employerOpportunities.loading')}
            </Text>
          </View>
        )}

        {/* Error State */}
        {error && !loading && (
          <Card style={styles.errorCard} padding="lg">
            <Ionicons name="alert-circle-outline" size={32} color={colors.danger || '#EF4444'} />
            <Text style={[styles.errorTitle, isRTL && styles.rtlWriting]}>
              {t('employerOpportunities.errorTitle')}
            </Text>
            <Text style={[styles.errorSubtitle, isRTL && styles.rtlWriting]}>
              {t('employerOpportunities.errorSubtitle')}
            </Text>
            <TouchableOpacity
              style={styles.retryBtn}
              onPress={() => fetchOpportunities()}
              accessibilityRole="button"
              accessibilityLabel={t('employerOpportunities.retry')}
            >
              <Text style={styles.retryBtnText}>{t('employerOpportunities.retry')}</Text>
            </TouchableOpacity>
          </Card>
        )}

        {/* Empty State */}
        {!loading && !error && opportunities.length === 0 && (
          <Card style={styles.emptyCard} padding="xl">
            <View style={styles.emptyIconCircle}>
              <Ionicons name="briefcase-outline" size={36} color={colors.accent || colors.teal} />
            </View>
            <Text style={[styles.emptyTitle, isRTL && styles.rtlWriting]}>
              {t('employerOpportunities.emptyTitle')}
            </Text>
            <Text style={[styles.emptySubtitle, isRTL && styles.rtlWriting]}>
              {t('employerOpportunities.emptySubtitle')}
            </Text>
            <GradientButton
              title={`+ ${t('employerOpportunities.createOpportunity')}`}
              color={colors.accent || colors.teal}
              onPress={() => navigation.navigate('CreateOpportunity')}
              style={styles.emptyCta}
            />
          </Card>
        )}

        {/* Populated Opportunities List */}
        {!loading && !error && opportunities.length > 0 && (
          <View style={styles.listContainer}>
            {opportunities.map((item, index) => {
              const postedDateStr = item.posted_at
                ? formatLocalizedDate(item.posted_at, locale)
                : '';
              const allSkills = [
                ...(item.required_skills || []),
                ...(item.preferred_skills || []),
              ];
              const previewSkills = allSkills.slice(0, 3);
              const remainingCount = allSkills.length - previewSkills.length;

              return (
                <Reveal key={item.id} delay={index * 40}>
                  <PressableCard
                    style={styles.oppCard}
                    padding="md"
                    onPress={() =>
                      navigation.navigate('EmployerApplicants', {
                        internshipId: item.id,
                        title: item.title,
                      })
                    }
                    accessibilityLabel={`${item.title} at ${item.company}`}
                  >
                    {/* Header: Title and Badges */}
                    <View style={[styles.cardHeader, isRTL && styles.rowRTL]}>
                      <Text style={[styles.title, isRTL && styles.rtlText]} numberOfLines={1}>
                        {item.title}
                      </Text>
                      <View style={[styles.badgesContainer, isRTL && styles.rowRTL]}>
                        <View
                          style={[
                            styles.statusBadge,
                            item.is_active === false ? styles.closedBadge : styles.publishedBadge,
                          ]}
                        >
                          <View
                            style={[
                              styles.statusDot,
                              item.is_active === false ? styles.closedDot : styles.publishedDot,
                            ]}
                          />
                          <Text
                            style={[
                              styles.statusBadgeText,
                              item.is_active === false
                                ? styles.closedBadgeText
                                : styles.publishedBadgeText,
                            ]}
                          >
                            {item.is_active === false
                              ? t('employerOpportunities.statusClosed', 'Closed')
                              : t('employerOpportunities.statusPublished', 'Published')}
                          </Text>
                        </View>
                        <View style={styles.workTypeBadge}>
                          <Text style={styles.workTypeBadgeText}>{item.work_type}</Text>
                        </View>
                      </View>
                    </View>

                    {/* Company and Location */}
                    <Text style={[styles.metaText, isRTL && styles.rtlText]}>
                      {item.company} {'\u00b7'} {item.location}
                    </Text>

                    {/* Skills preview chips */}
                    {previewSkills.length > 0 && (
                      <View style={[styles.skillsRow, isRTL && styles.rowRTL]}>
                        {previewSkills.map((sk) => (
                          <Chip key={sk} label={sk} variant="skill" />
                        ))}
                        {remainingCount > 0 && (
                          <View style={styles.moreSkillsBadge}>
                            <Text style={styles.moreSkillsText}>+{remainingCount}</Text>
                          </View>
                        )}
                      </View>
                    )}

                    {/* Footer Row */}
                    <View style={[styles.cardFooter, isRTL && styles.rowRTL]}>
                      {postedDateStr ? (
                        <Text style={[styles.postedDate, isRTL && styles.rtlText]}>
                          {t('employerOpportunities.postedOn', { date: postedDateStr })}
                        </Text>
                      ) : (
                        <View />
                      )}

                      <View style={[styles.cardActionGroup, isRTL && styles.rowRTL]}>
                        {item.is_active !== false && (
                          <TouchableOpacity
                            style={[styles.editOpportunityBtn, isRTL && styles.rowRTL]}
                            onPress={() =>
                              navigation.navigate('CreateOpportunity', {
                                internshipId: item.id,
                                opportunity: item,
                              })
                            }
                            accessibilityRole="button"
                            accessibilityLabel={`${t(
                              'employerOpportunities.editBtn',
                              'Edit'
                            )} ${item.title}`}
                          >
                            <Ionicons
                              name="create-outline"
                              size={15}
                              color={colors.accentStrong || colors.tealDark}
                            />
                            <Text
                              style={[
                                styles.editOpportunityBtnText,
                                isRTL && styles.rtlText,
                              ]}
                            >
                              {t('employerOpportunities.editBtn', 'Edit')}
                            </Text>
                          </TouchableOpacity>
                        )}

                        {item.is_active !== false && (
                          <TouchableOpacity
                            style={[styles.closeOpportunityBtn, isRTL && styles.rowRTL]}
                            onPress={() => handleCloseOpportunity(item)}
                            disabled={closingId === item.id}
                            accessibilityRole="button"
                            accessibilityLabel={`${t('employerOpportunities.closeBtn', 'Close')} ${item.title}`}
                          >
                            {closingId === item.id ? (
                              <ActivityIndicator size="small" color={colors.textMuted || '#9CA3AF'} />
                            ) : (
                              <Text style={[styles.closeOpportunityBtnText, isRTL && styles.rtlText]}>
                                {t('employerOpportunities.closeBtn', 'Close')}
                              </Text>
                            )}
                          </TouchableOpacity>
                        )}

                        <TouchableOpacity
                          style={[styles.viewApplicantsBtn, isRTL && styles.rowRTL]}
                          onPress={() =>
                            navigation.navigate('EmployerApplicants', {
                              internshipId: item.id,
                              title: item.title,
                            })
                          }
                          accessibilityRole="button"
                          accessibilityLabel={`${t('employerOpportunities.viewApplicants')} for ${item.title}`}
                        >
                          <Text style={[styles.viewApplicantsBtnText, isRTL && styles.rtlText]}>
                            {t('employerOpportunities.viewApplicants')}
                          </Text>
                          <Ionicons
                            name={isRTL ? 'arrow-back' : 'arrow-forward'}
                            size={14}
                            color={colors.accentStrong || colors.tealDark}
                            style={[styles.browseIcon, isRTL && styles.browseIconRTL]}
                          />
                        </TouchableOpacity>
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
    paddingTop: spacing.xs,
  },
  headerRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: spacing.md,
    paddingTop: spacing.sm,
  },
  headerTitleBlock: {
    flex: 1,
    marginEnd: spacing.sm,
  },
  eyebrow: {
    ...typography.eyebrow,
    color: colors.accentStrong || colors.tealDark,
    letterSpacing: 0.6,
  },
  screenTitle: {
    ...typography.display,
    color: colors.textPrimary || colors.textDark,
    marginTop: spacing.xxs,
  },
  createHeaderBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.accent || colors.teal,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs + 2,
    borderRadius: spacing.radii.pill,
    minHeight: spacing.minimumTouchTarget,
  },
  createHeaderBtnText: {
    ...typography.button,
    color: colors.textInverse || colors.white,
    fontSize: 13,
    marginStart: 4,
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
  },
  retryBtnText: {
    ...typography.button,
    color: colors.accent || colors.teal,
    fontSize: 13,
  },
  emptyCard: {
    alignItems: 'center',
    marginTop: spacing.lg,
    backgroundColor: colors.surface || colors.cardBg,
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
    marginTop: spacing.xxs,
    lineHeight: 18,
    maxWidth: 280,
  },
  emptyCta: {
    marginTop: spacing.lg,
    width: '100%',
  },
  listContainer: {
    gap: spacing.sm,
  },
  oppCard: {
    marginBottom: spacing.sm,
  },
  cardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: spacing.xxs,
  },
  title: {
    flex: 1,
    ...typography.cardTitle,
    fontSize: 16,
    color: colors.textPrimary || colors.textDark,
    marginEnd: spacing.sm,
  },
  badgesContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  statusBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: spacing.sm,
    paddingVertical: 2,
    borderRadius: spacing.radii.pill,
  },
  statusDot: {
    width: 5,
    height: 5,
    borderRadius: 2.5,
    marginEnd: 4,
  },
  editOpportunityBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    minHeight: spacing.minimumTouchTarget,
    paddingHorizontal: spacing.sm,
  },
  editOpportunityBtnText: {
    ...typography.button,
    fontSize: 12,
    color: colors.accentStrong || colors.tealDark,
  },
  publishedBadge: {
    backgroundColor: '#ECFDF5',
  },
  publishedDot: {
    backgroundColor: '#10B981',
  },
  publishedBadgeText: {
    ...typography.badge,
    fontSize: 10,
    color: '#065F46',
    fontWeight: '600',
  },
  closedBadge: {
    backgroundColor: '#F3F4F6',
  },
  closedDot: {
    backgroundColor: '#9CA3AF',
  },
  closedBadgeText: {
    ...typography.badge,
    fontSize: 10,
    color: '#6B7280',
    fontWeight: '600',
  },
  statusBadgeText: {
    ...typography.badge,
    fontSize: 10,
  },
  workTypeBadge: {
    backgroundColor: colors.accentSoft || '#E6F4F6',
    paddingHorizontal: spacing.sm,
    paddingVertical: 2,
    borderRadius: spacing.radii.pill,
  },
  workTypeBadgeText: {
    ...typography.badge,
    fontSize: 11,
    color: colors.accentStrong || colors.tealDark,
    textTransform: 'capitalize',
  },
  metaText: {
    ...typography.caption,
    color: colors.textSecondary || colors.textMuted,
    marginBottom: spacing.sm,
  },
  skillsRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    marginBottom: spacing.xs,
  },
  moreSkillsBadge: {
    backgroundColor: '#EDEDED',
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xs + 2,
    borderRadius: spacing.radii.pill,
    marginBottom: spacing.sm,
  },
  moreSkillsText: {
    ...typography.badge,
    fontSize: 11,
    color: colors.textMuted,
  },
  cardFooter: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.borderSubtle || colors.border,
    paddingTop: spacing.xs,
    marginTop: spacing.xs,
  },
  cardActionGroup: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
  },
  closeOpportunityBtn: {
    paddingVertical: spacing.xxs,
    paddingHorizontal: spacing.xs,
    minHeight: spacing.minimumTouchTarget,
    justifyContent: 'center',
  },
  closeOpportunityBtnText: {
    ...typography.button,
    color: colors.textSecondary || '#6B7280',
    fontSize: 12,
  },
  postedDate: {
    ...typography.caption,
    fontSize: 12,
    color: colors.textTertiary || colors.textMuted,
  },
  viewApplicantsBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: spacing.xxs,
    minHeight: spacing.minimumTouchTarget,
  },
  viewApplicantsBtnText: {
    ...typography.button,
    color: colors.accentStrong || colors.tealDark,
    fontSize: 13,
  },
  browseIcon: {
    marginStart: 4,
  },
  browseIconRTL: {
    marginStart: 0,
    marginEnd: 4,
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
