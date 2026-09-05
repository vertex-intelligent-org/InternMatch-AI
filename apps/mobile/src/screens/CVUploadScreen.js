import React, { useEffect, useRef, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ScrollView,
  Alert,
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
import GradientButton from '../components/GradientButton';
import BrandedAILoader from '../components/motion/BrandedAILoader';
import * as DocumentPicker from 'expo-document-picker';
import {
  uploadCV,
  getProcessingJob,
  confirmCVReplacement,
  cancelCVAnalysis,
  ApiError,
} from '../services/api';
import { useProfile } from '../context/ProfileContext';
import haptics from '../services/haptics';
import { useSubscription } from '../context/SubscriptionProvider';

const MAX_POLL_DURATION_MS = 210000; // 210s: allow background CV extraction to complete before hard timeout
const POLL_INTERVAL_MS = 1500;

const CV_JOB_ERROR_CODES = {
  'The uploaded document does not appear to be a valid CV or resume. Please upload a valid resume.':
    'CV_INVALID_DOCUMENT',
  "We couldn't read the uploaded document. Please make sure the file is not corrupted and is a valid PDF or DOCX file.":
    'CV_UNREADABLE_DOCUMENT',
};

const getCVJobErrorCode = (jobError) =>
  typeof jobError === 'string' && CV_JOB_ERROR_CODES[jobError]
    ? CV_JOB_ERROR_CODES[jobError]
    : 'CV_EXTRACTION_FAILED';

export default function CVUploadScreen({ route, navigation }) {
  const { t } = useTranslation();
  const {
    aiUsage,
    refreshAIUsage,
  } = useSubscription();

  const cvAnalysisUsage =
    aiUsage?.features?.find(
      (feature) =>
        feature.feature_key ===
        'cv_analysis'
    );

  const isCVAnalysisExhausted =
    cvAnalysisUsage?.remaining === 0;
  const [selectedFile, setSelectedFile] = useState(null);
  const [status, setStatus] = useState('idle'); // 'idle' | 'uploading' | 'queued' | 'processing' | 'pending_confirmation' | 'completed' | 'failed' | 'timeout'
  const [progressPercent, setProgressPercent] = useState(0);
  const [errorMessage, setErrorMessage] = useState(null);
  const [jobId, setJobId] = useState(null);
  const [isConfirming, setIsConfirming] = useState(false);
  const [isCancelling, setIsCancelling] = useState(false);

  const { profile, refreshProfile } = useProfile();
  const hasExistingCV = Boolean(profile?.cv_url || (profile?.skills && profile.skills.length > 0));

  const pollTimerRef = useRef(null);
  const isMountedRef = useRef(true);
  const isPollingRef = useRef(false);
  const confirmInFlightRef = useRef(false);
  const cancelInFlightRef = useRef(false);
  const cancelledJobIdRef = useRef(null);
  const startTimeRef = useRef(0);
  const visualProgressTimerRef = useRef(null);
  const visualProgressTickRef = useRef(0);

  const clearPolling = () => {
    if (pollTimerRef.current) {
      clearTimeout(pollTimerRef.current);
      pollTimerRef.current = null;
    }
    isPollingRef.current = false;
  };

  const clearVisualProgress = () => {
    if (visualProgressTimerRef.current) {
      clearInterval(visualProgressTimerRef.current);
      visualProgressTimerRef.current = null;
    }
    visualProgressTickRef.current = 0;
  };

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
      clearPolling();
      clearVisualProgress();
    };
  }, []);

  useEffect(() => {
    clearVisualProgress();

    if (status !== 'queued' && status !== 'processing') {
      return undefined;
    }

    visualProgressTimerRef.current = setInterval(() => {
      if (!isMountedRef.current) return;

      visualProgressTickRef.current += 1;
      const tick = visualProgressTickRef.current;

      setProgressPercent((current) => {
        // 100% is reserved exclusively for confirmed backend completion.
        if (current >= 94) return current;

        // Move quickly at first, then progressively slow down as the
        // operation approaches its visual waiting ceiling.
        if (current < 35) {
          return Math.min(35, current + 2);
        }

        if (current < 65) {
          return Math.min(65, current + 1);
        }

        if (current < 80) {
          return tick % 2 === 0 ? Math.min(80, current + 1) : current;
        }

        if (current < 90) {
          return tick % 3 === 0 ? Math.min(90, current + 1) : current;
        }

        return tick % 4 === 0 ? Math.min(94, current + 1) : current;
      });
    }, 400);

    return clearVisualProgress;
  }, [status]);

  const pickFileAndUpload = async () => {
    if (isCVAnalysisExhausted) {
      try {
        const latestUsage =
          await refreshAIUsage();

        const latestCVUsage =
          latestUsage?.features?.find(
            (feature) =>
              feature.feature_key ===
              'cv_analysis'
          );

        if (
          !latestCVUsage ||
          latestCVUsage.remaining === 0
        ) {
          navigation.navigate('Plans');
          return;
        }
      } catch (usageError) {
        console.warn(
          'AI usage refresh before CV analysis failed:',
          usageError
        );
        navigation.navigate('Plans');
        return;
      }
    }

    clearPolling();
    setErrorMessage(null);

    try {
      const result = await DocumentPicker.getDocumentAsync({
        type: [
          'application/pdf',
          'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        ],
        multiple: false,
        copyToCacheDirectory: true,
      });

      if (result.canceled || !result.assets || result.assets.length === 0) {
        return;
      }

      const fileAsset = result.assets[0];

      if (fileAsset.size && fileAsset.size > 10 * 1024 * 1024) {
        Alert.alert(t('cvUpload.fileTooLargeTitle'), t('cvUpload.fileTooLargeMsg'));
        return;
      }

      setSelectedFile(fileAsset);
      await startUploadAndPolling(fileAsset);
    } catch (err) {
      console.warn('Document picker error:', err);
      setErrorMessage('CV_PICKER_ERROR');
      setStatus('failed');
      haptics.error();
    }
  };

  const startUploadAndPolling = async (fileAsset) => {
    cancelledJobIdRef.current = null;
    setStatus('uploading');
    setProgressPercent(10);
    setErrorMessage(null);

    try {
      const uploadRes = await uploadCV({
        uri: fileAsset.uri,
        name: fileAsset.name,
        type: fileAsset.mimeType || 'application/pdf',
      });

      if (!isMountedRef.current) return;

      setJobId(uploadRes.job_id);
      setStatus('queued');
      setProgressPercent(15);
      startTimeRef.current = Date.now();

      scheduleNextPoll(uploadRes.job_id);
    } catch (err) {
      if (!isMountedRef.current) return;
      if (
        err?.status === 402 &&
        err?.code ===
          'AI_QUOTA_EXCEEDED'
      ) {
        setSelectedFile(null);
        setJobId(null);
        setProgressPercent(0);
        setErrorMessage(null);
        setStatus('idle');

        refreshAIUsage().catch(
          (usageError) => {
            console.warn(
              'AI usage refresh after CV quota response failed:',
              usageError
            );
          }
        );

        navigation.navigate('Plans');
        return;
      }

      console.warn('CV upload failed:', err);
      setErrorMessage('CV_UPLOAD_FAILED');
      setStatus('failed');
      haptics.error();
    }
  };

  const scheduleNextPoll = (activeJobId) => {
    clearPolling();
    if (!isMountedRef.current) return;

    pollTimerRef.current = setTimeout(() => {
      pollJobStatus(activeJobId);
    }, POLL_INTERVAL_MS);
  };

  const pollJobStatus = async (activeJobId) => {
    if (!isMountedRef.current || isPollingRef.current) return;

    if (Date.now() - startTimeRef.current > MAX_POLL_DURATION_MS) {
      setStatus('timeout');
      setErrorMessage('CV_TIMEOUT');
      clearPolling();
      return;
    }

    isPollingRef.current = true;

    try {
      const job = await getProcessingJob(activeJobId);

      if (
        !isMountedRef.current ||
        cancelledJobIdRef.current === activeJobId
      ) {
        return;
      }

      if (job.status === 'queued') {
        setStatus('queued');
        setProgressPercent((current) => {
          const confirmed = Math.max(15, Number(job.progress_percent) || 0);
          const ceiling = Math.min(20, confirmed + 5);

          if (current >= ceiling) return current;
          return Math.min(ceiling, current + 1);
        });
        isPollingRef.current = false;
        scheduleNextPoll(activeJobId);
      } else if (job.status === 'processing') {
        setStatus('processing');
        setProgressPercent((current) => {
          const confirmed = Math.max(15, Number(job.progress_percent) || 0);
          const ceiling = Math.min(94, confirmed + 8);

          // Progress never moves backwards. Between real backend checkpoints,
          // move gently inside a small bounded window so the UI stays alive.
          if (current >= ceiling) return current;

          const step = confirmed > current ? 6 : 2;
          return Math.min(ceiling, current + step);
        });
        isPollingRef.current = false;
        scheduleNextPoll(activeJobId);
      } else if (job.status === 'completed') {
        try {
          await refreshAIUsage();
        } catch (usageError) {
          console.warn(
            'AI usage refresh after CV completion failed:',
            usageError
          );
        }

        // Check requires_confirmation BEFORE normal completed success handling
        if (job.result && job.result.requires_confirmation === true) {
          clearPolling();
          setStatus('pending_confirmation');
          setProgressPercent(100);
          haptics.warning?.() || haptics.selection?.();
          return;
        }

        setProgressPercent(100);
        clearPolling();

        try {
          await refreshProfile();
        } catch (profileErr) {
          // The backend CV job already completed successfully. A temporary
          // local refresh failure must not misrepresent that success.
          console.warn('Profile refresh after CV completion failed:', profileErr);
        }

        if (isMountedRef.current) {
          setErrorMessage(null);
          setStatus('completed');
          haptics.success();
        }
      } else if (job.status === 'failed') {
        clearPolling();
        setStatus('failed');
        setProgressPercent(100);
        setErrorMessage(getCVJobErrorCode(job.error));
        haptics.error();
      }
    } catch (err) {
      if (!isMountedRef.current) return;
      console.warn('Polling error:', err);
      isPollingRef.current = false;

      if (err instanceof ApiError && err.status === 401) {
        setStatus('failed');
        setErrorMessage('UNAUTHENTICATED');
        haptics.error();
      } else {
        // Transient network failure; schedule retry
        scheduleNextPoll(activeJobId);
      }
    }
  };

  const handleConfirmReplacement = async () => {
    if (!jobId || confirmInFlightRef.current) return;

    // Ref guard is synchronous, unlike React state updates, so rapid taps
    // cannot start multiple confirmation requests in the same render cycle.
    confirmInFlightRef.current = true;
    setIsConfirming(true);

    try {
      await confirmCVReplacement(jobId);

      try {
        await refreshProfile();
      } catch (profileErr) {
        // Confirmation already succeeded on the backend. Do not tell the user
        // that confirmation failed just because the local refresh was transient.
        console.warn('Profile refresh after CV confirmation failed:', profileErr);
      }

      if (isMountedRef.current) {
        setErrorMessage(null);
        setStatus('completed');
        haptics.success();
      }
    } catch (err) {
      console.warn('Confirm CV replacement error:', err);
      if (isMountedRef.current) {
        setStatus('failed');
        setErrorMessage('CV_CONFIRMATION_FAILED');
        haptics.error();
      }
    } finally {
      confirmInFlightRef.current = false;
      if (isMountedRef.current) {
        setIsConfirming(false);
      }
    }
  };

  const resetAfterCancellation = (cancelledJobId) => {
    cancelledJobIdRef.current = cancelledJobId;
    clearPolling();
    clearVisualProgress();
    setStatus('idle');
    setProgressPercent(0);
    setErrorMessage(null);
    setSelectedFile(null);
    setJobId(null);
  };

  const handleCancelAnalysis = () => {
    if (!jobId || cancelInFlightRef.current || isCancelling) return;

    const activeJobId = jobId;

    Alert.alert(
      t('cvUpload.cancelAnalysisTitle'),
      t('cvUpload.cancelAnalysisMessage'),
      [
        {
          text: t('cvUpload.keepAnalyzing'),
          style: 'cancel',
        },
        {
          text: t('cvUpload.cancelAnalysis'),
          style: 'destructive',
          onPress: async () => {
            if (cancelInFlightRef.current) return;

            cancelInFlightRef.current = true;
            setIsCancelling(true);

            try {
              await cancelCVAnalysis(activeJobId);

              if (isMountedRef.current) {
                resetAfterCancellation(activeJobId);
                haptics.selection?.();
              }
            } catch (err) {
              console.warn('Cancel CV analysis error:', err);

              if (isMountedRef.current) {
                Alert.alert(
                  t('cvUpload.cancelFailedTitle'),
                  t('cvUpload.cancelFailedMessage')
                );
                haptics.error();
              }
            } finally {
              cancelInFlightRef.current = false;

              if (isMountedRef.current) {
                setIsCancelling(false);
              }
            }
          },
        },
      ]
    );
  };

  const handleStopPolling = () => {
    clearPolling();
    setStatus('idle');
    setProgressPercent(0);
    setErrorMessage(null);
    setSelectedFile(null);
  };

  const handleFinish = () => {
    if (route?.params?.origin === 'Home') {
      navigation.navigate('MainTabs', { screen: 'Home' });
    } else {
      navigation.goBack();
    }
  };

  const isWorking = status === 'uploading' || status === 'queued' || status === 'processing';
  const isAIProcessing = status === 'queued' || status === 'processing';

  return (
    <ScreenContainer edges={['top', 'bottom']}>
      <ScreenHeader
        title={hasExistingCV ? t('cvUpload.replaceTitle') : t('cvUpload.title')}
        showBack={true}
        navigation={navigation}
      />

      <ScrollView
        style={styles.screen}
        contentContainerStyle={styles.content}
        showsVerticalScrollIndicator={false}
      >
        <Text style={styles.subtitle}>
          {hasExistingCV ? t('cvUpload.replaceSubtitle') : t('cvUpload.subtitle')}
        </Text>

        {/* Upload Drop Zone */}
        {!isWorking && status !== 'completed' && status !== 'pending_confirmation' && (
          <View>
            <TouchableOpacity
              style={styles.dropZone}
              onPress={pickFileAndUpload}
              accessibilityRole="button"
              accessibilityLabel={hasExistingCV ? t('cvUpload.dropZoneReplace') : t('cvUpload.dropZoneDefault')}
              activeOpacity={0.7}
            >
              <Ionicons
                name="cloud-upload-outline"
                size={36}
                color={colors.accent || colors.teal}
              />
              <Text style={styles.dropText}>
                {selectedFile
                  ? selectedFile.name
                  : hasExistingCV
                  ? t('cvUpload.dropZoneReplace')
                  : t('cvUpload.dropZoneDefault')}
              </Text>
              <Text style={styles.dropHint}>{t('cvUpload.dropHint')}</Text>
            </TouchableOpacity>

            <Text style={styles.guidanceText}>
              {t('cvUpload.guidance')}
            </Text>
          </View>
        )}

        {/* In-Progress State */}
        {isWorking && (
          <Card style={styles.workingCard} padding="lg">
            <View style={styles.iconCircle}>
              <BrandedAILoader
                size={32}
                color={colors.accent || colors.teal}
                active={isAIProcessing}
              />
            </View>
            <Text style={styles.workingTitle}>
              {status === 'uploading'
                ? t('cvUpload.uploading')
                : status === 'queued'
                ? t('cvUpload.queued')
                : t('cvUpload.extracting')}
            </Text>
            <Text style={styles.workingFileName}>{selectedFile?.name}</Text>

            <View style={styles.progressTrack}>
              <View style={[styles.progressFill, { width: `${progressPercent}%` }]} />
            </View>
            <Text style={styles.percentText}>{progressPercent}%</Text>

            <Text style={styles.workingNotice}>
              {t('cvUpload.notice')}
            </Text>

            <TouchableOpacity
              style={styles.cancelBtn}
              onPress={handleCancelAnalysis}
              disabled={isCancelling}
              accessibilityRole="button"
              accessibilityLabel={t('cvUpload.cancelAnalysis')}
            >
              <Text style={styles.cancelText}>
                {isCancelling
                  ? t('cvUpload.cancellingAnalysis')
                  : t('cvUpload.cancelAnalysis')}
              </Text>
            </TouchableOpacity>


          </Card>
        )}

        {/* Identity Mismatch Pending Confirmation State */}
        {status === 'pending_confirmation' && (
          <Card style={styles.warningCard} padding="lg">
            <View style={styles.warningIconCircle}>
              <Ionicons
                name="alert-circle-outline"
                size={40}
                color={colors.warning || '#F59E0B'}
              />
            </View>
            <Text style={styles.warningTitle}>{t('cvUpload.mismatchTitle')}</Text>
            <Text style={styles.warningDescription}>
              {t('cvUpload.mismatchDescription')}
            </Text>
            <Text style={styles.warningHelper}>
              {t('cvUpload.mismatchHelper')}
            </Text>

            <GradientButton
              title={isConfirming ? t('common.loading') : t('cvUpload.mismatchConfirm')}
              color={colors.warning || '#F59E0B'}
              onPress={handleConfirmReplacement}
              disabled={isConfirming}
              style={{ marginTop: spacing.xl, width: '100%' }}
            />

            <TouchableOpacity
              style={styles.secondaryBtn}
              onPress={handleStopPolling}
              disabled={isConfirming}
              accessibilityRole="button"
              accessibilityLabel={t('cvUpload.mismatchCancel')}
            >
              <Text style={styles.secondaryBtnText}>{t('cvUpload.mismatchCancel')}</Text>
            </TouchableOpacity>
          </Card>
        )}

        {/* Completed Success State */}
        {status === 'completed' && (
          <Card variant="highlight" style={styles.successCard} padding="lg">
            <Ionicons
              name="checkmark-circle"
              size={48}
              color={colors.success || '#10B981'}
            />
            <Text style={styles.successTitle}>{t('cvUpload.successTitle')}</Text>
            <Text style={styles.successDescription}>
              {t('cvUpload.successDescription')}
            </Text>

            <GradientButton
              title={t('cvUpload.viewProfile')}
              color={colors.accent || colors.teal}
              onPress={() => navigation.navigate('MainTabs', { screen: 'Profile' })}
              style={{ marginTop: spacing.xl, width: '100%' }}
            />

            <TouchableOpacity
              style={styles.secondaryBtn}
              onPress={handleFinish}
              accessibilityRole="button"
              accessibilityLabel={t('cvUpload.backToDashboard')}
            >
              <Text style={styles.secondaryBtnText}>{t('cvUpload.backToDashboard')}</Text>
            </TouchableOpacity>
          </Card>
        )}

        {/* Failed / Error State */}
        {status === 'failed' && (
          <Card style={styles.errorCard} padding="lg">
            <Ionicons
              name="alert-circle"
              size={48}
              color={colors.danger || '#EF4444'}
            />
            <Text style={styles.errorTitle}>{t('cvUpload.errorTitle')}</Text>
            <Text style={styles.errorMessage}>
              {errorMessage === 'CV_TIMEOUT'
                ? t('cvUpload.timeoutMessage')
                : errorMessage === 'UNAUTHENTICATED'
                  ? t('errors.unauthenticated')
                  : errorMessage === 'CV_PICKER_ERROR'
                    ? t('cvUpload.errors.selectDoc', { defaultValue: t('cvUpload.errorTitle') })
                    : errorMessage === 'CV_INVALID_DOCUMENT'
                      ? t('cvUpload.errors.invalidDocument', { defaultValue: t('errors.cvUploadFailed') })
                      : errorMessage === 'CV_UNREADABLE_DOCUMENT'
                        ? t('cvUpload.errors.unreadableDocument', { defaultValue: t('errors.cvUploadFailed') })
                        : errorMessage === 'CV_EXTRACTION_FAILED'
                          ? t('cvUpload.errors.serverProcessingFailed', { defaultValue: t('errors.cvUploadFailed') })
                          : errorMessage === 'CV_CONFIRMATION_FAILED'
                            ? t('cvUpload.errors.confirmationFailed', { defaultValue: t('errors.cvUploadFailed') })
                        : errorMessage === 'PROFILE_REFRESH_FAILED'
                          ? t('cvUpload.errors.profileLoadFailed', { defaultValue: t('cvUpload.errorTitle') })
                          : t('errors.cvUploadFailed')}
            </Text>

            <GradientButton
              title={t('cvUpload.chooseAnother')}
              color={colors.primaryBlue}
              onPress={pickFileAndUpload}
              style={{ marginTop: spacing.xl, width: '100%' }}
            />
          </Card>
        )}

        {/* Timeout State */}
        {status === 'timeout' && (
          <Card style={styles.errorCard} padding="lg">
            <Ionicons
              name="time-outline"
              size={48}
              color={colors.warning || '#F59E0B'}
            />
            <Text style={styles.errorTitle}>{t('cvUpload.timeoutTitle')}</Text>
            <Text style={styles.errorMessage}>{t('cvUpload.timeoutMessage')}</Text>

            <GradientButton
              title={t('cvUpload.checkProfile')}
              color={colors.accent || colors.teal}
              onPress={() => navigation.navigate('MainTabs', { screen: 'Profile' })}
              style={{ marginTop: spacing.xl, width: '100%' }}
            />

            <TouchableOpacity
              style={styles.secondaryBtn}
              onPress={pickFileAndUpload}
              accessibilityRole="button"
              accessibilityLabel={t('cvUpload.uploadAgain')}
            >
              <Text style={styles.secondaryBtnText}>{t('cvUpload.uploadAgain')}</Text>
            </TouchableOpacity>
          </Card>
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
    paddingBottom: spacing.xxxl,
  },
  subtitle: {
    ...typography.caption,
    color: colors.textSecondary || colors.textMuted,
    textAlign: 'center',
    marginBottom: spacing.lg,
    lineHeight: 18,
  },
  dropZone: {
    borderWidth: 2,
    borderColor: colors.accent || colors.teal,
    borderStyle: 'dashed',
    borderRadius: spacing.radii.lg,
    paddingVertical: spacing.xxxl,
    paddingHorizontal: spacing.xl,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'rgba(255, 255, 255, 0.6)',
  },
  dropText: {
    marginTop: spacing.md,
    color: colors.textPrimary || colors.textDark,
    ...typography.bodyEmphasis,
    textAlign: 'center',
  },
  dropHint: {
    marginTop: spacing.xs,
    color: colors.textSecondary || colors.textMuted,
    ...typography.caption,
  },
  guidanceText: {
    ...typography.caption,
    color: colors.textSecondary || colors.textMuted,
    textAlign: 'center',
    marginTop: spacing.md,
    lineHeight: 18,
  },
  workingCard: {
    alignItems: 'center',
  },
  iconCircle: {
    width: 64,
    height: 64,
    borderRadius: 32,
    backgroundColor: colors.accentSoft || '#E6F4F6',
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: spacing.md,
  },
  workingTitle: {
    ...typography.cardTitle,
    color: colors.textPrimary || colors.textDark,
    textAlign: 'center',
  },
  workingFileName: {
    ...typography.caption,
    color: colors.textSecondary || colors.textMuted,
    marginTop: spacing.xs,
    marginBottom: spacing.md,
    textAlign: 'center',
  },
  progressTrack: {
    width: '100%',
    height: 6,
    borderRadius: 3,
    backgroundColor: colors.borderSubtle || '#E2E8F0',
    overflow: 'hidden',
  },
  progressFill: {
    height: 6,
    backgroundColor: colors.accent || colors.teal,
  },
  percentText: {
    ...typography.caption,
    fontWeight: '600',
    color: colors.accent || colors.teal,
    alignSelf: 'flex-end',
    marginTop: spacing.xs,
  },
  workingNotice: {
    ...typography.caption,
    color: colors.textSecondary || colors.textMuted,
    marginTop: spacing.md,
    textAlign: 'center',
    lineHeight: 18,
  },
  cancelBtn: {
    marginTop: spacing.lg,
    paddingVertical: spacing.xs,
    paddingHorizontal: spacing.md,
    minHeight: spacing.minimumTouchTarget,
    justifyContent: 'center',
  },
  cancelText: {
    ...typography.caption,
    color: colors.textSecondary || colors.textMuted,
    textDecorationLine: 'underline',
  },
  warningCard: {
    alignItems: 'center',
    borderColor: '#FDE68A',
    backgroundColor: '#FFFBEB',
  },
  warningIconCircle: {
    width: 64,
    height: 64,
    borderRadius: 32,
    backgroundColor: '#FEF3C7',
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: spacing.md,
  },
  warningTitle: {
    ...typography.cardTitle,
    fontSize: 18,
    color: '#92400E',
    textAlign: 'center',
    marginTop: spacing.xs,
  },
  warningDescription: {
    ...typography.body,
    fontSize: 14,
    color: '#78350F',
    textAlign: 'center',
    marginTop: spacing.sm,
    lineHeight: 20,
  },
  warningHelper: {
    ...typography.caption,
    color: '#92400E',
    textAlign: 'center',
    marginTop: spacing.md,
    lineHeight: 18,
  },
  successCard: {
    alignItems: 'center',
    borderColor: colors.success || '#10B981',
  },
  successTitle: {
    ...typography.cardTitle,
    fontSize: 18,
    color: colors.textPrimary || colors.textDark,
    marginTop: spacing.md,
  },
  successDescription: {
    ...typography.caption,
    color: colors.textSecondary || colors.textMuted,
    textAlign: 'center',
    marginTop: spacing.xs,
    lineHeight: 18,
  },
  errorCard: {
    alignItems: 'center',
    borderColor: colors.dangerSoft || '#FEE2E2',
    backgroundColor: '#FEF2F2',
  },
  errorTitle: {
    ...typography.cardTitle,
    fontSize: 18,
    color: colors.danger || '#EF4444',
    marginTop: spacing.md,
  },
  errorMessage: {
    ...typography.caption,
    color: colors.danger || '#EF4444',
    textAlign: 'center',
    marginTop: spacing.xs,
    lineHeight: 18,
  },
  secondaryBtn: {
    marginTop: spacing.md,
    paddingVertical: spacing.sm,
    alignItems: 'center',
    minHeight: spacing.minimumTouchTarget,
    justifyContent: 'center',
  },
  secondaryBtnText: {
    ...typography.button,
    color: colors.textPrimary || colors.textDark,
  },
});
