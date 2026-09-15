import React, { useState, useEffect, useCallback } from 'react';
import { TextInput } from 'react-native';
import { scheduleEmployerApplicantInterview } from '../services/api';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  ActivityIndicator,
  RefreshControl,
  TouchableOpacity,
  Alert,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as Sharing from 'expo-sharing';
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
import Chip from '../components/Chip';
import MatchBadge from '../components/MatchBadge';
import Reveal from '../components/motion/Reveal';
import EmployerCandidateIntelligence from '../components/EmployerCandidateIntelligence';
import {
  downloadEmployerApplicantCV,
  deleteTemporaryEmployerApplicantCV,
  getEmployerApplicantDetail,
  updateEmployerApplicantStatus,
} from '../services/api';

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

export default function EmployerApplicantDetailScreen({ route, navigation }) {
  const { t } = useTranslation();
  const { locale, isRTL } = useLocalization();
  const insets = useSafeAreaInsets();

  const { internshipId, applicationId, applicant: initialApplicant } = route.params || {};

  const [applicant, setApplicant] = useState(initialApplicant || null);
  const [loading, setLoading] = useState(!initialApplicant);
  const [refreshing, setRefreshing] = useState(false);
  const [mutatingStatus, setMutatingStatus] = useState(false);
  const [interviewFormOpen, setInterviewFormOpen] = useState(false);
  const [interviewDate, setInterviewDate] = useState('');
  const [interviewTime, setInterviewTime] = useState('');
  const [interviewMode, setInterviewMode] = useState('online');
  const [interviewLocation, setInterviewLocation] = useState('');
  const [interviewMessage, setInterviewMessage] = useState('');
  const [error, setError] = useState(null);
  const [openingCV, setOpeningCV] = useState(false);

  const fetchDetail = useCallback(
    async (isRefresh = false) => {
      if (!internshipId || !applicationId) return;

      if (isRefresh) {
        setRefreshing(true);
      } else if (!applicant) {
        setLoading(true);
      }
      setError(null);

      try {
        const res = await getEmployerApplicantDetail(internshipId, applicationId);
        setApplicant(res);
      } catch (err) {
        console.warn('Failed to load employer applicant detail:', err);
        if (!applicant) {
          setError('LOAD_FAILED');
        }
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [internshipId, applicationId, applicant]
  );

  useEffect(() => {
    fetchDetail();
  }, [fetchDetail]);

  const handleRefresh = () => {
    fetchDetail(true);
  };

  const handleUpdateStatus = useCallback(
    async (newStatus, notes) => {
      if (!internshipId || !applicationId || mutatingStatus) return;

      setMutatingStatus(true);
      try {
        const updated = await updateEmployerApplicantStatus(internshipId, applicationId, {
          status: newStatus,
          notes,
        });
        setApplicant((prev) => ({
          ...prev,
          status: updated.status || newStatus,
          updated_at: updated.updated_at || prev.updated_at,
        }));
      } catch (err) {
        console.warn('Failed to update applicant status:', err);
        Alert.alert(
          t('common.error', 'Error'),
          t('employerApplicantDetail.updateStatusError', 'Failed to update applicant status. Please try again.')
        );
      } finally {
        setMutatingStatus(false);
      }
    },
    [internshipId, applicationId, mutatingStatus, t]
  );

  const openInterviewForm = useCallback(() => {
    if (applicant?.interview_scheduled_at) {
      const scheduled = new Date(applicant.interview_scheduled_at);

      if (!Number.isNaN(scheduled.getTime())) {
        const year = scheduled.getFullYear();
        const month = String(scheduled.getMonth() + 1).padStart(2, '0');
        const day = String(scheduled.getDate()).padStart(2, '0');
        const hours = String(scheduled.getHours()).padStart(2, '0');
        const minutes = String(scheduled.getMinutes()).padStart(2, '0');

        setInterviewDate(`${year}-${month}-${day}`);
        setInterviewTime(`${hours}:${minutes}`);
      }

      setInterviewMode(applicant.interview_mode || 'online');
      setInterviewLocation(applicant.interview_location || '');
      setInterviewMessage(applicant.interview_message || '');
    }

    setInterviewFormOpen(true);
  }, [applicant]);

  const handleScheduleInterview = useCallback(async () => {
    if (!internshipId || !applicationId || mutatingStatus) {
      return;
    }

    const cleanDate = interviewDate.trim();
    const cleanTime = interviewTime.trim();
    const cleanLocation = interviewLocation.trim();
    const cleanMessage = interviewMessage.trim();

    if (!cleanDate || !cleanTime || !cleanLocation) {
      Alert.alert(
        t('common.error', 'Error'),
        t(
          'interviewScheduling.requiredFields',
          'Date, time, and meeting location are required.'
        )
      );
      return;
    }

    const localDateTime = new Date(`${cleanDate}T${cleanTime}:00`);

    if (Number.isNaN(localDateTime.getTime())) {
      Alert.alert(
        t('common.error', 'Error'),
        t(
          'interviewScheduling.invalidDateTime',
          'Enter a valid interview date and time.'
        )
      );
      return;
    }

    if (localDateTime.getTime() <= Date.now()) {
      Alert.alert(
        t('common.error', 'Error'),
        t(
          'interviewScheduling.futureDateRequired',
          'The interview must be scheduled for a future time.'
        )
      );
      return;
    }

    setMutatingStatus(true);

    try {
      const updated = await scheduleEmployerApplicantInterview(
        internshipId,
        applicationId,
        {
          scheduled_at: localDateTime.toISOString(),
          mode: interviewMode,
          location: cleanLocation,
          message: cleanMessage || null,
        }
      );

      setApplicant(updated);
      setInterviewFormOpen(false);

      Alert.alert(
        t('interviewScheduling.successTitle', 'Interview Scheduled'),
        t(
          'interviewScheduling.successMessage',
          'The interview details are now visible to the candidate.'
        )
      );
    } catch (err) {
      console.warn('Failed to schedule interview:', err);

      Alert.alert(
        t('common.error', 'Error'),
        t(
          'interviewScheduling.scheduleError',
          'Failed to schedule the interview. Please try again.'
        )
      );
    } finally {
      setMutatingStatus(false);
    }
  }, [
    internshipId,
    applicationId,
    mutatingStatus,
    interviewDate,
    interviewTime,
    interviewMode,
    interviewLocation,
    interviewMessage,
    t,
  ]);

  const confirmAccept = useCallback(() => {
    Alert.alert(
      t('employerApplicantDetail.acceptAlertTitle', 'Accept Candidate?'),
      t(
        'employerApplicantDetail.acceptAlertMessage',
        'This will mark the application as Accepted. The candidate will see their acceptance in their application tracker.'
      ),
      [
        { text: t('common.cancel', 'Cancel'), style: 'cancel' },
        {
          text: t('employerApplicantDetail.acceptBtn', 'Accept Candidate'),
          onPress: () => handleUpdateStatus('accepted'),
        },
      ]
    );
  }, [t, handleUpdateStatus]);

  const confirmReject = useCallback(() => {
    Alert.alert(
      t('employerApplicantDetail.rejectAlertTitle', 'Reject Candidate?'),
      t(
        'employerApplicantDetail.rejectAlertMessage',
        'This will mark the application as Rejected. This action cannot be undone.'
      ),
      [
        { text: t('common.cancel', 'Cancel'), style: 'cancel' },
        {
          text: t('employerApplicantDetail.rejectBtn', 'Reject Candidate'),
          style: 'destructive',
          onPress: () => handleUpdateStatus('rejected'),
        },
      ]
    );
  }, [t, handleUpdateStatus]);

  const handleViewCV = useCallback(async () => {
    if (!internshipId || !applicationId || openingCV) {
      return;
    }

    setOpeningCV(true);

    let localCV = null;

    try {
      // Security boundary:
      // CV bytes are fetched only through the authenticated InternMatch API.
      // No storage-provider URL or storage token reaches the mobile client.
      localCV = await downloadEmployerApplicantCV(
        internshipId,
        applicationId
      );

      const sharingAvailable =
        await Sharing.isAvailableAsync();

      if (!sharingAvailable) {
        throw new Error(
          'A local document viewer is unavailable on this device.'
        );
      }

      await Sharing.shareAsync(
        localCV.uri,
        {
          mimeType: localCV.mime_type,
          dialogTitle: t(
            'employerCandidateEvidence.openCV',
            'Open candidate CV'
          ),
        }
      );
    } catch (cvError) {
      Alert.alert(
        t(
          'employerCandidateEvidence.cvErrorTitle',
          'Unable to open CV'
        ),
        t(
          'employerCandidateEvidence.cvErrorMessage',
          'The candidate CV is unavailable right now. Please try again.'
        )
      );
    } finally {
      if (localCV?.uri) {
        try {
          await deleteTemporaryEmployerApplicantCV(
            localCV.uri
          );
        } catch {
          // Best-effort cache cleanup only.
        }
      }

      setOpeningCV(false);
    }
  }, [applicationId, internshipId, openingCV, t]);

  const candidate = applicant?.candidate;
  const statusStyle = getStatusBadgeStyle(applicant?.status);
  const appliedDateStr = applicant?.applied_date
    ? formatLocalizedDate(applicant.applied_date, locale)
    : '';

  const skillEvidence = Array.isArray(applicant?.skill_evidence)
    ? applicant.skill_evidence
    : [];

  const cvEvidencedSkills = skillEvidence.filter(
    (item) => item?.cv_evidenced === true
  );

  const selfDeclaredOnlySkills = skillEvidence.filter(
    (item) =>
      item?.self_declared === true &&
      item?.cv_evidenced !== true &&
      item?.cv_provenance_known === true
  );

  const legacyUnknownSkills = skillEvidence.filter(
    (item) =>
      item?.cv_evidenced !== true &&
      item?.cv_provenance_known !== true
  );

  return (
    <ScreenContainer edges={['top', 'bottom']}>
      <ScreenHeader
        title={candidate?.full_name || t('employerApplicantDetail.title')}
        subtitle={candidate?.department || undefined}
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
        {/* Loading State */}
        {loading && !refreshing && (
          <View style={styles.centerLoading}>
            <ActivityIndicator size="large" color={colors.accent || colors.teal} />
            <Text style={[styles.loadingText, isRTL && styles.rtlWriting]}>
              {t('employerApplicantDetail.loading')}
            </Text>
          </View>
        )}

        {/* Error State */}
        {error && !loading && !applicant && (
          <Card style={styles.errorCard} padding="lg">
            <Ionicons name="alert-circle-outline" size={32} color={colors.danger || '#EF4444'} />
            <Text style={[styles.errorTitle, isRTL && styles.rtlWriting]}>
              {t('employerApplicantDetail.errorTitle')}
            </Text>
            <Text style={[styles.errorSubtitle, isRTL && styles.rtlWriting]}>
              {t('employerApplicantDetail.errorSubtitle')}
            </Text>
            <TouchableOpacity
              style={styles.retryBtn}
              onPress={() => fetchDetail()}
              accessibilityRole="button"
              accessibilityLabel={t('employerApplicantDetail.retry')}
            >
              <Text style={styles.retryBtnText}>{t('employerApplicantDetail.retry')}</Text>
            </TouchableOpacity>
          </Card>
        )}

        {/* Populated Content */}
        {applicant && (
          <>
            {/* Sequence 1: Candidate Overview Card */}
            <Reveal delay={0}>
              <Card style={styles.overviewCard} padding="lg">
                <View style={[styles.overviewHeader, isRTL && styles.rowRTL]}>
                  <View style={styles.candidateAvatarCircle}>
                    <Ionicons name="person" size={28} color={colors.accentStrong || colors.tealDark} />
                  </View>
                  <View style={styles.overviewInfo}>
                    <Text style={[styles.candidateFullName, isRTL && styles.rtlText]} numberOfLines={1}>
                      {candidate?.full_name}
                    </Text>
                    {candidate?.headline ? (
                      <Text style={[styles.headlineText, isRTL && styles.rtlText]}>
                        {candidate.headline}
                      </Text>
                    ) : null}
                    {candidate?.department ? (
                      <Text style={[styles.departmentText, isRTL && styles.rtlText]}>
                        {candidate.department}
                      </Text>
                    ) : null}
                  </View>
                </View>

                {/* Match score section if available */}
                {typeof applicant.match_score === 'number' && (
                  <View style={[styles.matchScoreRow, isRTL && styles.rowRTL]}>
                    <Text style={[styles.matchScoreLabel, isRTL && styles.rtlText]}>
                      {t('employerApplicantDetail.matchScoreLabel')}
                    </Text>
                    <MatchBadge score={applicant.match_score} />
                  </View>
                )}
              </Card>
            </Reveal>

            {/* Grounded deterministic match explanation.
                These values are persisted canonical Match components from the backend.
                No LLM-generated recruiter explanation is used here. */}
            {typeof applicant.match_score === 'number' && (
              <Reveal delay={20}>
                <Card style={styles.employerMatchExplanationCard} padding="md">
                  <View style={[styles.explanationHeader, isRTL && styles.rowRTL]}>
                    <View style={styles.explanationTitleBlock}>
                      <Text style={[styles.sectionTitle, isRTL && styles.rtlText]}>
                        {t(
                          'employerCandidateRanking.explanationTitle',
                          'Why this candidate ranks here'
                        )}
                      </Text>
                      <Text style={[styles.explanationSubtitle, isRTL && styles.rtlText]}>
                        {t(
                          'employerCandidateRanking.explanationSubtitle',
                          'Based on the same persisted match factors used to rank applicants.'
                        )}
                      </Text>
                    </View>
                    <MatchBadge score={applicant.match_score} />
                  </View>

                  <View style={styles.scoreBreakdown}>
                    <View style={[styles.scoreBreakdownRow, isRTL && styles.rowRTL]}>
                      <View style={styles.scoreBreakdownLabelBlock}>
                        <Text style={[styles.scoreBreakdownLabel, isRTL && styles.rtlText]}>
                          {t('employerCandidateRanking.skillsFit', 'Skills fit')}
                        </Text>
                        <Text style={[styles.scoreBreakdownWeight, isRTL && styles.rtlText]}>
                          {t('employerCandidateRanking.weight50', '50% of overall score')}
                        </Text>
                      </View>
                      <Text style={styles.scoreBreakdownValue}>
                        {typeof applicant.skill_score === 'number'
                          ? `${applicant.skill_score}/100`
                          : '—'}
                      </Text>
                    </View>

                    <View style={[styles.scoreBreakdownRow, isRTL && styles.rowRTL]}>
                      <View style={styles.scoreBreakdownLabelBlock}>
                        <Text style={[styles.scoreBreakdownLabel, isRTL && styles.rtlText]}>
                          {t('employerCandidateRanking.semanticFit', 'Semantic fit')}
                        </Text>
                        <Text style={[styles.scoreBreakdownWeight, isRTL && styles.rtlText]}>
                          {t('employerCandidateRanking.weight30', '30% of overall score')}
                        </Text>
                      </View>
                      <Text style={styles.scoreBreakdownValue}>
                        {typeof applicant.vector_score === 'number'
                          ? `${applicant.vector_score}/100`
                          : '—'}
                      </Text>
                    </View>

                    <View style={[styles.scoreBreakdownRow, isRTL && styles.rowRTL]}>
                      <View style={styles.scoreBreakdownLabelBlock}>
                        <Text style={[styles.scoreBreakdownLabel, isRTL && styles.rtlText]}>
                          {t('employerCandidateRanking.profileFit', 'Profile fit')}
                        </Text>
                        <Text style={[styles.scoreBreakdownWeight, isRTL && styles.rtlText]}>
                          {t('employerCandidateRanking.weight20', '20% of overall score')}
                        </Text>
                      </View>
                      <Text style={styles.scoreBreakdownValue}>
                        {typeof applicant.attribute_score === 'number'
                          ? `${applicant.attribute_score}/100`
                          : '—'}
                      </Text>
                    </View>
                  </View>

                  {(applicant.matching_skills?.length > 0 ||
                    applicant.missing_skills?.length > 0) && (
                    <View style={styles.skillsEvidenceBlock}>
                      {applicant.matching_skills?.length > 0 && (
                        <View style={styles.skillEvidenceSection}>
                          <Text style={[styles.skillEvidenceTitle, isRTL && styles.rtlText]}>
                            {t(
                              'employerCandidateRanking.matchingSkillsTitle',
                              'Matching skills'
                            )}
                          </Text>
                          <View style={[styles.skillChipWrap, isRTL && styles.rowRTL]}>
                            {applicant.matching_skills.map((skill) => (
                              <View key={`match-${skill}`} style={styles.matchingSkillChip}>
                                <Ionicons
                                  name="checkmark-circle-outline"
                                  size={14}
                                  color={colors.success || '#10B981'}
                                />
                                <Text
                                  style={[
                                    styles.matchingSkillText,
                                    isRTL && styles.rtlText,
                                  ]}
                                >
                                  {skill}
                                </Text>
                              </View>
                            ))}
                          </View>
                        </View>
                      )}

                      {applicant.missing_skills?.length > 0 && (
                        <View style={styles.skillEvidenceSection}>
                          <Text style={[styles.skillEvidenceTitle, isRTL && styles.rtlText]}>
                            {t(
                              'employerCandidateRanking.missingSkillsTitle',
                              'Missing role skills'
                            )}
                          </Text>
                          <View style={[styles.skillChipWrap, isRTL && styles.rowRTL]}>
                            {applicant.missing_skills.map((skill) => (
                              <View key={`missing-${skill}`} style={styles.missingSkillChip}>
                                <Ionicons
                                  name="remove-circle-outline"
                                  size={14}
                                  color={colors.warning || '#D97706'}
                                />
                                <Text
                                  style={[
                                    styles.missingSkillText,
                                    isRTL && styles.rtlText,
                                  ]}
                                >
                                  {skill}
                                </Text>
                              </View>
                            ))}
                          </View>
                        </View>
                      )}
                    </View>
                  )}

                  <Text style={[styles.explanationFootnote, isRTL && styles.rtlText]}>
                    {t(
                      'employerCandidateRanking.explanationFootnote',
                      'Ranking is decision support only. Review the full application before making a hiring decision.'
                    )}
                  </Text>
                </Card>
              </Reveal>
            )}

            {/* Sequence 2: Application Details & Recruiter Action Controls */}
            <Reveal delay={30}>
              <Card style={styles.metaCard} padding="md">
                <Text style={[styles.sectionTitle, isRTL && styles.rtlText]}>
                  {t('employerApplicantDetail.applicationStatus')}
                </Text>
                <View style={[styles.statusRow, isRTL && styles.rowRTL]}>
                  <View style={[styles.statusPill, { backgroundColor: statusStyle.bg }]}>
                    <Text style={[styles.statusPillText, { color: statusStyle.fg }]}>
                      {t(
                        `applicationStatusLabels.${applicant.status}`,
                        applicant.status
                      )}
                    </Text>
                  </View>
                  {appliedDateStr ? (
                    <Text style={[styles.appliedDateText, isRTL && styles.rtlText]}>
                      {t('employerApplicantDetail.appliedOn', { date: appliedDateStr })}
                    </Text>
                  ) : null}
                </View>

                {/* Recruiter Lifecycle Actions */}
                <View style={styles.actionsDivider} />
                <Text style={[styles.actionsHeading, isRTL && styles.rtlText]}>
                  {t('employerApplicantDetail.actionsHeading', 'Recruiter Decision')}
                </Text>

                {interviewFormOpen && (
                  <View style={styles.interviewFormCard}>
                    <View style={[styles.interviewFormHeader, isRTL && styles.rowRTL]}>
                      <View style={styles.interviewFormTitleWrap}>
                        <Text style={[styles.interviewFormTitle, isRTL && styles.rtlText]}>
                          {t(
                            'interviewScheduling.formTitle',
                            applicant.status === 'interviewing'
                              ? 'Reschedule Interview'
                              : 'Schedule Interview'
                          )}
                        </Text>
                        <Text style={[styles.interviewFormSubtitle, isRTL && styles.rtlText]}>
                          {t(
                            'interviewScheduling.formSubtitle',
                            'Set the canonical interview details the candidate will see.'
                          )}
                        </Text>
                      </View>
                      <Ionicons name="calendar-outline" size={22} color={colors.accent || colors.teal} />
                    </View>

                    <Text style={[styles.interviewFieldLabel, isRTL && styles.rtlText]}>
                      {t('interviewScheduling.modeLabel', 'Interview Type')}
                    </Text>

                    <View style={[styles.interviewModeRow, isRTL && styles.rowRTL]}>
                      <TouchableOpacity
                        style={[
                          styles.interviewModeButton,
                          interviewMode === 'online' && styles.interviewModeButtonActive,
                        ]}
                        onPress={() => setInterviewMode('online')}
                      >
                        <Ionicons
                          name="videocam-outline"
                          size={17}
                          color={
                            interviewMode === 'online'
                              ? (colors.textInverse || colors.white)
                              : (colors.textSecondary || colors.textMuted)
                          }
                        />
                        <Text
                          style={[
                            styles.interviewModeButtonText,
                            interviewMode === 'online' && styles.interviewModeButtonTextActive,
                          ]}
                        >
                          {t('interviewScheduling.online', 'Online')}
                        </Text>
                      </TouchableOpacity>

                      <TouchableOpacity
                        style={[
                          styles.interviewModeButton,
                          interviewMode === 'onsite' && styles.interviewModeButtonActive,
                        ]}
                        onPress={() => setInterviewMode('onsite')}
                      >
                        <Ionicons
                          name="location-outline"
                          size={17}
                          color={
                            interviewMode === 'onsite'
                              ? (colors.textInverse || colors.white)
                              : (colors.textSecondary || colors.textMuted)
                          }
                        />
                        <Text
                          style={[
                            styles.interviewModeButtonText,
                            interviewMode === 'onsite' && styles.interviewModeButtonTextActive,
                          ]}
                        >
                          {t('interviewScheduling.onsite', 'On-site')}
                        </Text>
                      </TouchableOpacity>
                    </View>

                    <View style={[styles.interviewDateTimeRow, isRTL && styles.rowRTL]}>
                      <View style={styles.interviewDateTimeField}>
                        <Text style={[styles.interviewFieldLabel, isRTL && styles.rtlText]}>
                          {t('interviewScheduling.dateLabel', 'Date')}
                        </Text>
                        <TextInput
                          style={[styles.interviewInput, isRTL && styles.rtlInput]}
                          value={interviewDate}
                          onChangeText={setInterviewDate}
                          placeholder="2026-09-01"
                          placeholderTextColor={colors.textTertiary || colors.textMuted}
                          autoCapitalize="none"
                        />
                      </View>

                      <View style={styles.interviewDateTimeField}>
                        <Text style={[styles.interviewFieldLabel, isRTL && styles.rtlText]}>
                          {t('interviewScheduling.timeLabel', 'Time')}
                        </Text>
                        <TextInput
                          style={[styles.interviewInput, isRTL && styles.rtlInput]}
                          value={interviewTime}
                          onChangeText={setInterviewTime}
                          placeholder="14:30"
                          placeholderTextColor={colors.textTertiary || colors.textMuted}
                          autoCapitalize="none"
                        />
                      </View>
                    </View>

                    <Text style={[styles.interviewFieldLabel, isRTL && styles.rtlText]}>
                      {interviewMode === 'online'
                        ? t('interviewScheduling.linkLabel', 'Meeting Link')
                        : t('interviewScheduling.locationLabel', 'Interview Location')}
                    </Text>

                    <TextInput
                      style={[styles.interviewInput, isRTL && styles.rtlInput]}
                      value={interviewLocation}
                      onChangeText={setInterviewLocation}
                      placeholder={
                        interviewMode === 'online'
                          ? 'https://meet.example.com/...'
                          : t('interviewScheduling.locationPlaceholder', 'Office or meeting address')
                      }
                      placeholderTextColor={colors.textTertiary || colors.textMuted}
                      autoCapitalize="none"
                      autoCorrect={false}
                    />

                    <Text style={[styles.interviewFieldLabel, isRTL && styles.rtlText]}>
                      {t('interviewScheduling.messageLabel', 'Message to Candidate')}
                    </Text>

                    <TextInput
                      style={[
                        styles.interviewInput,
                        styles.interviewMessageInput,
                        isRTL && styles.rtlInput,
                      ]}
                      value={interviewMessage}
                      onChangeText={setInterviewMessage}
                      placeholder={t(
                        'interviewScheduling.messagePlaceholder',
                        'Add preparation notes or anything the candidate should know.'
                      )}
                      placeholderTextColor={colors.textTertiary || colors.textMuted}
                      multiline
                      textAlignVertical="top"
                      maxLength={2000}
                    />

                    <View style={[styles.interviewFormActions, isRTL && styles.rowRTL]}>
                      <TouchableOpacity
                        style={styles.interviewCancelButton}
                        onPress={() => setInterviewFormOpen(false)}
                        disabled={mutatingStatus}
                      >
                        <Text style={styles.interviewCancelButtonText}>
                          {t('common.cancel', 'Cancel')}
                        </Text>
                      </TouchableOpacity>

                      <TouchableOpacity
                        style={styles.interviewScheduleButton}
                        onPress={handleScheduleInterview}
                        disabled={mutatingStatus}
                      >
                        <Ionicons
                          name="calendar-outline"
                          size={17}
                          color={colors.textInverse || colors.white}
                        />
                        <Text style={styles.interviewScheduleButtonText}>
                          {applicant.status === 'interviewing'
                            ? t('interviewScheduling.rescheduleAction', 'Reschedule')
                            : t('interviewScheduling.scheduleAction', 'Schedule Interview')}
                        </Text>
                      </TouchableOpacity>
                    </View>
                  </View>
                )}

                {applicant.status === 'interviewing' && !interviewFormOpen && (
                  <TouchableOpacity
                    style={[styles.rescheduleButton, isRTL && styles.rowRTL]}
                    onPress={openInterviewForm}
                    accessibilityRole="button"
                    accessibilityLabel={t(
                      'interviewScheduling.rescheduleAction',
                      'Reschedule'
                    )}
                  >
                    <Ionicons
                      name="calendar-outline"
                      size={17}
                      color={colors.accent || colors.teal}
                    />
                    <Text style={styles.rescheduleButtonText}>
                      {t('interviewScheduling.rescheduleAction', 'Reschedule Interview')}
                    </Text>
                  </TouchableOpacity>
                )}

                {mutatingStatus ? (
                  <View style={styles.actionLoadingRow}>
                    <ActivityIndicator size="small" color={colors.accent || colors.teal} />
                    <Text style={[styles.actionLoadingText, isRTL && styles.rtlText]}>
                      {t('employerApplicantDetail.updatingStatus', 'Updating candidate status...')}
                    </Text>
                  </View>
                ) : (
                  <>
                    {applicant.status === 'applied' && (
                      <View style={styles.actionButtonsCol}>
                        <TouchableOpacity
                          style={[styles.primaryActionBtn, isRTL && styles.rowRTL]}
                          onPress={openInterviewForm}
                          accessibilityRole="button"
                          accessibilityLabel={t('employerApplicantDetail.moveToInterview', 'Move to Interview')}
                        >
                          <Ionicons name="chatbubbles-outline" size={16} color={colors.textInverse || colors.white} />
                          <Text style={styles.primaryActionBtnText}>
                            {t('employerApplicantDetail.moveToInterview', 'Move to Interview')}
                          </Text>
                        </TouchableOpacity>

                        <View style={[styles.secondaryActionRow, isRTL && styles.rowRTL]}>
                          <TouchableOpacity
                            style={[styles.acceptBtn, isRTL && styles.rowRTL]}
                            onPress={confirmAccept}
                            accessibilityRole="button"
                            accessibilityLabel={t('employerApplicantDetail.acceptBtn', 'Accept Candidate')}
                          >
                            <Ionicons name="checkmark-circle-outline" size={16} color="#065F46" />
                            <Text style={styles.acceptBtnText}>
                              {t('employerApplicantDetail.acceptBtn', 'Accept Candidate')}
                            </Text>
                          </TouchableOpacity>

                          <TouchableOpacity
                            style={[styles.rejectBtn, isRTL && styles.rowRTL]}
                            onPress={confirmReject}
                            accessibilityRole="button"
                            accessibilityLabel={t('employerApplicantDetail.rejectBtn', 'Reject Candidate')}
                          >
                            <Ionicons name="close-circle-outline" size={16} color="#991B1B" />
                            <Text style={styles.rejectBtnText}>
                              {t('employerApplicantDetail.rejectBtn', 'Reject Candidate')}
                            </Text>
                          </TouchableOpacity>
                        </View>
                      </View>
                    )}

                    {applicant.status === 'interviewing' && (
                      <View style={styles.actionButtonsCol}>
                        <View style={styles.interviewingBanner}>
                          <Ionicons name="time-outline" size={18} color="#D97706" />
                          <Text style={[styles.interviewingBannerText, isRTL && styles.rtlText]}>
                            {t('employerApplicantDetail.inInterviewBanner', 'Candidate is currently in the interview stage.')}
                          </Text>
                        </View>

                        <View style={[styles.secondaryActionRow, isRTL && styles.rowRTL]}>
                          <TouchableOpacity
                            style={[styles.acceptBtn, isRTL && styles.rowRTL]}
                            onPress={confirmAccept}
                            accessibilityRole="button"
                            accessibilityLabel={t('employerApplicantDetail.acceptBtn', 'Accept Candidate')}
                          >
                            <Ionicons name="checkmark-circle-outline" size={16} color="#065F46" />
                            <Text style={styles.acceptBtnText}>
                              {t('employerApplicantDetail.acceptBtn', 'Accept Candidate')}
                            </Text>
                          </TouchableOpacity>

                          <TouchableOpacity
                            style={[styles.rejectBtn, isRTL && styles.rowRTL]}
                            onPress={confirmReject}
                            accessibilityRole="button"
                            accessibilityLabel={t('employerApplicantDetail.rejectBtn', 'Reject Candidate')}
                          >
                            <Ionicons name="close-circle-outline" size={16} color="#991B1B" />
                            <Text style={styles.rejectBtnText}>
                              {t('employerApplicantDetail.rejectBtn', 'Reject Candidate')}
                            </Text>
                          </TouchableOpacity>
                        </View>
                      </View>
                    )}

                    {applicant.status === 'accepted' && (
                      <View style={styles.terminalBannerAccepted}>
                        <Ionicons name="checkmark-done-circle" size={22} color="#10B981" />
                        <View style={styles.terminalBannerTextCol}>
                          <Text style={[styles.terminalAcceptedTitle, isRTL && styles.rtlText]}>
                            {t('employerApplicantDetail.acceptedBannerTitle', 'Offer Accepted')}
                          </Text>
                          <Text style={[styles.terminalSubtitle, isRTL && styles.rtlText]}>
                            {t('employerApplicantDetail.acceptedBannerSubtitle', 'This candidate has been accepted for the internship.')}
                          </Text>
                        </View>
                      </View>
                    )}

                    {applicant.status === 'rejected' && (
                      <View style={styles.terminalBannerRejected}>
                        <Ionicons name="close-circle" size={22} color="#EF4444" />
                        <View style={styles.terminalBannerTextCol}>
                          <Text style={[styles.terminalRejectedTitle, isRTL && styles.rtlText]}>
                            {t('employerApplicantDetail.rejectedBannerTitle', 'Application Closed')}
                          </Text>
                          <Text style={[styles.terminalSubtitle, isRTL && styles.rtlText]}>
                            {t('employerApplicantDetail.rejectedBannerSubtitle', 'Candidate was not selected for this position.')}
                          </Text>
                        </View>
                      </View>
                    )}
                  </>
                )}
              </Card>
            </Reveal>

            {typeof applicant.match_score === 'number' && (
              <Reveal delay={45}>
                <Card style={styles.aiRankingCard} padding="md">
                  <View style={[styles.aiRankingHeader, isRTL && styles.rowRTL]}>
                    <View style={styles.aiRankingIcon}>
                      <Ionicons
                        name="sparkles"
                        size={19}
                        color={colors.accentStrong || colors.tealDark}
                      />
                    </View>

                    <View style={styles.aiRankingHeaderText}>
                      <Text style={[styles.sectionTitle, isRTL && styles.rtlText]}>
                        {t('employerCandidateRanking.analysisTitle')}
                      </Text>
                      <Text style={[styles.aiRankingSubtitle, isRTL && styles.rtlText]}>
                        {t('employerCandidateRanking.analysisSubtitle')}
                      </Text>
                    </View>

                    <MatchBadge score={applicant.match_score} />
                  </View>

                  {applicant.matching_skills?.length > 0 ? (
                    <View style={styles.aiRankingSection}>
                      <Text style={[styles.aiRankingLabel, isRTL && styles.rtlText]}>
                        {t('employerCandidateRanking.strengths')}
                      </Text>
                      <View style={[styles.skillsChipRow, isRTL && styles.rowRTL]}>
                        {applicant.matching_skills.map((skill) => (
                          <Chip
                            key={`match-${skill}`}
                            label={skill}
                            variant="skill"
                          />
                        ))}
                      </View>
                    </View>
                  ) : null}

                  {applicant.missing_skills?.length > 0 ? (
                    <View style={styles.aiRankingSection}>
                      <Text style={[styles.aiRankingLabel, isRTL && styles.rtlText]}>
                        {t('employerCandidateRanking.gaps')}
                      </Text>
                      <Text style={[styles.aiRankingGapText, isRTL && styles.rtlText]}>
                        {applicant.missing_skills.join(', ')}
                      </Text>
                    </View>
                  ) : (
                    <Text style={[styles.aiRankingGapText, isRTL && styles.rtlText]}>
                      {t('employerCandidateRanking.noKnownGaps')}
                    </Text>
                  )}

                  <Text style={[styles.aiRankingDisclaimer, isRTL && styles.rtlText]}>
                    {t('employerCandidateRanking.disclaimer')}
                  </Text>
                </Card>
              </Reveal>
            )}

            {/* Sequence 3: Candidate Skills */}
            <Reveal delay={60}>
              <Card style={styles.skillsCard} padding="md">
                <Text style={[styles.sectionTitle, isRTL && styles.rtlText]}>
                  {t('employerApplicantDetail.skillsTitle')}
                </Text>
                {candidate?.skills && candidate.skills.length > 0 ? (
                  <View style={[styles.skillsChipRow, isRTL && styles.rowRTL]}>
                    {candidate.skills.map((sk) => (
                      <Chip key={sk} label={sk} variant="skill" />
                    ))}
                  </View>
                ) : (
                  <Text style={[styles.emptyText, isRTL && styles.rtlText]}>
                    {t('employerApplicantDetail.noSkills')}
                  </Text>
                )}
              </Card>
            </Reveal>

            {/* Candidate documents — CV access is requested only on demand. */}
            <Reveal delay={70}>
              <Card style={styles.documentsCard} padding="lg">
                <View style={[styles.evidenceCardHeader, isRTL && styles.rowRTL]}>
                  <View style={styles.evidenceHeaderIcon}>
                    <Ionicons
                      name="folder-open-outline"
                      size={20}
                      color={colors.accent || colors.teal}
                    />
                  </View>

                  <View style={styles.evidenceHeaderText}>
                    <Text style={[styles.sectionTitle, isRTL && styles.rtlText]}>
                      {t(
                        'employerCandidateEvidence.documentsTitle',
                        'Candidate Documents'
                      )}
                    </Text>
                    <Text style={[styles.evidenceSubtitle, isRTL && styles.rtlText]}>
                      {t(
                        'employerCandidateEvidence.documentsSubtitle',
                        'Access documents shared with this submitted application.'
                      )}
                    </Text>
                  </View>
                </View>

                <TouchableOpacity
                  style={[
                    styles.viewCVButton,
                    isRTL && styles.rowRTL,
                    openingCV && styles.viewCVButtonDisabled,
                  ]}
                  onPress={handleViewCV}
                  disabled={openingCV}
                  accessibilityRole="button"
                  accessibilityLabel={t(
                    'employerCandidateEvidence.viewCV',
                    'View CV'
                  )}
                >
                  {openingCV ? (
                    <ActivityIndicator
                      size="small"
                      color={colors.textInverse || colors.white}
                    />
                  ) : (
                    <Ionicons
                      name="document-outline"
                      size={18}
                      color={colors.textInverse || colors.white}
                    />
                  )}

                  <Text style={styles.viewCVButtonText}>
                    {openingCV
                      ? t(
                          'employerCandidateEvidence.openingCV',
                          'Opening CV...'
                        )
                      : t(
                          'employerCandidateEvidence.viewCV',
                          'View CV'
                        )}
                  </Text>
                </TouchableOpacity>

                <Text style={[styles.secureAccessNote, isRTL && styles.rtlText]}>
                  {t(
                    'employerCandidateEvidence.secureAccessNote',
                    'CV access is private and temporary. The document is fetched through InternMatch only when you open it; no storage-provider link is exposed.'
                  )}
                </Text>
              </Card>
            </Reveal>

            {/* Candidate skill provenance — separate CV evidence from profile claims. */}
            <Reveal delay={80}>
              <Card style={styles.skillProvenanceCard} padding="lg">
                <View style={[styles.evidenceCardHeader, isRTL && styles.rowRTL]}>
                  <View style={styles.evidenceHeaderIcon}>
                    <Ionicons
                      name="shield-checkmark-outline"
                      size={20}
                      color={colors.accent || colors.teal}
                    />
                  </View>

                  <View style={styles.evidenceHeaderText}>
                    <Text style={[styles.sectionTitle, isRTL && styles.rtlText]}>
                      {t(
                        'employerCandidateEvidence.skillsTitle',
                        'Skills Evidence'
                      )}
                    </Text>
                    <Text style={[styles.evidenceSubtitle, isRTL && styles.rtlText]}>
                      {t(
                        'employerCandidateEvidence.skillsSubtitle',
                        'CV evidence is separated from skills the candidate added to their profile.'
                      )}
                    </Text>
                  </View>
                </View>

                {cvEvidencedSkills.length > 0 ? (
                  <View style={styles.provenanceSection}>
                    <Text style={[styles.provenanceSectionTitle, isRTL && styles.rtlText]}>
                      {t(
                        'employerCandidateEvidence.cvEvidenceTitle',
                        'Evidenced in current CV'
                      )}
                    </Text>

                    <View style={[styles.provenanceSkillWrap, isRTL && styles.rowRTL]}>
                      {cvEvidencedSkills.map((item) => (
                        <View
                          key={`cv-evidence-${item.name}`}
                          style={styles.cvEvidenceChip}
                        >
                          <Ionicons
                            name="checkmark-circle"
                            size={14}
                            color={colors.success || '#10B981'}
                          />

                          <Text style={[styles.cvEvidenceText, isRTL && styles.rtlText]}>
                            {item.name}
                          </Text>

                          {item.self_declared === true ? (
                            <Text style={styles.bothSourcesLabel}>
                              {t(
                                'employerCandidateEvidence.alsoProfile',
                                'CV + profile'
                              )}
                            </Text>
                          ) : null}
                        </View>
                      ))}
                    </View>
                  </View>
                ) : (
                  <Text style={[styles.evidenceEmptyText, isRTL && styles.rtlText]}>
                    {t(
                      'employerCandidateEvidence.noCVEvidence',
                      'No skill evidence is currently available from the uploaded CV.'
                    )}
                  </Text>
                )}

                {selfDeclaredOnlySkills.length > 0 ? (
                  <View style={styles.provenanceSection}>
                    <Text style={[styles.provenanceSectionTitle, isRTL && styles.rtlText]}>
                      {t(
                        'employerCandidateEvidence.selfDeclaredTitle',
                        'Self-declared — not evidenced in current CV'
                      )}
                    </Text>

                    <View style={[styles.provenanceSkillWrap, isRTL && styles.rowRTL]}>
                      {selfDeclaredOnlySkills.map((item) => (
                        <View
                          key={`self-declared-${item.name}`}
                          style={styles.selfDeclaredChip}
                        >
                          <Ionicons
                            name="person-outline"
                            size={14}
                            color={colors.warning || '#D97706'}
                          />
                          <Text style={[styles.selfDeclaredText, isRTL && styles.rtlText]}>
                            {item.name}
                          </Text>
                        </View>
                      ))}
                    </View>
                  </View>
                ) : null}

                {legacyUnknownSkills.length > 0 ? (
                  <View style={styles.provenanceSection}>
                    <Text style={[styles.provenanceSectionTitle, isRTL && styles.rtlText]}>
                      {t(
                        'employerCandidateEvidence.legacyTitle',
                        'Historical skills — CV source not yet confirmed'
                      )}
                    </Text>

                    <View style={[styles.provenanceSkillWrap, isRTL && styles.rowRTL]}>
                      {legacyUnknownSkills.map((item) => (
                        <View
                          key={`legacy-skill-${item.name}`}
                          style={styles.legacySkillChip}
                        >
                          <Ionicons
                            name="help-circle-outline"
                            size={14}
                            color={colors.textSecondary || colors.textMuted}
                          />
                          <Text style={[styles.legacySkillText, isRTL && styles.rtlText]}>
                            {item.name}
                          </Text>
                        </View>
                      ))}
                    </View>
                  </View>
                ) : null}

                <Text style={[styles.evidenceFootnote, isRTL && styles.rtlText]}>
                  {t(
                    'employerCandidateEvidence.evidenceFootnote',
                    'Not appearing in a CV does not prove a candidate lacks a skill. Use this evidence together with the full application.'
                  )}
                </Text>
              </Card>
            </Reveal>

            {/* Sequence 4: Generated Cover Letter */}
            <Reveal delay={90}>
              <Card style={styles.letterCard} padding="lg">
                <View style={[styles.letterHeader, isRTL && styles.rowRTL]}>
                  <Ionicons
                    name="document-text-outline"
                    size={20}
                    color={colors.accent || colors.teal}
                    style={isRTL ? styles.iconRTL : styles.iconLTR}
                  />
                  <Text style={[styles.sectionTitle, isRTL && styles.rtlText]}>
                    {t('employerApplicantDetail.coverLetterTitle')}
                  </Text>
                </View>

                {applicant.generated_cover_letter ? (
                  <Text style={[styles.letterBody, isRTL && styles.rtlWriting]}>
                    {applicant.generated_cover_letter}
                  </Text>
                ) : (
                  <Text style={[styles.emptyText, isRTL && styles.rtlText]}>
                    {t('employerApplicantDetail.noCoverLetter')}
                  </Text>
                )}
              </Card>
            </Reveal>
          </>
        )}

        <EmployerCandidateIntelligence
          internshipId={internshipId}
          applicationId={applicationId}
          navigation={navigation}
          isRTL={isRTL}
        />

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
    gap: spacing.sm,
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
  overviewCard: {
    marginBottom: spacing.xs,
  },
  overviewHeader: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  candidateAvatarCircle: {
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: colors.accentSoft || '#E6F4F6',
    alignItems: 'center',
    justifyContent: 'center',
    marginEnd: spacing.md,
  },
  overviewInfo: {
    flex: 1,
  },
  candidateFullName: {
    ...typography.cardTitle,
    fontSize: 18,
    color: colors.textPrimary || colors.textDark,
  },
  headlineText: {
    ...typography.caption,
    color: colors.textSecondary || colors.textMuted,
    marginTop: 2,
  },
  departmentText: {
    ...typography.caption,
    color: colors.accentStrong || colors.tealDark,
    fontWeight: '600',
    marginTop: 2,
  },
  matchScoreRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: spacing.md,
    paddingTop: spacing.sm,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.borderSubtle || colors.border,
  },
  matchScoreLabel: {
    ...typography.label,
    fontSize: 13,
    color: colors.textSecondary || colors.textMuted,
  },
  aiRankingCard: {
    marginBottom: spacing.xs,
  },
  aiRankingHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    marginBottom: spacing.md,
  },
  aiRankingIcon: {
    width: 36,
    height: 36,
    borderRadius: 18,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.accentSoft || '#E6F4F6',
  },
  aiRankingHeaderText: {
    flex: 1,
  },
  aiRankingSubtitle: {
    ...typography.caption,
    color: colors.textSecondary || colors.textMuted,
  },
  aiRankingSection: {
    marginTop: spacing.sm,
  },
  aiRankingLabel: {
    ...typography.caption,
    fontWeight: '700',
    color: colors.textPrimary || colors.textDark,
    marginBottom: spacing.xs,
  },
  aiRankingGapText: {
    ...typography.body,
    fontSize: 13,
    color: colors.textSecondary || colors.textMuted,
    lineHeight: 19,
  },
  aiRankingDisclaimer: {
    ...typography.caption,
    color: colors.textTertiary || colors.textMuted,
    marginTop: spacing.md,
    lineHeight: 17,
  },
  metaCard: {
    marginBottom: spacing.xs,
  },
  sectionTitle: {
    ...typography.label,
    fontSize: 14,
    fontWeight: '700',
    color: colors.textPrimary || colors.textDark,
    marginBottom: spacing.xs,
  },
  statusRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: spacing.xs,
  },
  statusPill: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
    borderRadius: spacing.radii.pill,
  },
  statusPillText: {
    ...typography.badge,
    fontSize: 12,
    fontWeight: '700',
    textTransform: 'capitalize',
  },
  appliedDateText: {
    ...typography.caption,
    color: colors.textSecondary || colors.textMuted,
  },
  actionsDivider: {
    height: StyleSheet.hairlineWidth,
    backgroundColor: colors.borderSubtle || colors.border,
    marginVertical: spacing.md,
  },
  actionsHeading: {
    ...typography.label,
    fontSize: 13,
    fontWeight: '700',
    color: colors.textSecondary || colors.textMuted,
    marginBottom: spacing.sm,
  },
  actionLoadingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: spacing.sm,
    gap: spacing.sm,
  },
  actionLoadingText: {
    ...typography.caption,
    color: colors.textSecondary || colors.textMuted,
  },
  actionButtonsCol: {
    gap: spacing.sm,
  },
  primaryActionBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.accent || colors.teal,
    paddingVertical: spacing.sm + 2,
    paddingHorizontal: spacing.md,
    borderRadius: spacing.radii.sm,
    minHeight: spacing.minimumTouchTarget,
    gap: spacing.xs,
  },
  primaryActionBtnText: {
    ...typography.button,
    color: colors.textInverse || colors.white,
    fontSize: 14,
  },
  secondaryActionRow: {
    flexDirection: 'row',
    gap: spacing.sm,
  },
  acceptBtn: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#ECFDF5',
    borderWidth: 1,
    borderColor: '#A7F3D0',
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.sm,
    borderRadius: spacing.radii.sm,
    minHeight: spacing.minimumTouchTarget,
    gap: 4,
  },
  acceptBtnText: {
    ...typography.button,
    color: '#065F46',
    fontSize: 13,
  },
  rejectBtn: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#FEF2F2',
    borderWidth: 1,
    borderColor: '#FECACA',
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.sm,
    borderRadius: spacing.radii.sm,
    minHeight: spacing.minimumTouchTarget,
    gap: 4,
  },
  rejectBtnText: {
    ...typography.button,
    color: '#991B1B',
    fontSize: 13,
  },
  interviewingBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#FFFBEB',
    borderWidth: 1,
    borderColor: '#FDE68A',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: spacing.radii.sm,
    gap: spacing.xs,
  },
  interviewingBannerText: {
    flex: 1,
    ...typography.caption,
    color: '#92400E',
    fontWeight: '600',
  },
  terminalBannerAccepted: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#ECFDF5',
    borderWidth: 1,
    borderColor: '#A7F3D0',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.md,
    borderRadius: spacing.radii.sm,
    gap: spacing.sm,
  },
  terminalBannerRejected: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#FEF2F2',
    borderWidth: 1,
    borderColor: '#FECACA',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.md,
    borderRadius: spacing.radii.sm,
    gap: spacing.sm,
  },
  terminalBannerTextCol: {
    flex: 1,
  },
  terminalAcceptedTitle: {
    ...typography.label,
    fontSize: 14,
    fontWeight: '700',
    color: '#065F46',
  },
  terminalRejectedTitle: {
    ...typography.label,
    fontSize: 14,
    fontWeight: '700',
    color: '#991B1B',
  },
  terminalSubtitle: {
    ...typography.caption,
    color: colors.textSecondary || colors.textMuted,
    marginTop: 2,
  },
  skillsCard: {
    marginBottom: spacing.xs,
  },
  skillsChipRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    marginTop: spacing.xs,
  },
  letterCard: {
    marginBottom: spacing.md,
  },
  letterHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: spacing.sm,
  },
  letterBody: {
    ...typography.bodySecondary,
    fontSize: 14,
    lineHeight: 22,
    color: colors.textPrimary || colors.textDark,
  },
  emptyText: {
    ...typography.caption,
    color: colors.textTertiary || colors.textMuted,
    fontStyle: 'italic',
    marginTop: spacing.xs,
  },
  iconLTR: {
    marginEnd: spacing.xs,
  },
  iconRTL: {
    marginStart: spacing.xs,
  },
  employerMatchExplanationCard: {
    marginBottom: spacing.md,
  },
  explanationHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing.sm,
  },
  explanationTitleBlock: {
    flex: 1,
  },
  explanationSubtitle: {
    ...typography.caption,
    color: colors.textSecondary || colors.textMuted,
    marginTop: spacing.xxs,
    lineHeight: 18,
  },
  scoreBreakdown: {
    marginTop: spacing.md,
    gap: spacing.xs,
  },
  scoreBreakdownRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.borderSubtle || colors.border,
    paddingTop: spacing.xs,
  },
  scoreBreakdownLabelBlock: {
    flex: 1,
    marginEnd: spacing.sm,
  },
  scoreBreakdownLabel: {
    ...typography.label,
    color: colors.textPrimary || colors.textDark,
    fontSize: 13,
  },
  scoreBreakdownWeight: {
    ...typography.caption,
    color: colors.textTertiary || colors.textMuted,
    fontSize: 11,
    marginTop: 1,
  },
  scoreBreakdownValue: {
    ...typography.cardTitle,
    color: colors.accentStrong || colors.tealDark,
    fontSize: 15,
  },
  skillsEvidenceBlock: {
    marginTop: spacing.md,
    gap: spacing.sm,
  },
  skillEvidenceSection: {
    gap: spacing.xs,
  },
  skillEvidenceTitle: {
    ...typography.label,
    color: colors.textSecondary || colors.textMuted,
    fontSize: 12,
  },
  skillChipWrap: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.xs,
  },
  matchingSkillChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: spacing.sm,
    paddingVertical: 5,
    borderRadius: spacing.radii.pill,
    backgroundColor: colors.successSoft || '#ECFDF5',
  },
  matchingSkillText: {
    ...typography.caption,
    color: colors.textPrimary || colors.textDark,
    fontSize: 12,
  },
  missingSkillChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: spacing.sm,
    paddingVertical: 5,
    borderRadius: spacing.radii.pill,
    backgroundColor: colors.warningSoft || '#FEF3C7',
  },
  missingSkillText: {
    ...typography.caption,
    color: colors.textPrimary || colors.textDark,
    fontSize: 12,
  },
  explanationFootnote: {
    ...typography.caption,
    color: colors.textTertiary || colors.textMuted,
    fontSize: 11,
    lineHeight: 16,
    marginTop: spacing.md,
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
  interviewFormCard: {
    backgroundColor: colors.surfaceMuted || '#F8FAFC',
    borderWidth: 1,
    borderColor: colors.border || '#E2E8F0',
    borderRadius: spacing.radii?.md || 12,
    padding: spacing.md,
    marginBottom: spacing.md,
    gap: spacing.sm,
  },
  interviewFormHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing.sm,
  },
  interviewFormTitleWrap: {
    flex: 1,
  },
  interviewFormTitle: {
    ...typography.bodyMedium,
    fontWeight: '700',
    color: colors.textPrimary || colors.textDark,
  },
  interviewFormSubtitle: {
    ...typography.caption,
    color: colors.textSecondary || colors.textMuted,
    marginTop: 2,
  },
  interviewFieldLabel: {
    ...typography.caption,
    fontWeight: '600',
    color: colors.textSecondary || colors.textMuted,
    marginTop: spacing.xs,
  },
  interviewModeRow: {
    flexDirection: 'row',
    gap: spacing.sm,
  },
  interviewModeButton: {
    flex: 1,
    minHeight: spacing.minimumTouchTarget,
    borderWidth: 1,
    borderColor: colors.border || '#E2E8F0',
    borderRadius: spacing.radii?.sm || 8,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    backgroundColor: colors.surface || colors.white,
  },
  interviewModeButtonActive: {
    backgroundColor: colors.accent || colors.teal,
    borderColor: colors.accent || colors.teal,
  },
  interviewModeButtonText: {
    ...typography.caption,
    fontWeight: '600',
    color: colors.textSecondary || colors.textMuted,
  },
  interviewModeButtonTextActive: {
    color: colors.textInverse || colors.white,
  },
  interviewDateTimeRow: {
    flexDirection: 'row',
    gap: spacing.sm,
  },
  interviewDateTimeField: {
    flex: 1,
  },
  interviewInput: {
    minHeight: spacing.minimumTouchTarget,
    borderWidth: 1,
    borderColor: colors.border || '#E2E8F0',
    borderRadius: spacing.radii?.sm || 8,
    backgroundColor: colors.surface || colors.white,
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.sm,
    color: colors.textPrimary || colors.textDark,
    ...typography.body,
  },
  interviewMessageInput: {
    minHeight: 92,
  },
  interviewFormActions: {
    flexDirection: 'row',
    gap: spacing.sm,
    marginTop: spacing.xs,
  },
  interviewCancelButton: {
    flex: 1,
    minHeight: spacing.minimumTouchTarget,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: colors.border || '#E2E8F0',
    borderRadius: spacing.radii?.sm || 8,
    backgroundColor: colors.surface || colors.white,
  },
  interviewCancelButtonText: {
    ...typography.button,
    color: colors.textSecondary || colors.textMuted,
  },
  interviewScheduleButton: {
    flex: 2,
    minHeight: spacing.minimumTouchTarget,
    alignItems: 'center',
    justifyContent: 'center',
    flexDirection: 'row',
    gap: 6,
    borderRadius: spacing.radii?.sm || 8,
    backgroundColor: colors.accent || colors.teal,
  },
  interviewScheduleButtonText: {
    ...typography.button,
    color: colors.textInverse || colors.white,
  },
  rescheduleButton: {
    minHeight: spacing.minimumTouchTarget,
    borderWidth: 1,
    borderColor: colors.accent || colors.teal,
    borderRadius: spacing.radii?.sm || 8,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    marginBottom: spacing.sm,
  },
  rescheduleButtonText: {
    ...typography.button,
    color: colors.accent || colors.teal,
  },
  rtlInput: {
    textAlign: 'right',
  },

  documentsCard: {
    marginBottom: spacing.xs,
  },
  skillProvenanceCard: {
    marginBottom: spacing.xs,
  },
  evidenceCardHeader: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    marginBottom: spacing.md,
  },
  evidenceHeaderIcon: {
    width: 36,
    height: 36,
    borderRadius: 18,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.accentSoft || '#E6F4F6',
    marginEnd: spacing.sm,
  },
  evidenceHeaderText: {
    flex: 1,
  },
  evidenceSubtitle: {
    ...typography.caption,
    color: colors.textSecondary || colors.textMuted,
    lineHeight: 18,
  },
  viewCVButton: {
    minHeight: spacing.minimumTouchTarget,
    borderRadius: spacing.radii.sm,
    backgroundColor: colors.accent || colors.teal,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.xs,
  },
  viewCVButtonDisabled: {
    opacity: 0.7,
  },
  viewCVButtonText: {
    ...typography.button,
    color: colors.textInverse || colors.white,
  },
  secureAccessNote: {
    ...typography.caption,
    color: colors.textTertiary || colors.textMuted,
    lineHeight: 17,
    marginTop: spacing.sm,
  },
  provenanceSection: {
    marginTop: spacing.sm,
  },
  provenanceSectionTitle: {
    ...typography.label,
    fontSize: 13,
    fontWeight: '700',
    color: colors.textPrimary || colors.textDark,
    marginBottom: spacing.xs,
  },
  provenanceSkillWrap: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.xs,
  },
  cvEvidenceChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    borderRadius: spacing.radii.pill,
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xs,
    backgroundColor: colors.successSoft || '#DCFCE7',
  },
  cvEvidenceText: {
    ...typography.caption,
    fontWeight: '600',
    color: '#065F46',
  },
  bothSourcesLabel: {
    ...typography.caption,
    fontSize: 10,
    fontWeight: '700',
    color: '#047857',
  },
  selfDeclaredChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    borderRadius: spacing.radii.pill,
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xs,
    backgroundColor: colors.warningSoft || '#FEF3C7',
  },
  selfDeclaredText: {
    ...typography.caption,
    fontWeight: '600',
    color: '#92400E',
  },
  evidenceEmptyText: {
    ...typography.caption,
    color: colors.textSecondary || colors.textMuted,
    lineHeight: 18,
  },
  evidenceFootnote: {
    ...typography.caption,
    color: colors.textTertiary || colors.textMuted,
    lineHeight: 17,
    marginTop: spacing.md,
  },
  legacySkillChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    borderRadius: spacing.radii.pill,
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xs,
    backgroundColor: colors.surfaceMuted || '#F3F4F6',
  },
  legacySkillText: {
    ...typography.caption,
    fontWeight: '600',
    color: colors.textSecondary || colors.textMuted,
  },
});
