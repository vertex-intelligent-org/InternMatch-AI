import React, { useEffect, useState, useCallback, useRef } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  TextInput,
  ActivityIndicator,
  RefreshControl,
  Alert,
  KeyboardAvoidingView,
  Platform,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTranslation } from 'react-i18next';
import colors from '../theme/colors';
import { spacing } from '../theme/spacing';
import { typography } from '../theme/typography';
import ScreenContainer from '../components/ScreenContainer';
import ScreenHeader from '../components/ScreenHeader';
import Card from '../components/Card';
import PressableScale from '../components/PressableScale';
import {
  getApplicationDetail,
  generateInterviewPrep,
  updateApplicationStatus,
  ApiError,
} from '../services/api';
import haptics from '../services/haptics';
import { useLocalization } from '../localization/LocalizationContext';
import { formatLocalizedDate, formatLocalizedDateTime } from '../localization/formatters';
import useSmoothAIProgress from '../hooks/useSmoothAIProgress';
import { useSubscription } from '../context/SubscriptionProvider';

const CANONICAL_STATUSES = [
  'saved',
  'applied',
  'interviewing',
  'rejected',
  'accepted',
];

const STATUS_CONFIG = {
  saved: {
    bg: colors.surfaceMuted || '#F1F5F9',
    fg: colors.textSecondary || '#475569',
    icon: 'bookmark-outline',
  },
  applied: {
    bg: colors.infoSoft || '#E0F2FE',
    fg: colors.info || '#0284C7',
    icon: 'send-outline',
  },
  interviewing: {
    bg: colors.warningSoft || '#FEF3C7',
    fg: colors.warning || '#D97706',
    icon: 'chatbubbles-outline',
  },
  rejected: {
    bg: colors.dangerSoft || '#FEE2E2',
    fg: colors.danger || '#DC2626',
    icon: 'close-circle-outline',
  },
  accepted: {
    bg: colors.successSoft || '#DCFCE7',
    fg: colors.success || '#16A34A',
    icon: 'checkmark-circle-outline',
  },
};

function StatusPill({ status }) {
  const { t } = useTranslation();
  const config = STATUS_CONFIG[status] || STATUS_CONFIG.saved;
  const label = t(`applications.statuses.${status}`, { defaultValue: status });
  return (
    <View style={[styles.statusPill, { backgroundColor: config.bg }]}>
      <Ionicons
        name={config.icon}
        size={12}
        color={config.fg}
        style={styles.pillIcon}
      />
      <Text style={[styles.statusPillText, { color: config.fg }]}>
        {label}
      </Text>
    </View>
  );
}

export default function ApplicationDetailScreen({ route, navigation }) {
  const { t } = useTranslation();
  const {
    refreshAIUsage,
  } = useSubscription();
  const { locale } = useLocalization();
  const applicationId =
    route?.params?.applicationId ||
    route?.params?.id ||
    route?.params?.application?.id;

  const [detail, setDetail] = useState(null);
  const [interviewPrep, setInterviewPrep] = useState(null);
  const [interviewPrepLoading, setInterviewPrepLoading] = useState(false);
  const [interviewPrepError, setInterviewPrepError] = useState(false);

  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(null);
  const [isNotFound, setIsNotFound] = useState(false);

  // Status mutation state
  const [mutatingStatus, setMutatingStatus] = useState(false);

  // Notes editing state
  const [notesText, setNotesText] = useState('');
  const [isEditingNotes, setIsEditingNotes] = useState(false);
  const [savingNotes, setSavingNotes] = useState(false);
  const requestGenerationRef = useRef(0);
  const mutationLockRef = useRef(false);

  const fetchDetail = useCallback(async (isRefresh = false) => {
    const generation = ++requestGenerationRef.current;
    if (!applicationId) {
      setIsNotFound(true);
      setLoading(false);
      return;
    }

    if (!isRefresh) {
      setLoading(true);
    }
    setError(null);
    setIsNotFound(false);

    try {
      const data = await getApplicationDetail(applicationId);
      if (generation !== requestGenerationRef.current) return;
      setDetail(data);
      setNotesText(data.notes || '');
    } catch (err) {
      if (generation !== requestGenerationRef.current) return;
      if (err instanceof ApiError && err.status === 404) {
        setIsNotFound(true);
      } else {
        console.warn('Failed to fetch application detail:', err);
        setError('APPLICATION_LOAD_FAILED');
      }
    } finally {
      if (generation !== requestGenerationRef.current) return;
      setLoading(false);
      setRefreshing(false);
    }
  }, [applicationId]);

  useEffect(() => {
    fetchDetail();
    return () => {
      requestGenerationRef.current += 1;
    };
  }, [fetchDetail]);

  const handleRefresh = async () => {
    if (mutationLockRef.current) return;
    setRefreshing(true);
    await fetchDetail(true);
  };


  const handleSaveNotes = async () => {
    if (!detail || !applicationId || savingNotes || mutatingStatus || refreshing || loading || mutationLockRef.current) return;

    setSavingNotes(true);
    mutationLockRef.current = true;
    requestGenerationRef.current += 1;
    try {
      const trimmedNotes = notesText.trim();
      await updateApplicationStatus(applicationId, {
        status: detail.status,
        notes: trimmedNotes.length > 0 ? trimmedNotes : null,
      });
      haptics.success();
      setIsEditingNotes(false);
      // Refetch authoritative server state
      await fetchDetail(true);
    } catch (err) {
      haptics.error();
      console.warn('Failed to save notes:', err);
      Alert.alert(
        t('applicationDetail.notesUpdateFailedTitle', { defaultValue: t('common.error') }),
        t('errors.applicationNotesSaveFailed')
      );
    } finally {
      mutationLockRef.current = false;
      setSavingNotes(false);
    }
  };

  const formatEventDate = (isoString) => {
    if (!isoString) return '';
    return formatLocalizedDateTime(isoString, locale);
  };

  const formatAppliedDate = (dateString) => {
    if (!dateString) return null;
    return formatLocalizedDate(dateString, locale);
  };


  const interviewPrepProgress =
    useSmoothAIProgress(
      interviewPrepLoading,
      8,
      94,
      22000
    );

  const handleGenerateInterviewPrep = async () => {
    if (!applicationId || interviewPrepLoading) {
      return;
    }

    setInterviewPrepLoading(true);
    setInterviewPrepError(false);

    try {
      const result = await generateInterviewPrep(
        applicationId,
        locale
      );

      setInterviewPrep(result);

      refreshAIUsage().catch(
        (usageError) => {
          console.warn(
            'AI usage refresh after interview prep failed:',
            usageError
          );
        }
      );

      haptics.success();
    } catch (err) {
      if (
        err instanceof ApiError &&
        err.status === 402 &&
        err.code === 'AI_QUOTA_EXCEEDED'
      ) {
        refreshAIUsage().catch(
          (usageError) => {
            console.warn(
              'AI usage refresh after interview prep quota response failed:',
              usageError
            );
          }
        );

        navigation.navigate('Plans');
        return;
      }

      console.warn(
        'Failed to generate interview prep:',
        err
      );
      setInterviewPrepError(true);
      haptics.error();
    } finally {
      setInterviewPrepLoading(false);
    }
  };


  return (
    <ScreenContainer edges={['top', 'bottom']}>
      <ScreenHeader
        title={t('applicationDetail.title')}
        showBack={true}
        navigation={navigation}
      />

      <KeyboardAvoidingView
        style={styles.container}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        <ScrollView
          style={styles.scrollView}
          contentContainerStyle={styles.content}
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
          {/* Loading State */}
          {loading && !refreshing && (
            <View style={styles.centerContainer}>
              <ActivityIndicator
                size="large"
                color={colors.accent || colors.teal}
              />
              <Text style={styles.loadingText}>{t('applicationDetail.loading')}</Text>
            </View>
          )}

          {/* 404 Not Found State */}
          {!loading && isNotFound && (
            <Card style={styles.notFoundCard} padding="lg">
              <Ionicons
                name="alert-circle-outline"
                size={44}
                color={colors.danger || '#EF4444'}
              />
              <Text style={styles.notFoundTitle}>{t('applicationDetail.notFoundTitle')}</Text>
              <Text style={styles.notFoundSubtitle}>
                {t('applicationDetail.notFoundMessage')}
              </Text>
              <TouchableOpacity
                style={styles.backBtn}
                onPress={() => navigation.goBack()}
                accessibilityRole="button"
                accessibilityLabel={t('applicationDetail.backToApplications')}
              >
                <Text style={styles.backBtnText}>{t('applicationDetail.backToApplications')}</Text>
              </TouchableOpacity>
            </Card>
          )}

          {/* Error State */}
          {!loading && !isNotFound && error && (
            <Card style={styles.errorCard} padding="lg">
              <Ionicons
                name="cloud-offline-outline"
                size={40}
                color={colors.danger || '#EF4444'}
              />
              <Text style={styles.errorTitle}>{t('applicationDetail.errorTitle')}</Text>
              <Text style={styles.errorSubtitle}>
                {t('errors.applicationLoadFailed', { defaultValue: t('applicationDetail.errorSubtitle', { defaultValue: t('applicationDetail.errorTitle') }) })}
              </Text>
              <TouchableOpacity
                style={styles.retryBtn}
                onPress={() => fetchDetail()}
                accessibilityRole="button"
                accessibilityLabel={t('common.tryAgain')}
              >
                <Text style={styles.retryBtnText}>{t('common.tryAgain')}</Text>
              </TouchableOpacity>
            </Card>
          )}

          {/* Populated Application Detail */}
          {!loading && !isNotFound && !error && detail && (
            <>
              {/* Hero Information Card */}
              <Card style={styles.heroCard} padding="lg">
                <View style={styles.heroHeader}>
                  <View style={styles.heroTitleWrap}>
                    <Text style={styles.jobTitle}>
                      {detail.job_title || t('applications.defaultJobTitle')}
                    </Text>
                    {detail.company_name ? (
                      <View style={styles.companyRow}>
                        <Ionicons
                          name="business-outline"
                          size={14}
                          color={colors.textSecondary || colors.textMuted}
                          style={styles.companyIcon}
                        />
                        <Text style={styles.companyName}>
                          {detail.company_name}
                        </Text>
                      </View>
                    ) : null}
                  </View>
                  <StatusPill status={detail.status} />
                </View>

                {/* Applied Date Banner if present */}
                {detail.applied_date ? (
                  <View style={styles.appliedDateBanner}>
                    <Ionicons
                      name="calendar"
                      size={14}
                      color={colors.info || '#0284C7'}
                      style={styles.appliedIcon}
                    />
                    <Text style={styles.appliedDateText}>
                      {t('applications.appliedDate', { date: formatAppliedDate(detail.applied_date) })}
                    </Text>
                  </View>
                ) : null}

                {/* Shortcut Actions Row */}
                <View style={styles.shortcutsRow}>
                  {detail.generated_cover_letter ? (
                    <PressableScale
                      style={styles.shortcutBtnPrimary}
                      onPress={() =>
                        navigation.navigate('CoverLetter', {
                          applicationId: detail.id,
                          draft: detail.generated_cover_letter,
                          currentStatus: detail.status,
                          internshipId: detail.internship_id,
                          companyName: detail.company_name,
                          jobTitle: detail.job_title,
                        })
                      }
                      accessibilityRole="button"
                      accessibilityLabel={t('applications.coverLetterBtn')}
                    >
                      <Ionicons
                        name="document-text"
                        size={15}
                        color={colors.accentStrong || colors.tealDark}
                        style={styles.shortcutIcon}
                      />
                      <Text style={styles.shortcutBtnTextPrimary}>
                        {t('applications.coverLetterBtn')}
                      </Text>
                    </PressableScale>
                  ) : null}

                  {detail.internship_id ? (
                    <PressableScale
                      style={styles.shortcutBtnSecondary}
                      onPress={() =>
                        navigation.navigate('InternshipDetail', {
                          internshipId: detail.internship_id,
                        })
                      }
                      accessibilityRole="button"
                      accessibilityLabel={t('applications.listingBtn')}
                    >
                      <Ionicons
                        name="open-outline"
                        size={15}
                        color={colors.textPrimary || colors.textDark}
                        style={styles.shortcutIcon}
                      />
                      <Text style={styles.shortcutBtnTextSecondary}>
                        {t('applications.listingBtn')}
                      </Text>
                    </PressableScale>
                  ) : null}
                </View>
              </Card>

              {/* Draft Application or Canonical Status Card */}
              {detail.status === 'saved' ? (
                <Card style={styles.draftNoticeCard} padding="md">
                  <View style={styles.draftNoticeHeader}>
                    <View style={styles.draftIconCircle}>
                      <Ionicons
                        name="document-text-outline"
                        size={22}
                        color={colors.accentStrong || colors.tealDark}
                      />
                    </View>
                    <View style={styles.draftNoticeTitleCol}>
                      <Text style={styles.draftNoticeTitle}>
                        {t('applicationDetail.draftTitle', 'Draft Application')}
                      </Text>
                      <Text style={styles.draftNoticeSubtitle}>
                        {t(
                          'applicationDetail.draftSubtitle',
                          'This application is saved as a draft. Review your cover letter before submitting to the employer.'
                        )}
                      </Text>
                    </View>
                  </View>

                  <PressableScale
                    style={styles.submitDraftBtn}
                    onPress={() =>
                      navigation.navigate('CoverLetter', {
                        applicationId: detail.id,
                        draft: detail.generated_cover_letter,
                        currentStatus: detail.status,
                        internshipId: detail.internship_id,
                        companyName: detail.company_name,
                        jobTitle: detail.job_title,
                      })
                    }
                    accessibilityRole="button"
                    accessibilityLabel={t('applicationDetail.reviewAndSubmit', 'Review & Submit Application')}
                  >
                    <Ionicons name="paper-plane-outline" size={16} color={colors.textInverse || colors.white} />
                    <Text style={styles.submitDraftBtnText}>
                      {t('applicationDetail.reviewAndSubmit', 'Review & Submit Application')}
                    </Text>
                  </PressableScale>
                </Card>
              ) : (
                <Card style={styles.sectionCard} padding="md">
                  <View style={styles.sectionHeaderRow}>
                    <Text style={styles.sectionTitle}>
                      {t('applicationDetail.canonicalStatusTitle', 'Application Status')}
                    </Text>
                    <StatusPill status={detail.status} />
                  </View>
                  <Text style={styles.canonicalStatusExplanation}>
                    {detail.status === 'applied' &&
                      t(
                        'applicationDetail.statusExplanationApplied',
                        'Your application has been received by the employer and is awaiting review.'
                      )}
                    {detail.status === 'interviewing' &&
                      t(
                        'applicationDetail.statusExplanationInterviewing',
                        'Great news! The employer has selected your application for the interview stage.'
                      )}
                    {detail.status === 'accepted' &&
                      t(
                        'applicationDetail.statusExplanationAccepted',
                        'Congratulations! Your application has been accepted for this internship.'
                      )}
                    {detail.status === 'rejected' &&
                      t(
                        'applicationDetail.statusExplanationRejected',
                        'The employer has reviewed your application and decided not to proceed at this time.'
                      )}
                  </Text>
                </Card>
              )}

              {detail.interview_scheduled_at && (
                <Card style={styles.sectionCard} padding="md">
                  <View style={styles.interviewDetailHeader}>
                    <View style={styles.interviewDetailIconWrap}>
                      <Ionicons
                        name="calendar-outline"
                        size={20}
                        color={colors.accent || colors.teal}
                      />
                    </View>
                    <View style={styles.interviewDetailHeaderText}>
                      <Text style={styles.sectionTitle}>
                        {t(
                          'interviewScheduling.candidateCardTitle',
                          'Interview Details'
                        )}
                      </Text>
                      <Text style={styles.sectionSubtitle}>
                        {t(
                          'interviewScheduling.candidateCardSubtitle',
                          'Your employer has scheduled an interview.'
                        )}
                      </Text>
                    </View>
                  </View>

                  <View style={styles.interviewDetailRows}>
                    <View style={styles.interviewDetailRow}>
                      <Ionicons
                        name="time-outline"
                        size={17}
                        color={colors.textSecondary || colors.textMuted}
                      />
                      <View style={styles.interviewDetailRowText}>
                        <Text style={styles.interviewDetailLabel}>
                          {t('interviewScheduling.dateTimeLabel', 'Date & Time')}
                        </Text>
                        <Text style={styles.interviewDetailValue}>
                          {formatEventDate(detail.interview_scheduled_at)}
                        </Text>
                      </View>
                    </View>

                    <View style={styles.interviewDetailRow}>
                      <Ionicons
                        name={
                          detail.interview_mode === 'online'
                            ? 'videocam-outline'
                            : 'location-outline'
                        }
                        size={17}
                        color={colors.textSecondary || colors.textMuted}
                      />
                      <View style={styles.interviewDetailRowText}>
                        <Text style={styles.interviewDetailLabel}>
                          {t('interviewScheduling.modeLabel', 'Interview Type')}
                        </Text>
                        <Text style={styles.interviewDetailValue}>
                          {detail.interview_mode === 'online'
                            ? t('interviewScheduling.online', 'Online')
                            : t('interviewScheduling.onsite', 'On-site')}
                        </Text>
                      </View>
                    </View>

                    {detail.interview_location ? (
                      <View style={styles.interviewDetailRow}>
                        <Ionicons
                          name={
                            detail.interview_mode === 'online'
                              ? 'link-outline'
                              : 'navigate-outline'
                          }
                          size={17}
                          color={colors.textSecondary || colors.textMuted}
                        />
                        <View style={styles.interviewDetailRowText}>
                          <Text style={styles.interviewDetailLabel}>
                            {detail.interview_mode === 'online'
                              ? t('interviewScheduling.linkLabel', 'Meeting Link')
                              : t('interviewScheduling.locationLabel', 'Interview Location')}
                          </Text>
                          <Text
                            style={styles.interviewDetailValue}
                            selectable
                          >
                            {detail.interview_location}
                          </Text>
                        </View>
                      </View>
                    ) : null}

                    {detail.interview_message ? (
                      <View style={styles.interviewMessageBox}>
                        <Text style={styles.interviewDetailLabel}>
                          {t(
                            'interviewScheduling.employerMessageTitle',
                            'Message from Employer'
                          )}
                        </Text>
                        <Text style={styles.interviewMessageText}>
                          {detail.interview_message}
                        </Text>
                      </View>
                    ) : null}
                  </View>
                </Card>
              )}

              {detail.status === 'interviewing' &&
                detail.interview_scheduled_at ? (
                <Card style={styles.interviewPrepCard} padding="md">
                  <View style={styles.interviewPrepHeader}>
                    <View style={styles.interviewPrepIconWrap}>
                      <Ionicons
                        name="sparkles"
                        size={20}
                        color={colors.accentStrong || colors.tealDark}
                      />
                    </View>

                    <View style={styles.interviewPrepHeaderText}>
                      <Text style={styles.sectionTitle}>
                        {t('interviewPrep.title', 'AI Interview Prep')}
                      </Text>
                      <Text style={styles.sectionSubtitle}>
                        {t(
                          'interviewPrep.subtitle',
                          'Personalized preparation grounded in your profile and this opportunity.'
                        )}
                      </Text>
                    </View>
                  </View>

                  {!interviewPrep ? (
                    <>
                      <Text style={styles.interviewPrepIntro}>
                        {t(
                          'interviewPrep.intro',
                          'Get likely practice questions, focus areas, strengths to highlight, and useful questions to ask.'
                        )}
                      </Text>

                      {interviewPrepError ? (
                        <Text style={styles.interviewPrepError}>
                          {t(
                            'interviewPrep.error',
                            'Interview preparation could not be generated. Please try again.'
                          )}
                        </Text>
                      ) : null}

                      <TouchableOpacity
                        style={styles.interviewPrepGenerateBtn}
                        onPress={handleGenerateInterviewPrep}
                        disabled={interviewPrepLoading}
                        accessibilityRole="button"
                        accessibilityLabel={t(
                          'interviewPrep.generate',
                          'Generate AI Interview Prep'
                        )}
                      >
                        {interviewPrepLoading ? (
                          <View
                            style={
                              styles.interviewPrepLoadingRow
                            }
                          >
                            <ActivityIndicator
                              size="small"
                              color={
                                colors.textInverse ||
                                colors.white
                              }
                            />
                            <Text
                              style={
                                styles.interviewPrepLoadingText
                              }
                              accessibilityLiveRegion="polite"
                            >
                              {t(
                                'interviewPrep.generating',
                                {
                                  progress:
                                    interviewPrepProgress,
                                  defaultValue:
                                    'Preparing interview guidance ({{progress}}%)...',
                                }
                              )}
                            </Text>
                          </View>
                        ) : (
                          <>
                            <Ionicons
                              name="sparkles-outline"
                              size={17}
                              color={colors.textInverse || colors.white}
                            />
                            <Text style={styles.interviewPrepGenerateText}>
                              {t(
                                'interviewPrep.generate',
                                'Generate AI Interview Prep'
                              )}
                            </Text>
                          </>
                        )}
                      </TouchableOpacity>
                    </>
                  ) : (
                    <View style={styles.interviewPrepContent}>
                      <Text style={styles.interviewPrepSummary}>
                        {interviewPrep.preparation_summary}
                      </Text>

                      {interviewPrep.likely_questions?.length > 0 ? (
                        <View style={styles.interviewPrepSection}>
                          <Text style={styles.interviewPrepSectionTitle}>
                            {t('interviewPrep.likelyQuestions', 'Practice Questions')}
                          </Text>
                          {interviewPrep.likely_questions.map((item, index) => (
                            <View
                              key={`question-${index}`}
                              style={styles.interviewPrepBulletRow}
                            >
                              <Text style={styles.interviewPrepBullet}>
                                {index + 1}.
                              </Text>
                              <Text style={styles.interviewPrepBulletText}>
                                {item}
                              </Text>
                            </View>
                          ))}
                        </View>
                      ) : null}

                      {interviewPrep.focus_areas?.length > 0 ? (
                        <View style={styles.interviewPrepSection}>
                          <Text style={styles.interviewPrepSectionTitle}>
                            {t('interviewPrep.focusAreas', 'Focus Areas')}
                          </Text>
                          {interviewPrep.focus_areas.map((item, index) => (
                            <View
                              key={`focus-${index}`}
                              style={styles.interviewPrepBulletRow}
                            >
                              <Ionicons
                                name="flag-outline"
                                size={15}
                                color={colors.accent || colors.teal}
                              />
                              <Text style={styles.interviewPrepBulletText}>
                                {item}
                              </Text>
                            </View>
                          ))}
                        </View>
                      ) : null}

                      {interviewPrep.strengths_to_highlight?.length > 0 ? (
                        <View style={styles.interviewPrepSection}>
                          <Text style={styles.interviewPrepSectionTitle}>
                            {t(
                              'interviewPrep.strengths',
                              'Strengths to Highlight'
                            )}
                          </Text>
                          {interviewPrep.strengths_to_highlight.map(
                            (item, index) => (
                              <View
                                key={`strength-${index}`}
                                style={styles.interviewPrepBulletRow}
                              >
                                <Ionicons
                                  name="checkmark-circle-outline"
                                  size={15}
                                  color={colors.success || '#10B981'}
                                />
                                <Text style={styles.interviewPrepBulletText}>
                                  {item}
                                </Text>
                              </View>
                            )
                          )}
                        </View>
                      ) : null}

                      {interviewPrep.questions_to_ask?.length > 0 ? (
                        <View style={styles.interviewPrepSection}>
                          <Text style={styles.interviewPrepSectionTitle}>
                            {t(
                              'interviewPrep.questionsToAsk',
                              'Questions You Can Ask'
                            )}
                          </Text>
                          {interviewPrep.questions_to_ask.map(
                            (item, index) => (
                              <View
                                key={`ask-${index}`}
                                style={styles.interviewPrepBulletRow}
                              >
                                <Ionicons
                                  name="chatbubble-ellipses-outline"
                                  size={15}
                                  color={colors.accent || colors.teal}
                                />
                                <Text style={styles.interviewPrepBulletText}>
                                  {item}
                                </Text>
                              </View>
                            )
                          )}
                        </View>
                      ) : null}

                      <Text style={styles.interviewPrepDisclaimer}>
                        {t(
                          'interviewPrep.disclaimer',
                          'These are AI-generated preparation suggestions, not guaranteed employer questions.'
                        )}
                      </Text>
                    </View>
                  )}
                </Card>
              ) : null}

              {/* Status Timeline Card */}
              <Card style={styles.sectionCard} padding="md">
                <Text style={styles.sectionTitle}>{t('applicationDetail.timelineTitle')}</Text>
                <Text style={styles.sectionSubtitle}>
                  {t('applicationDetail.timelineSubtitle')}
                </Text>

                {detail.timeline && detail.timeline.length > 0 ? (
                  <View style={styles.timelineList}>
                    {detail.timeline.map((event, index) => {
                      const config =
                        STATUS_CONFIG[event.status] || STATUS_CONFIG.saved;
                      const label = t(`applications.statuses.${event.status}`, { defaultValue: event.status });
                      const isLast = index === detail.timeline.length - 1;

                      return (
                        <View key={`${event.status}-${event.occurred_at}-${index}`} style={styles.timelineStepRow}>
                          {/* Rail & Marker */}
                          <View style={styles.timelineRailCol}>
                            <View
                              style={[
                                styles.timelineMarker,
                                {
                                  borderColor: config.fg,
                                  backgroundColor: config.bg,
                                },
                              ]}
                            >
                              <Ionicons
                                name={config.icon}
                                size={12}
                                color={config.fg}
                              />
                            </View>
                            {!isLast && <View style={styles.timelineLine} />}
                          </View>

                          {/* Event Details */}
                          <View style={styles.timelineContentWrap}>
                            <View style={styles.timelineHeaderRow}>
                              <Text style={styles.timelineStatusTitle}>
                                {label}
                              </Text>
                            </View>
                            <Text style={styles.timelineTimestamp}>
                              {formatEventDate(event.occurred_at)}
                            </Text>
                          </View>
                        </View>
                      );
                    })}
                  </View>
                ) : (
                  <View style={styles.emptyTimelineBox}>
                    <Ionicons
                      name="time-outline"
                      size={28}
                      color={colors.textTertiary || colors.textMuted}
                      style={styles.emptyTimelineIcon}
                    />
                    <Text style={styles.emptyTimelineTitle}>
                      {t('applicationDetail.emptyTimelineTitle')}
                    </Text>
                    <Text style={styles.emptyTimelineSubtitle}>
                      {t('applicationDetail.emptyTimelineSubtitle')}
                    </Text>
                  </View>
                )}
              </Card>

              {/* Notes Card */}
              <Card style={styles.sectionCard} padding="md">
                <View style={styles.notesHeaderRow}>
                  <Text style={styles.sectionTitle}>{t('applicationDetail.personalNotesTitle')}</Text>
                  {!isEditingNotes ? (
                    <TouchableOpacity
                      style={styles.editNotesToggle}
                      onPress={() => setIsEditingNotes(true)}
                      disabled={mutatingStatus || savingNotes || refreshing}
                      accessibilityRole="button"
                      accessibilityLabel={t('common.edit')}
                    >
                      <Ionicons
                        name="create-outline"
                        size={15}
                        color={colors.accent || colors.teal}
                      />
                      <Text style={styles.editNotesToggleText}>{t('common.edit')}</Text>
                    </TouchableOpacity>
                  ) : null}
                </View>

                {isEditingNotes ? (
                  <View style={styles.notesEditWrap}>
                    <TextInput
                      style={styles.notesInput}
                      value={notesText}
                      onChangeText={setNotesText}
                      editable={!savingNotes && !mutatingStatus && !refreshing}
                      placeholder={t('applicationDetail.notesPlaceholder')}
                      placeholderTextColor={colors.textTertiary || '#94A3B8'}
                      multiline={true}
                      numberOfLines={4}
                      textAlignVertical="top"
                      accessibilityLabel={t('applicationDetail.personalNotesTitle')}
                    />
                    <View style={styles.notesActionsRow}>
                      <TouchableOpacity
                        style={styles.notesCancelBtn}
                        onPress={() => {
                          setNotesText(detail.notes || '');
                          setIsEditingNotes(false);
                        }}
                        disabled={savingNotes || mutatingStatus || refreshing}
                        accessibilityRole="button"
                        accessibilityLabel={t('common.cancel')}
                      >
                        <Text style={styles.notesCancelBtnText}>{t('common.cancel')}</Text>
                      </TouchableOpacity>

                      <TouchableOpacity
                        style={styles.notesSaveBtn}
                        onPress={handleSaveNotes}
                        disabled={savingNotes || mutatingStatus || refreshing}
                        accessibilityRole="button"
                        accessibilityLabel={t('applicationDetail.saveNotes')}
                      >
                        {savingNotes ? (
                          <ActivityIndicator
                            size="small"
                            color={colors.textInverse || colors.white}
                          />
                        ) : (
                          <Text style={styles.notesSaveBtnText}>{t('applicationDetail.saveNotes')}</Text>
                        )}
                      </TouchableOpacity>
                    </View>
                  </View>
                ) : (
                  <View style={styles.notesDisplayBox}>
                    {detail.notes ? (
                      <Text style={styles.notesDisplayText}>{detail.notes}</Text>
                    ) : (
                      <Text style={styles.notesEmptyText}>
                        {t('applicationDetail.noNotesText')}
                      </Text>
                    )}
                  </View>
                )}
              </Card>
            </>
          )}
        </ScrollView>
      </KeyboardAvoidingView>
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  scrollView: {
    flex: 1,
    backgroundColor: colors.background || colors.screenBg,
  },
  content: {
    paddingHorizontal: spacing.screenHorizontalPadding,
    paddingTop: spacing.xs,
    paddingBottom: spacing.xxxl * 2,
  },
  centerContainer: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: spacing.xxxl * 2,
  },
  loadingText: {
    ...typography.bodyMedium,
    color: colors.textSecondary || colors.textMuted,
    marginTop: spacing.md,
  },
  notFoundCard: {
    alignItems: 'center',
    marginTop: spacing.xl,
  },
  notFoundTitle: {
    ...typography.h3,
    color: colors.textPrimary || colors.textDark,
    marginTop: spacing.md,
    marginBottom: spacing.xs,
    textAlign: 'center',
  },
  notFoundSubtitle: {
    ...typography.bodyMedium,
    color: colors.textSecondary || colors.textMuted,
    textAlign: 'center',
    marginBottom: spacing.xl,
  },
  backBtn: {
    backgroundColor: colors.accent || colors.teal,
    paddingHorizontal: spacing.xl,
    paddingVertical: spacing.sm,
    borderRadius: spacing.radiusMd || 10,
    minHeight: spacing.minimumTouchTarget,
    justifyContent: 'center',
    alignItems: 'center',
  },
  backBtnText: {
    ...typography.bodyMedium,
    color: colors.textInverse || colors.white,
    fontWeight: '600',
  },
  errorCard: {
    alignItems: 'center',
    marginTop: spacing.xl,
  },
  errorTitle: {
    ...typography.h3,
    color: colors.danger || '#EF4444',
    marginTop: spacing.md,
    marginBottom: spacing.xs,
    textAlign: 'center',
  },
  errorSubtitle: {
    ...typography.bodyMedium,
    color: colors.textSecondary || colors.textMuted,
    textAlign: 'center',
    marginBottom: spacing.xl,
  },
  retryBtn: {
    backgroundColor: colors.accent || colors.teal,
    paddingHorizontal: spacing.xl,
    paddingVertical: spacing.sm,
    borderRadius: spacing.radiusMd || 10,
    minHeight: spacing.minimumTouchTarget,
    justifyContent: 'center',
    alignItems: 'center',
  },
  retryBtnText: {
    ...typography.bodyMedium,
    color: colors.textInverse || colors.white,
    fontWeight: '600',
  },
  heroCard: {
    marginBottom: spacing.md,
  },
  heroHeader: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
  },
  heroTitleWrap: {
    flex: 1,
    marginEnd: spacing.sm,
  },
  jobTitle: {
    ...typography.h2,
    color: colors.textPrimary || colors.textDark,
    fontWeight: '700',
  },
  companyRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: spacing.xxs + 2,
  },
  companyIcon: {
    marginEnd: spacing.xs,
  },
  companyName: {
    ...typography.bodyMedium,
    color: colors.textSecondary || colors.textMuted,
    fontWeight: '500',
  },
  statusPill: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: spacing.sm + 2,
    paddingVertical: spacing.xxs + 2,
    borderRadius: spacing.radiusSm || 8,
  },
  pillIcon: {
    marginEnd: spacing.xxs + 2,
  },
  statusPillText: {
    ...typography.caption,
    fontWeight: '700',
    fontSize: 12,
  },
  appliedDateBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.infoSoft || '#E0F2FE',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs + 2,
    borderRadius: spacing.radiusSm || 8,
    marginTop: spacing.md,
  },
  appliedIcon: {
    marginEnd: spacing.xs,
  },
  appliedDateText: {
    ...typography.caption,
    color: colors.info || '#0284C7',
    fontWeight: '600',
  },
  shortcutsRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    marginTop: spacing.md,
  },
  shortcutBtnPrimary: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.accentSoft || '#E6F4F6',
    borderWidth: 1,
    borderColor: colors.accent || colors.teal,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs + 2,
    borderRadius: spacing.radiusSm || 8,
    minHeight: 38,
  },
  shortcutIcon: {
    marginEnd: spacing.xs,
  },
  shortcutBtnTextPrimary: {
    ...typography.caption,
    color: colors.accentStrong || colors.tealDark,
    fontWeight: '600',
  },
  shortcutBtnSecondary: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.surfaceMuted || '#F1F5F9',
    borderWidth: 1,
    borderColor: colors.border || '#E2E8F0',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs + 2,
    borderRadius: spacing.radiusSm || 8,
    minHeight: 38,
  },
  shortcutIcon: {
    marginEnd: spacing.xs,
  },
  shortcutBtnTextSecondary: {
    ...typography.caption,
    color: colors.textPrimary || colors.textDark,
    fontWeight: '600',
  },
  interviewPrepCard: {
    marginBottom: spacing.md,
    borderWidth: 1,
    borderColor: colors.accentSoft || '#CCFBF1',
  },
  interviewPrepHeader: {
    flexDirection: 'row',
    alignItems: 'flex-start',
  },
  interviewPrepIconWrap: {
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.accentSoft || '#E6F4F6',
    marginEnd: spacing.sm,
  },
  interviewPrepHeaderText: {
    flex: 1,
  },
  interviewPrepIntro: {
    ...typography.bodyMedium,
    color: colors.textSecondary || colors.textMuted,
    lineHeight: 20,
    marginBottom: spacing.md,
  },
  interviewPrepError: {
    ...typography.caption,
    color: colors.danger || '#EF4444',
    marginBottom: spacing.sm,
  },
  interviewPrepGenerateBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.xs,
    minHeight: spacing.minimumTouchTarget,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: spacing.radiusSm || 8,
    backgroundColor: colors.accent || colors.teal,
  },
  interviewPrepGenerateText: {
    ...typography.bodyMedium,
    color: colors.textInverse || colors.white,
    fontWeight: '700',
  },
  interviewPrepContent: {
    marginTop: spacing.xs,
  },
  interviewPrepSummary: {
    ...typography.bodyMedium,
    color: colors.textPrimary || colors.textDark,
    lineHeight: 21,
  },
  interviewPrepSection: {
    marginTop: spacing.md,
  },
  interviewPrepSectionTitle: {
    ...typography.bodyMedium,
    color: colors.textPrimary || colors.textDark,
    fontWeight: '700',
    marginBottom: spacing.xs,
  },
  interviewPrepBulletRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: spacing.xs,
    marginBottom: spacing.xs,
  },
  interviewPrepBullet: {
    ...typography.caption,
    minWidth: 18,
    color: colors.accentStrong || colors.tealDark,
    fontWeight: '700',
  },
  interviewPrepBulletText: {
    ...typography.bodyMedium,
    flex: 1,
    color: colors.textSecondary || colors.textMuted,
    lineHeight: 20,
  },
  interviewPrepDisclaimer: {
    ...typography.caption,
    color: colors.textTertiary || colors.textMuted,
    lineHeight: 17,
    marginTop: spacing.md,
  },
  sectionCard: {
    marginBottom: spacing.md,
  },
  sectionHeaderRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  sectionTitle: {
    ...typography.h3,
    color: colors.textPrimary || colors.textDark,
    fontWeight: '700',
  },
  sectionSubtitle: {
    ...typography.caption,
    color: colors.textSecondary || colors.textMuted,
    marginTop: spacing.xxs,
    marginBottom: spacing.md,
  },
  canonicalStatusExplanation: {
    ...typography.bodyMedium,
    color: colors.textSecondary || colors.textMuted,
    marginTop: spacing.xs,
    lineHeight: 20,
  },
  draftNoticeCard: {
    marginBottom: spacing.md,
    backgroundColor: '#F0FDFA',
    borderWidth: 1,
    borderColor: '#99F6E4',
  },
  draftNoticeHeader: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    marginBottom: spacing.md,
  },
  draftIconCircle: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: '#CCFBF1',
    alignItems: 'center',
    justifyContent: 'center',
    marginEnd: spacing.sm,
  },
  draftNoticeTitleCol: {
    flex: 1,
  },
  draftNoticeTitle: {
    ...typography.h3,
    fontSize: 16,
    color: colors.accentStrong || '#0F766E',
    fontWeight: '700',
  },
  draftNoticeSubtitle: {
    ...typography.caption,
    color: '#134E4A',
    marginTop: 2,
    lineHeight: 18,
  },
  submitDraftBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.accent || colors.teal,
    paddingVertical: spacing.sm + 2,
    paddingHorizontal: spacing.md,
    borderRadius: spacing.radiusSm || 8,
    minHeight: spacing.minimumTouchTarget,
    gap: spacing.xs,
  },
  submitDraftBtnText: {
    ...typography.bodyMedium,
    color: colors.textInverse || colors.white,
    fontWeight: '700',
    fontSize: 14,
  },
  statusChipsGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.xs + 2,
  },
  statusChip: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.surfaceMuted || '#F8FAFC',
    borderWidth: 1,
    borderColor: colors.border || '#E2E8F0',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs + 2,
    borderRadius: spacing.radiusSm || 8,
    minHeight: 36,
  },
  statusChipSelected: {
    backgroundColor: colors.surface || colors.white,
    borderWidth: 1.5,
  },
  chipIcon: {
    marginEnd: spacing.xs,
  },
  statusChipText: {
    ...typography.caption,
    color: colors.textSecondary || colors.textMuted,
    fontWeight: '500',
  },
  timelineList: {
    marginTop: spacing.xs,
  },
  timelineStepRow: {
    flexDirection: 'row',
    minHeight: 52,
  },
  timelineRailCol: {
    alignItems: 'center',
    width: 28,
    marginEnd: spacing.sm,
  },
  timelineMarker: {
    width: 24,
    height: 24,
    borderRadius: 12,
    borderWidth: 2,
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 2,
  },
  timelineLine: {
    width: 2,
    flex: 1,
    backgroundColor: colors.border || '#E2E8F0',
    marginVertical: 2,
  },
  timelineContentWrap: {
    flex: 1,
    paddingBottom: spacing.md,
  },
  timelineHeaderRow: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  timelineStatusTitle: {
    ...typography.bodyMedium,
    color: colors.textPrimary || colors.textDark,
    fontWeight: '600',
  },
  timelineTimestamp: {
    ...typography.caption,
    color: colors.textSecondary || colors.textMuted,
    marginTop: 2,
    fontSize: 12,
  },
  emptyTimelineBox: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: spacing.lg,
    paddingHorizontal: spacing.md,
    backgroundColor: colors.surfaceMuted || '#F8FAFC',
    borderRadius: spacing.radiusSm || 8,
    borderWidth: 1,
    borderColor: colors.border || '#E2E8F0',
    borderStyle: 'dashed',
  },
  emptyTimelineIcon: {
    marginBottom: spacing.xs,
  },
  emptyTimelineTitle: {
    ...typography.bodyMedium,
    color: colors.textSecondary || colors.textMuted,
    fontWeight: '600',
    textAlign: 'center',
  },
  emptyTimelineSubtitle: {
    ...typography.caption,
    color: colors.textTertiary || colors.textMuted,
    textAlign: 'center',
    marginTop: spacing.xxs,
  },
  notesHeaderRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: spacing.sm,
  },
  editNotesToggle: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: spacing.xs,
  },
  editNotesToggleText: {
    ...typography.caption,
    color: colors.accent || colors.teal,
    fontWeight: '600',
    marginStart: spacing.xxs + 2,
  },
  notesDisplayBox: {
    backgroundColor: colors.surfaceMuted || '#F8FAFC',
    padding: spacing.md,
    borderRadius: spacing.radiusSm || 8,
    borderWidth: 1,
    borderColor: colors.border || '#E2E8F0',
    minHeight: 60,
  },
  notesDisplayText: {
    ...typography.bodyMedium,
    color: colors.textPrimary || colors.textDark,
    lineHeight: 20,
  },
  notesEmptyText: {
    ...typography.caption,
    color: colors.textTertiary || colors.textMuted,
    fontStyle: 'italic',
  },
  notesEditWrap: {
    marginTop: spacing.xxs,
  },
  notesInput: {
    ...typography.bodyMedium,
    backgroundColor: colors.surface || colors.white,
    borderWidth: 1,
    borderColor: colors.accent || colors.teal,
    borderRadius: spacing.radiusSm || 8,
    padding: spacing.md,
    color: colors.textPrimary || colors.textDark,
    minHeight: 90,
  },
  notesActionsRow: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    alignItems: 'center',
    gap: spacing.sm,
    marginTop: spacing.sm,
  },
  notesCancelBtn: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs + 2,
    borderRadius: spacing.radiusSm || 8,
    minHeight: 36,
    justifyContent: 'center',
    alignItems: 'center',
  },
  notesCancelBtnText: {
    ...typography.caption,
    color: colors.textSecondary || colors.textMuted,
    fontWeight: '600',
  },
  notesSaveBtn: {
    backgroundColor: colors.accent || colors.teal,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.xs + 2,
    borderRadius: spacing.radiusSm || 8,
    minHeight: 36,
    justifyContent: 'center',
    alignItems: 'center',
  },
  notesSaveBtnText: {
    ...typography.caption,
    color: colors.textInverse || colors.white,
    fontWeight: '600',
  },
  interviewDetailHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    marginBottom: spacing.md,
  },
  interviewDetailIconWrap: {
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.surfaceMuted || '#F1F5F9',
  },
  interviewDetailHeaderText: {
    flex: 1,
  },
  interviewDetailRows: {
    gap: spacing.md,
  },
  interviewDetailRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: spacing.sm,
  },
  interviewDetailRowText: {
    flex: 1,
  },
  interviewDetailLabel: {
    ...typography.caption,
    fontWeight: '600',
    color: colors.textSecondary || colors.textMuted,
  },
  interviewDetailValue: {
    ...typography.body,
    color: colors.textPrimary || colors.textDark,
    marginTop: 2,
  },
  interviewMessageBox: {
    backgroundColor: colors.surfaceMuted || '#F8FAFC',
    borderRadius: spacing.radiusSm || 8,
    padding: spacing.md,
    borderWidth: 1,
    borderColor: colors.border || '#E2E8F0',
  },
  interviewMessageText: {
    ...typography.body,
    color: colors.textPrimary || colors.textDark,
    marginTop: spacing.xs,
    lineHeight: 21,
  },

  interviewPrepLoadingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.sm,
  },
  interviewPrepLoadingText: {
    color: colors.textInverse || colors.white,
    fontSize: 13,
    fontWeight: '700',
  },
});
