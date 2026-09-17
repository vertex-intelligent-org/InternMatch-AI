import React, { useEffect, useState, useCallback, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { getLocalizedErrorMessage } from '../localization/errorMessages';
import { useLocalization } from '../localization/LocalizationContext';
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
import { useScrollToTop } from '@react-navigation/native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import colors from '../theme/colors';
import { spacing } from '../theme/spacing';
import { typography } from '../theme/typography';
import motionTokens from '../motion/motionTokens';
import { getTabScreenBottomPadding } from '../theme/tabBarLayout';
import ScreenContainer from '../components/ScreenContainer';
import Card from '../components/Card';
import GlassSurface from '../components/GlassSurface';
import PressableCard from '../components/PressableCard';
import PressableScale from '../components/PressableScale';
import GradientButton from '../components/GradientButton';
import MatchBadge from '../components/MatchBadge';
import Reveal from '../components/motion/Reveal';
import MatchIntelligenceOrb from '../components/motion/MatchIntelligenceOrb';
import AIPulse from '../components/motion/AIPulse';
import AuthenticatedAppChromeHeader from '../components/AuthenticatedAppChromeHeader';
import { useProfile } from '../context/ProfileContext';
import { useTabScroll, useTabScrollReporter } from '../context/TabScrollContext';
import { normalizeAccountType } from '../services/subscriptionService';
import { ApiError, getMatches, getEmployerInternships, getEmployerOrganization } from '../services/api';
import { useMatchCalculation } from '../hooks/useMatchCalculation';
import EmployerWorkspaceSummary from '../components/EmployerWorkspaceSummary';

export default function HomeScreen({ navigation }) {
  const { profile, refreshProfile } = useProfile();
  const { t } = useTranslation();
  const { isRTL } = useLocalization();
  const insets = useSafeAreaInsets();

  const accountType = profile?.preferences?.account_type
    ? normalizeAccountType(profile.preferences.account_type)
    : null;
  const isEmployer = accountType === 'employer';

  const displayName =
    profile?.full_name?.trim() ||
    (isEmployer ? t('home.employerFallback', { defaultValue: 'Employer' }) : t('home.studentFallback'));

  const scrollViewRef = useRef(null);
  const createGateInFlightRef = useRef(false);
  const refreshInFlightRef = useRef(false);
  const employerRetryInFlightRef = useRef(false);
  const matchesRetryInFlightRef = useRef(false);
  useTabScroll('Home', scrollViewRef);
  useScrollToTop(scrollViewRef);
  const onScroll = useTabScrollReporter(20);

  const [matches, setMatches] = useState([]);
  const [matchesLoading, setMatchesLoading] = useState(false);
  const [matchesError, setMatchesError] = useState(null);
  const [refreshing, setRefreshing] = useState(false);

  // Employer workspace state
  const [employerOpportunities, setEmployerOpportunities] = useState([]);
  const [employerTotal, setEmployerTotal] = useState(0);
  const [employerLoading, setEmployerLoading] = useState(false);
  const [employerError, setEmployerError] = useState(null);
  const [createGateLoading, setCreateGateLoading] = useState(false);

  const handleCreateOpportunity = useCallback(async () => {
    if (createGateInFlightRef.current || createGateLoading) return;

    createGateInFlightRef.current = true;
    setCreateGateLoading(true);

    try {
      const organization = await getEmployerOrganization();

      if (organization.verification_status === 'verified') {
        navigation.navigate('CreateOpportunity');
        return;
      }

      navigation.navigate('EmployerVerification');
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        navigation.navigate('EmployerVerification');
        return;
      }

      console.warn('Failed to verify employer publication access:', err);

      Alert.alert(
        t('employerVerification.loadErrorTitle'),
        t('employerVerification.loadError')
      );
    } finally {
      createGateInFlightRef.current = false;
      setCreateGateLoading(false);
    }
  }, [createGateLoading, navigation, t]);


  const {
    isCalculating,
    progressPercent,
    calculationError,
    startCalculation,
    cancelCalculation,
  } = useMatchCalculation();
  const calculationErrorMessage = calculationError ? getLocalizedErrorMessage({ code: calculationError }, t) : null;
  const matchesErrorMessage = matchesError ? getLocalizedErrorMessage({ code: matchesError }, t) : null;

  const handleStopChecking = useCallback(() => {
    Alert.alert(
      t('home.calculation.stopConfirmTitle'),
      t('home.calculation.stopConfirmMessage'),
      [
        {
          text: t('home.calculation.keepChecking'),
          style: 'cancel',
        },
        {
          text: t('home.calculation.stop'),
          onPress: cancelCalculation,
        },
      ]
    );
  }, [cancelCalculation, t]);

  // Derived from real backend profile state
  const hasAnalyzedCV = Boolean(
    profile?.has_cv ||
      (profile?.skills && profile.skills.length > 0) ||
      (profile?.education && profile.education.length > 0) ||
      (profile?.experience && profile.experience.length > 0) ||
      (profile?.projects && profile.projects.length > 0)
  );

  const fetchMatchesData = useCallback(async () => {
    if (isEmployer || !hasAnalyzedCV) return;

    setMatchesLoading(true);
    setMatchesError(null);

    try {
      const res = await getMatches();
      setMatches(res.matches || []);
    } catch (err) {
      console.warn('Failed to load matches on Home:', err);
      const errorCode = 'MATCHES_LOAD_FAILED';
      setMatchesError(errorCode);
    } finally {
      setMatchesLoading(false);
    }
  }, [isEmployer, hasAnalyzedCV]);

  const fetchEmployerData = useCallback(async () => {
    if (!isEmployer) return;

    setEmployerLoading(true);
    setEmployerError(null);

    try {
      const res = await getEmployerInternships({ limit: 50 });
      const items = res.items || [];
      setEmployerOpportunities(items.slice(0, 5));
      const publishedCount = items.filter((i) => i.is_active !== false).length;
      setEmployerTotal(publishedCount);
    } catch (err) {
      console.warn('Failed to load employer data on Home:', err);
      setEmployerError('EMPLOYER_LOAD_FAILED');
    } finally {
      setEmployerLoading(false);
    }
  }, [isEmployer]);

  useEffect(() => {
    if (isEmployer) {
      fetchEmployerData();
    } else if (hasAnalyzedCV) {
      fetchMatchesData();
    }
  }, [isEmployer, hasAnalyzedCV, fetchEmployerData, fetchMatchesData]);

  const handleRefresh = async () => {
    if (refreshInFlightRef.current || refreshing) return;

    refreshInFlightRef.current = true;
    setRefreshing(true);

    try {
      await refreshProfile();
      if (isEmployer) {
        await fetchEmployerData();
      } else if (hasAnalyzedCV) {
        await fetchMatchesData();
      }
    } catch (err) {
      console.warn('Home refresh error:', err);
    } finally {
      refreshInFlightRef.current = false;
      setRefreshing(false);
    }
  };

  const handleEmployerRetry = async () => {
    if (employerRetryInFlightRef.current || employerLoading) return;

    employerRetryInFlightRef.current = true;

    try {
      await fetchEmployerData();
    } finally {
      employerRetryInFlightRef.current = false;
    }
  };

  const handleMatchesRetry = async () => {
    if (matchesRetryInFlightRef.current || matchesLoading) return;

    matchesRetryInFlightRef.current = true;

    try {
      await fetchMatchesData();
    } finally {
      matchesRetryInFlightRef.current = false;
    }
  };

  const handleStartCalculation = () => {
    startCalculation(() => {
      fetchMatchesData();
    });
  };

  const topMatches = matches.slice(0, 3);
  const firstMatch = topMatches[0];
  const remainingMatches = topMatches.slice(1);

  const bottomPadding = getTabScreenBottomPadding(insets.bottom);

  if (!profile) {
    return (
      <ScreenContainer edges={['top']}>
        <View style={styles.centerLoading}>
          <ActivityIndicator size="large" color={colors.accent || colors.teal} />
        </View>
      </ScreenContainer>
    );
  }

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
        {/* Sequence 1: Greeting */}
        <Reveal delay={0}>
          <View style={styles.headerBlock}>
            {isRTL ? (
              <View style={styles.greetingRowRTL}>
                <Text style={[styles.hello, styles.rtlText]}>
                  {t('home.greetingHello', { defaultValue: 'أهلاً' })},
                </Text>
                <View style={styles.nameIsolation}>
                  <Text
                    style={[styles.hello, styles.nameLTR]}
                    numberOfLines={1}
                    ellipsizeMode="tail"
                  >
                    {displayName}
                  </Text>
                </View>
                <Text style={styles.hello}>
                  {'\u{1F44B}'}
                </Text>
              </View>
            ) : (
              <View style={styles.greetingRowLTR}>
                <Text style={styles.hello} numberOfLines={2}>
                  {t('home.greeting', { name: displayName })} {'\u{1F44B}'}
                </Text>
              </View>
            )}
          </View>
        </Reveal>

        {isEmployer ? (
          <>
            {/* Sequence 2: Employer Recruiter Dashboard Hero Card */}
            <Reveal delay={motionTokens.stagger.fast}>
              <GlassSurface variant="card" style={styles.employerHeroCard}>
                <View style={[styles.employerHeroHeader, isRTL && styles.rowRTL]}>
                  <View style={styles.employerIconCircle}>
                    <Ionicons name="briefcase" size={24} color={colors.accentStrong || colors.tealDark} />
                  </View>
                  <View style={styles.employerHeroTitleBlock}>
                    <Text style={[styles.employerHeroEyebrow, isRTL && styles.rtlText]}>
                      {t('home.employer.eyebrow')}
                    </Text>
                    <Text style={[styles.employerHeroTitle, isRTL && styles.rtlText]}>
                      {t('home.employer.title')}
                    </Text>
                  </View>
                </View>
                <Text style={[styles.employerHeroDescription, isRTL && styles.rtlText]}>
                  {t('home.employer.description')}
                </Text>

                {/* Live Metric Stat Pill */}
                <View style={[styles.employerStatsRow, isRTL && styles.rowRTL]}>
                  <View style={[styles.employerStatBox, isRTL && styles.rowRTL]}>
                    <View style={styles.statDot} />
                    <Text style={styles.statCount}>{employerTotal}</Text>
                    <Text style={[styles.statLabel, isRTL && styles.rtlText]}>
                      {t('home.employer.publishedOpportunities', { defaultValue: 'Published Opportunities' })}
                    </Text>
                  </View>
                </View>

                <View style={styles.employerActions}>
                  <GradientButton
                    title={`+ ${t('home.employer.createOpportunity')}`}
                    color={colors.accent || colors.teal}
                    onPress={handleCreateOpportunity}
                    disabled={createGateLoading}
                    loading={createGateLoading}
                    style={styles.employerActionBtn}
                  />
                  <TouchableOpacity
                    style={[styles.employerProfileLink, isRTL && styles.rowRTL]}
                    onPress={() => navigation.navigate('MainTabs', { screen: 'Opportunities' })}
                    accessibilityRole="button"
                    accessibilityLabel={t('home.employer.viewOpportunities')}
                  >
                    <Text style={[styles.employerProfileLinkText, isRTL && styles.rtlText]}>
                      {t('home.employer.viewOpportunities')}
                    </Text>
                    <Ionicons
                      name={isRTL ? 'arrow-back' : 'arrow-forward'}
                      size={16}
                      color={colors.accentStrong || colors.tealDark}
                      style={[styles.browseIcon, isRTL && styles.browseIconRTL]}
                    />
                  </TouchableOpacity>
                </View>
              </GlassSurface>
            </Reveal>

            <Reveal delay={motionTokens.stagger.normal}>
              <EmployerWorkspaceSummary
                navigation={navigation}
                refreshKey={refreshing}
                isRTL={isRTL}
              />
            </Reveal>

            {/* Sequence 3: Employer Opportunities Overview */}
            <Reveal delay={motionTokens.stagger.normal}>
              {employerLoading && !refreshing && employerOpportunities.length === 0 && (
                <View style={styles.centerLoading}>
                  <ActivityIndicator size="small" color={colors.accent || colors.teal} />
                  <Text style={[styles.loadingText, isRTL && styles.rtlWriting]}>
                    {t('home.employer.loadingWorkspace')}
                  </Text>
                </View>
              )}

              {employerError && !employerLoading && (
                <Card style={styles.errorCard} padding="md">
                  <Ionicons name="alert-circle-outline" size={24} color={colors.danger || '#EF4444'} />
                  <Text style={[styles.errorText, isRTL && styles.rtlWriting]}>
                    {t('home.employer.errorLoading')}
                  </Text>
                  <TouchableOpacity
                    style={styles.retryBtn}
                    onPress={handleEmployerRetry}
                    disabled={employerLoading}
                    accessibilityRole="button"
                    accessibilityLabel={t('home.employer.retry')}
                    accessibilityState={{
                      disabled: employerLoading,
                      busy: employerLoading,
                    }}
                  >
                    <Text style={[styles.retryBtnText, isRTL && styles.rtlWriting]}>
                      {t('home.employer.retry')}
                    </Text>
                  </TouchableOpacity>
                </Card>
              )}

              {!employerLoading && !employerError && employerTotal === 0 && (
                <Card style={styles.emptyMatchesCard} padding="lg">
                  <Ionicons name="briefcase-outline" size={36} color={colors.accent || colors.teal} />
                  <Text style={[styles.emptyMatchesTitle, isRTL && styles.rtlWriting]}>
                    {t('home.employer.noOpportunitiesTitle')}
                  </Text>
                  <Text style={[styles.emptyMatchesSubtitle, isRTL && styles.rtlWriting]}>
                    {t('home.employer.noOpportunitiesSubtitle')}
                  </Text>
                  <GradientButton
                    title={`+ ${t('home.employer.createOpportunity')}`}
                    color={colors.accent || colors.teal}
                    onPress={handleCreateOpportunity}
                    disabled={createGateLoading}
                    loading={createGateLoading}
                    style={{ marginTop: spacing.lg, width: '100%' }}
                  />
                </Card>
              )}

              {!employerLoading && !employerError && employerOpportunities.length > 0 && (
                <>
                  <View style={[styles.sectionHeaderRow, isRTL && styles.rowRTL]}>
                    <Text style={[styles.sectionEyebrow, isRTL && styles.rtlText]}>
                      {t('home.employer.recentOpportunities')}
                    </Text>
                    {employerTotal > employerOpportunities.length && (
                      <TouchableOpacity
                        onPress={() => navigation.navigate('MainTabs', { screen: 'Opportunities' })}
                        hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
                        accessibilityRole="button"
                        accessibilityLabel={t('home.employer.viewAll', { total: employerTotal })}
                      >
                        <Text style={[styles.seeAllLink, isRTL && styles.rtlText]}>
                          {t('home.employer.viewAll', { total: employerTotal })}
                        </Text>
                      </TouchableOpacity>
                    )}
                  </View>

                  {employerOpportunities.map((opp) => (
                    <PressableCard
                      key={opp.id}
                      style={styles.employerOppCard}
                      padding="md"
                      onPress={() =>
                        navigation.navigate('EmployerApplicants', {
                          internshipId: opp.id,
                          title: opp.title,
                        })
                      }
                      accessibilityLabel={`${opp.title} at ${opp.company}`}
                    >
                      <View style={[styles.oppCardHeader, isRTL && styles.rowRTL]}>
                        <Text style={[styles.oppTitle, isRTL && styles.rtlText]} numberOfLines={1}>
                          {opp.title}
                        </Text>
                        <View style={[styles.badgesContainer, isRTL && styles.rowRTL]}>
                          <View
                            style={[
                              styles.statusBadge,
                              opp.is_active === false ? styles.closedBadge : styles.publishedBadge,
                            ]}
                          >
                            <View
                              style={[
                                styles.statusDot,
                                opp.is_active === false ? styles.closedDot : styles.publishedDot,
                              ]}
                            />
                            <Text
                              style={[
                                styles.statusBadgeText,
                                opp.is_active === false
                                  ? styles.closedBadgeText
                                  : styles.publishedBadgeText,
                              ]}
                            >
                              {opp.is_active === false
                                ? t('employerOpportunities.statusClosed', 'Closed')
                                : t('employerOpportunities.statusPublished', 'Published')}
                            </Text>
                          </View>
                          <View style={styles.workTypePill}>
                            <Text style={styles.workTypePillText}>{opp.work_type}</Text>
                          </View>
                        </View>
                      </View>
                      <Text style={[styles.oppMeta, isRTL && styles.rtlText]}>
                        {opp.company} {'\u00b7'} {opp.location}
                      </Text>
                      <View style={[styles.oppFooter, isRTL && styles.rowRTL]}>
                        <TouchableOpacity
                          style={[styles.viewApplicantsBtn, isRTL && styles.rowRTL]}
                          onPress={() =>
                            navigation.navigate('EmployerApplicants', {
                              internshipId: opp.id,
                              title: opp.title,
                            })
                          }
                          accessibilityRole="button"
                          accessibilityLabel={`${t('home.employer.viewApplicants')} for ${opp.title}`}
                        >
                          <Text style={[styles.viewApplicantsBtnText, isRTL && styles.rtlText]}>
                            {t('home.employer.viewApplicants')}
                          </Text>
                          <Ionicons
                            name={isRTL ? 'arrow-back' : 'arrow-forward'}
                            size={14}
                            color={colors.accentStrong || colors.tealDark}
                            style={[styles.browseIcon, isRTL && styles.browseIconRTL]}
                          />
                        </TouchableOpacity>
                      </View>
                    </PressableCard>
                  ))}
                </>
              )}
            </Reveal>
          </>
        ) : (
          <>
            {/* Sequence 2: Signature Match Intelligence Hero Orb */}
            <Reveal delay={motionTokens.stagger.fast}>

              <MatchIntelligenceOrb
                score={firstMatch?.overall_score}
                topMatch={firstMatch}
                hasAnalyzedCV={hasAnalyzedCV}
                isCalculating={isCalculating}
                progressPercent={progressPercent}
              />
            </Reveal>

            {!hasAnalyzedCV ? (
          <>
            {/* Sequence 3: Upload CV Prompt Card */}
            <Reveal delay={motionTokens.stagger.normal}>
              <Card style={styles.uploadCard} padding="lg">
                <View style={styles.uploadIconCircle}>
                  <Ionicons name="arrow-up" size={22} color={colors.accent || colors.teal} />
                </View>
                <Text style={[styles.uploadTitle, isRTL && styles.rtlWriting]}>{t('home.upload.title')}</Text>
                <Text style={[styles.uploadSubtitle, isRTL && styles.rtlWriting]}>
                  {t('home.upload.subtitle')}
                </Text>
                <GradientButton
                  title={t('home.upload.button')}
                  color={colors.accent || colors.teal}
                  onPress={() => navigation.navigate('CVUpload', { origin: 'Home' })}
                  style={{ marginTop: spacing.lg, width: '100%' }}
                />
              </Card>
            </Reveal>

            {/* Sequence 4: Recommendation browsing card */}
            <Reveal delay={motionTokens.stagger.slow}>
              <Text style={[styles.sectionEyebrow, isRTL && styles.rtlText]}>{t('home.recommendations.eyebrow')}</Text>
              <Card style={styles.infoCard} padding="md">
                <Text style={[styles.infoTitle, isRTL && styles.rtlText]}>{t('home.recommendations.title')}</Text>
                <Text style={[styles.infoSubtitle, isRTL && styles.rtlText]}>
                  {t('home.recommendations.subtitle')}
                </Text>
                <TouchableOpacity
                  style={[styles.browseButton, isRTL && styles.rowRTL]}
                  onPress={() => navigation.navigate('MainTabs', { screen: 'Internships' })}
                  accessibilityRole="button"
                  accessibilityLabel={t('home.recommendations.explore')}
                >
                  <Text style={[styles.browseButtonText, isRTL && styles.rtlText]}>{t('home.recommendations.explore')}</Text>
                  <Ionicons
                    name={isRTL ? 'arrow-back' : 'arrow-forward'}
                    size={16}
                    color={colors.accentStrong || colors.tealDark}
                    style={[styles.browseIcon, isRTL && styles.browseIconRTL]}
                  />
                </TouchableOpacity>
              </Card>
            </Reveal>
          </>
        ) : (
          <>
            {/* Sequence 3: CV Analyzed Status Card */}
            <Reveal delay={motionTokens.stagger.normal}>
              <Card style={styles.statusCard} padding="md">
                <Text style={[styles.statusLabel, isRTL && styles.rtlText]}>{t('home.cvStatus.eyebrow')}</Text>
                <Text style={[styles.statusTitle, isRTL && styles.rtlText]}>{t('home.cvStatus.analyzed')}</Text>
                <View style={[styles.statusFileRow, isRTL && styles.rowRTL]}>
                  <Text style={[styles.statusFileName, isRTL && styles.rtlText]}>{t('home.cvStatus.document')}</Text>
                  <TouchableOpacity
                    onPress={() => navigation.navigate('CVUpload', { origin: 'Home' })}
                    hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
                    accessibilityRole="button"
                    accessibilityLabel={t('home.cvStatus.reloadA11y')}
                  >
                    <Text style={[styles.reloadLink, isRTL && styles.rtlText]}>{t('home.cvStatus.reload')}</Text>
                  </TouchableOpacity>
                </View>
              </Card>
            </Reveal>

            {/* Sequence 4: Today's Matchups Section */}
            <Reveal delay={motionTokens.stagger.slow}>
              <View style={[styles.sectionHeaderRow, isRTL && styles.rowRTL]}>
                <Text style={[styles.sectionEyebrow, isRTL && styles.rtlText]}>{t('home.matchups.eyebrow')}</Text>
                {matches.length > 3 ? (
                  <TouchableOpacity
                    onPress={() => navigation.navigate('MainTabs', { screen: 'Matchups' })}
                    hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
                    accessibilityRole="button"
                    accessibilityLabel={t('home.matchups.seeAllA11y', { total: matches.length })}
                  >
                    <Text style={[styles.seeAllLink, isRTL && styles.rtlText]}>{t('home.matchups.seeAll', { total: matches.length })}</Text>
                  </TouchableOpacity>
                ) : null}
              </View>

              {/* Calculating State with Ambient AIPulse */}
              {isCalculating && (
                <AIPulse active={isCalculating} style={styles.calculatingPulseWrap}>
                  <Card style={styles.calculatingCard} padding="md">
                    <ActivityIndicator size="small" color={colors.accent || colors.teal} />
                    <Text style={[styles.calculatingTitle, isRTL && styles.rtlWriting]}>{t('home.calculation.finding')}</Text>
                    <Text style={[styles.calculatingSubtitle, isRTL && styles.rtlWriting]}>
                      {t('home.calculation.evaluating', { progress: progressPercent })}
                    </Text>
                    <View style={styles.progressTrack}>
                      <View style={[styles.progressFill, { width: `${progressPercent}%` }]} />
                    </View>
                    <TouchableOpacity
                      style={styles.cancelCalcBtn}
                      onPress={handleStopChecking}
                      accessibilityRole="button"
                      accessibilityLabel={t('home.calculation.stop')}
                    >
                      <Text style={[styles.cancelCalcText, isRTL && styles.rtlWriting]}>{t('home.calculation.stop')}</Text>
                    </TouchableOpacity>
                  </Card>
                </AIPulse>
              )}

              {/* Calculation Error */}
              {calculationError && (
                <Card style={styles.errorCard} padding="md">
                  <Ionicons name="alert-circle-outline" size={24} color={colors.danger || '#EF4444'} />
                  <Text style={[styles.errorText, isRTL && styles.rtlWriting]}>{calculationErrorMessage}</Text>
                  <TouchableOpacity
                    style={styles.retryBtn}
                    onPress={handleStartCalculation}
                    accessibilityRole="button"
                    accessibilityLabel={t('home.calculation.tryAgain')}
                  >
                    <Text style={[styles.retryBtnText, isRTL && styles.rtlWriting]}>{t('home.calculation.tryAgain')}</Text>
                  </TouchableOpacity>
                </Card>
              )}

              {/* Loading Matches */}
              {matchesLoading && !isCalculating && (
                <View style={styles.centerLoading}>
                  <ActivityIndicator size="small" color={colors.accent || colors.teal} />
                  <Text style={[styles.loadingText, isRTL && styles.rtlWriting]}>{t('home.matches.loading')}</Text>
                </View>
              )}

              {/* Matches Error */}
              {matchesError && !matchesLoading && !isCalculating && (
                <Card style={styles.errorCard} padding="md">
                  <Ionicons name="alert-circle-outline" size={24} color={colors.danger || '#EF4444'} />
                  <Text style={[styles.errorText, isRTL && styles.rtlWriting]}>{matchesErrorMessage}</Text>
                  <TouchableOpacity
                    style={styles.retryBtn}
                    onPress={handleMatchesRetry}
                    disabled={matchesLoading}
                    accessibilityRole="button"
                    accessibilityLabel={t('home.matches.retry')}
                    accessibilityState={{
                      disabled: matchesLoading,
                      busy: matchesLoading,
                    }}
                  >
                    <Text style={[styles.retryBtnText, isRTL && styles.rtlWriting]}>{t('home.matches.retry')}</Text>
                  </TouchableOpacity>
                </Card>
              )}

              {/* Empty Matches State */}
              {!matchesLoading && !isCalculating && !matchesError && matches.length === 0 && (
                <Card style={styles.emptyMatchesCard} padding="lg">
                  <Ionicons name="sparkles-outline" size={36} color={colors.accent || colors.teal} />
                  <Text style={[styles.emptyMatchesTitle, isRTL && styles.rtlWriting]}>{t('home.matches.emptyTitle')}</Text>
                  <Text style={[styles.emptyMatchesSubtitle, isRTL && styles.rtlWriting]}>
                    {t('home.matches.emptySubtitle')}
                  </Text>
                  <GradientButton
                    title={t('home.matches.find')}
                    color={colors.accent || colors.teal}
                    onPress={handleStartCalculation}
                    style={{ marginTop: spacing.lg, width: '100%' }}
                  />
                </Card>
              )}

              {/* Populated Top Matches */}
              {!matchesLoading && !isCalculating && topMatches.length > 0 && (
                <>
                  {/* Highlight First Match */}
                  {firstMatch && (
                    <Card variant="highlight" style={styles.highlightCard} padding="md">
                      <PressableScale
                        onPress={() =>
                          navigation.navigate('InternshipDetail', {
                            internshipId: firstMatch.internship.id,
                          })
                        }
                        scaleTo={0.985}
                        activeOpacity={0.85}
                        accessibilityRole="button"
                        accessibilityLabel={t('home.matches.internshipAtCompany', { title: firstMatch.internship.title, company: firstMatch.internship.company })}
                      >
                        <View style={[styles.highlightTop, isRTL && styles.rowRTL]}>
                          <Ionicons name="flame" size={16} color="#F2812B" style={[styles.flameIcon, isRTL && styles.flameIconRTL]} />
                          <Text style={[styles.highlightTitle, isRTL && styles.highlightTitleRTL]}>{firstMatch.internship.title}</Text>
                          <MatchBadge score={firstMatch.overall_score} />
                        </View>
                        <Text style={styles.highlightMeta}>
                          {firstMatch.internship.company} {'\u00b7'} {firstMatch.internship.location}
                        </Text>
                      </PressableScale>

                      <PressableScale
                        style={[styles.whyLinkWrap, isRTL && styles.rowRTL]}
                        onPress={() =>
                          navigation.navigate('WhyYouMatch', {
                            matchId: firstMatch.match_id,
                            internshipId: firstMatch.internship.id,
                          })
                        }
                        scaleTo={0.98}
                        activeOpacity={0.8}
                        accessibilityRole="button"
                        accessibilityLabel={t('home.matches.whyA11y')}
                      >
                        <Text style={[styles.whyLink, isRTL && styles.rtlText]}>{t('home.matches.why')}</Text>
                        <Ionicons
                          name={isRTL ? 'chevron-back' : 'chevron-forward'}
                          size={14}
                          color={colors.primaryBlue}
                          style={[styles.chevronIcon, isRTL && styles.chevronIconRTL]}
                        />
                      </PressableScale>
                    </Card>
                  )}

                  {/* Remaining Top Matches */}
                  {remainingMatches.map((item, index) => (
                    <PressableCard
                      key={item.match_id}
                      style={[
                        styles.plainRowCard,
                        index === remainingMatches.length - 1 && { marginBottom: spacing.md },
                      ]}
                      padding="sm"
                      onPress={() =>
                        navigation.navigate('InternshipDetail', {
                          internshipId: item.internship.id,
                        })
                      }
                      accessibilityLabel={t('home.matches.internshipAtCompany', { title: item.internship.title, company: item.internship.company })}
                    >
                      <View style={[styles.plainRow, isRTL && styles.rowRTL]}>
                        <View style={[styles.plainRowMain, isRTL && styles.plainRowMainRTL]}>
                          <Text style={styles.plainTitle}>{item.internship.title}</Text>
                          <Text style={styles.plainMeta}>
                            {item.internship.company} {'\u00b7'} {item.internship.location}
                          </Text>
                        </View>
                        <MatchBadge score={item.overall_score} />
                      </View>
                    </PressableCard>
                  ))}

                  {matches.length > 3 && (
                    <TouchableOpacity
                      style={[styles.viewAllMatchupsBtn, isRTL && styles.rowRTL]}
                      onPress={() => navigation.navigate('MainTabs', { screen: 'Matchups' })}
                      accessibilityRole="button"
                      accessibilityLabel={t('home.matches.viewAll', { total: matches.length })}
                    >
                      <Text style={[styles.viewAllMatchupsText, isRTL && styles.rtlText]}>{t('home.matches.viewAll', { total: matches.length })}</Text>
                      <Ionicons
                        name={isRTL ? 'arrow-back' : 'arrow-forward'}
                        size={16}
                        color={colors.accentStrong || colors.tealDark}
                        style={[styles.arrowIcon, isRTL && styles.arrowIconRTL]}
                      />
                    </TouchableOpacity>
                  )}
                </>
              )}
            </Reveal>
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
    paddingTop: spacing.xs,
    paddingBottom: 128,
  },
  headerBlock: {
    marginBottom: spacing.md,
    paddingTop: spacing.sm,
  },
  hello: {
    ...typography.display,
    color: colors.textPrimary || colors.textDark,
  },
  uploadCard: {
    alignItems: 'center',
    marginBottom: spacing.xl,
  },
  uploadIconCircle: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: colors.accentSoft || '#E6F4F6',
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: spacing.md,
  },
  uploadTitle: {
    ...typography.cardTitle,
    color: colors.textPrimary || colors.textDark,
    textAlign: 'center',
  },
  uploadSubtitle: {
    ...typography.caption,
    color: colors.textSecondary || colors.textMuted,
    textAlign: 'center',
    marginTop: spacing.xs,
    lineHeight: 18,
  },
  sectionEyebrow: {
    ...typography.eyebrow,
    color: colors.textSecondary || colors.textMuted,
    letterSpacing: 0.6,
  },
  sectionHeaderRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: spacing.md,
    marginBottom: spacing.sm,
  },
  seeAllLink: {
    ...typography.caption,
    color: colors.accentStrong || colors.tealDark,
    fontWeight: '600',
  },
  infoCard: {
    marginTop: spacing.sm,
  },
  infoTitle: {
    ...typography.cardTitle,
    color: colors.textPrimary || colors.textDark,
  },
  infoSubtitle: {
    ...typography.caption,
    color: colors.textSecondary || colors.textMuted,
    marginTop: spacing.xs,
    lineHeight: 18,
  },
  browseButton: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: spacing.md,
    minHeight: spacing.minimumTouchTarget,
  },
  browseButtonText: {
    ...typography.button,
    color: colors.accentStrong || colors.tealDark,
    fontSize: 13,
  },
  browseIcon: {
    marginStart: spacing.xs,
  },
  statusCard: {
    marginBottom: spacing.md,
  },
  statusLabel: {
    ...typography.eyebrow,
    color: colors.accentStrong || colors.tealDark,
  },
  statusTitle: {
    ...typography.cardTitle,
    color: colors.textPrimary || colors.textDark,
    marginTop: spacing.xs,
  },
  statusFileRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: spacing.sm,
    paddingTop: spacing.xs,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.borderSubtle || colors.border,
  },
  statusFileName: {
    ...typography.caption,
    color: colors.textSecondary || colors.textMuted,
  },
  reloadLink: {
    ...typography.caption,
    fontWeight: '600',
    color: colors.accent || colors.teal,
  },
  calculatingPulseWrap: {
    marginBottom: spacing.md,
  },
  calculatingCard: {
    alignItems: 'center',
  },
  calculatingTitle: {
    ...typography.cardTitle,
    color: colors.textPrimary || colors.textDark,
    marginTop: spacing.sm,
  },
  calculatingSubtitle: {
    ...typography.caption,
    color: colors.textSecondary || colors.textMuted,
    marginTop: spacing.xs,
    textAlign: 'center',
  },
  progressTrack: {
    width: '100%',
    height: 6,
    borderRadius: 3,
    backgroundColor: colors.borderSubtle || '#E2E8F0',
    overflow: 'hidden',
    marginTop: spacing.md,
  },
  progressFill: {
    height: 6,
    backgroundColor: colors.accent || colors.teal,
  },
  cancelCalcBtn: {
    marginTop: spacing.md,
    minHeight: spacing.minimumTouchTarget,
    justifyContent: 'center',
  },
  cancelCalcText: {
    ...typography.caption,
    color: colors.textSecondary || colors.textMuted,
    textDecorationLine: 'underline',
  },
  errorCard: {
    alignItems: 'center',
    marginBottom: spacing.md,
    borderColor: colors.dangerSoft || '#FEE2E2',
    backgroundColor: '#FEF2F2',
  },
  errorText: {
    ...typography.caption,
    color: colors.danger || '#EF4444',
    textAlign: 'center',
    marginTop: spacing.xs,
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
  centerLoading: {
    alignItems: 'center',
    paddingVertical: spacing.xl,
  },
  loadingText: {
    ...typography.caption,
    color: colors.textSecondary || colors.textMuted,
    marginTop: spacing.sm,
  },
  emptyMatchesCard: {
    alignItems: 'center',
    marginTop: spacing.sm,
  },
  emptyMatchesTitle: {
    ...typography.cardTitle,
    color: colors.textPrimary || colors.textDark,
    marginTop: spacing.sm,
  },
  emptyMatchesSubtitle: {
    ...typography.caption,
    color: colors.textSecondary || colors.textMuted,
    textAlign: 'center',
    marginTop: spacing.xs,
    lineHeight: 18,
  },
  highlightCard: {
    marginBottom: spacing.md,
  },
  highlightTop: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  flameIcon: {
    marginEnd: spacing.xs,
  },
  highlightTitle: {
    flex: 1,
    ...typography.cardTitle,
    color: colors.textPrimary || colors.textDark,
    marginEnd: spacing.sm,
  },
  highlightMeta: {
    ...typography.caption,
    color: colors.textSecondary || colors.textMuted,
    marginTop: spacing.xs,
  },
  whyLinkWrap: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: spacing.md,
    paddingTop: spacing.sm,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.borderSubtle || colors.border,
    minHeight: spacing.minimumTouchTarget,
  },
  whyLink: {
    ...typography.bodyEmphasis,
    color: colors.info || colors.primaryBlue,
    fontSize: 13,
  },
  chevronIcon: {
    marginStart: spacing.xxs,
  },
  plainRowCard: {
    marginBottom: spacing.sm,
  },
  plainRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: spacing.xs,
    minHeight: spacing.minimumTouchTarget,
  },
  plainRowMain: {
    flex: 1,
    marginEnd: spacing.md,
  },
  plainTitle: {
    ...typography.cardTitle,
    fontSize: 14,
    color: colors.textPrimary || colors.textDark,
  },
  plainMeta: {
    ...typography.caption,
    color: colors.textSecondary || colors.textMuted,
    marginTop: spacing.xxs,
  },
  viewAllMatchupsBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: spacing.md,
    marginTop: spacing.xs,
    minHeight: spacing.minimumTouchTarget,
  },
  viewAllMatchupsText: {
    ...typography.button,
    color: colors.accentStrong || colors.tealDark,
    fontSize: 13,
  },
  arrowIcon: {
    marginStart: spacing.xs,
  },
  rtlWriting: {
    writingDirection: 'rtl',
  },
  rowRTL: {
    flexDirection: 'row-reverse',
  },
  rtlText: {
    writingDirection: 'rtl',
    textAlign: 'right',
  },
  browseIconRTL: {
    marginStart: 0,
    marginEnd: spacing.xs,
  },
  flameIconRTL: {
    marginEnd: 0,
    marginStart: spacing.xs,
  },
  highlightTitleRTL: {
    marginEnd: 0,
    marginStart: spacing.sm,
  },
  chevronIconRTL: {
    marginStart: 0,
    marginEnd: spacing.xxs,
  },
  plainRowMainRTL: {
    marginEnd: 0,
    marginStart: spacing.md,
  },
  arrowIconRTL: {
    marginStart: 0,
    marginEnd: spacing.xs,
  },
  greetingRowRTL: {
    flexDirection: 'row-reverse',
    alignItems: 'center',
    justifyContent: 'flex-end',
    flexWrap: 'wrap',
    columnGap: spacing.xs,
  },
  greetingRowLTR: {
    flexDirection: 'row',
    alignItems: 'center',
    flexWrap: 'wrap',
  },
  nameIsolation: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  nameLTR: {
    writingDirection: 'ltr',
    textAlign: 'left',
  },
  employerHeroCard: {
    padding: spacing.lg,
    borderRadius: spacing.radii.card || spacing.radii.lg,
    marginBottom: spacing.lg,
  },
  employerHeroHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: spacing.md,
  },
  employerIconCircle: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: colors.accentSoft || '#E6F4F6',
    alignItems: 'center',
    justifyContent: 'center',
    marginEnd: spacing.md,
  },
  employerHeroTitleBlock: {
    flex: 1,
  },
  employerHeroEyebrow: {
    ...typography.eyebrow,
    color: colors.accentStrong || colors.tealDark,
    letterSpacing: 0.6,
  },
  employerHeroTitle: {
    ...typography.cardTitle,
    fontSize: 18,
    color: colors.textPrimary || colors.textDark,
    marginTop: spacing.xxs,
  },
  employerHeroDescription: {
    ...typography.bodySecondary,
    color: colors.textSecondary || colors.textMuted,
    fontSize: 13,
    lineHeight: 19,
    marginBottom: spacing.lg,
  },
  employerActions: {
    gap: spacing.sm,
  },
  employerActionBtn: {
    width: '100%',
  },
  employerProfileLink: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: spacing.sm,
    minHeight: spacing.minimumTouchTarget,
  },
  employerProfileLinkText: {
    ...typography.button,
    color: colors.accentStrong || colors.tealDark,
    fontSize: 13,
  },
  employerStatsRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: spacing.md,
  },
  employerStatBox: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(14, 116, 144, 0.08)',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs + 2,
    borderRadius: spacing.radii.pill,
  },
  statDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: colors.success || '#10B981',
    marginEnd: spacing.xs,
  },
  statCount: {
    ...typography.label,
    fontWeight: '700',
    color: colors.accentStrong || colors.tealDark,
    fontSize: 14,
    marginEnd: spacing.xs,
  },
  statLabel: {
    ...typography.caption,
    color: colors.textSecondary || colors.textMuted,
    fontSize: 12,
  },
  employerOppCard: {
    marginBottom: spacing.sm,
  },
  oppCardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: spacing.xxs,
  },
  oppTitle: {
    flex: 1,
    ...typography.cardTitle,
    fontSize: 15,
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
  workTypePill: {
    backgroundColor: colors.accentSoft || '#E6F4F6',
    paddingHorizontal: spacing.sm,
    paddingVertical: 2,
    borderRadius: spacing.radii.pill,
  },
  workTypePillText: {
    ...typography.badge,
    fontSize: 11,
    color: colors.accentStrong || colors.tealDark,
    textTransform: 'capitalize',
  },
  oppMeta: {
    ...typography.caption,
    color: colors.textSecondary || colors.textMuted,
    marginBottom: spacing.sm,
  },
  oppFooter: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    alignItems: 'center',
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.borderSubtle || colors.border,
    paddingTop: spacing.xs,
  },
  viewApplicantsBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    minHeight: spacing.minimumTouchTarget,
    paddingVertical: spacing.xxs,
  },
  viewApplicantsBtnText: {
    ...typography.button,
    color: colors.accentStrong || colors.tealDark,
    fontSize: 13,
  },
});
