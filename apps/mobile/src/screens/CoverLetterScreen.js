import React, { useRef, useState } from 'react';
import {
  View,
  Text,
  TextInput,
  StyleSheet,
  TouchableOpacity,
  KeyboardAvoidingView,
  Platform,
  Alert,
  ActivityIndicator,
  ScrollView,
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
import { submitApplication, updateApplicationStatus, ApiError } from '../services/api';
import haptics from '../services/haptics';

export default function CoverLetterScreen({ route, navigation }) {
  const { t } = useTranslation();
  const applicationId = route?.params?.applicationId;
  const initialDraft = route?.params?.draft ?? '';
  const initialStatus = route?.params?.currentStatus ?? 'saved';
  const companyName = route?.params?.companyName;
  const jobTitle = route?.params?.jobTitle;

  const [text, setText] = useState(initialDraft);
  const [currentStatus, setCurrentStatus] = useState(initialStatus);
  const [isUpdating, setIsUpdating] = useState(false);
  const [updateError, setUpdateError] = useState(null);
  const submitInFlightRef = useRef(false);

  const handleSubmitApplication = async () => {
    if (!applicationId) {
      Alert.alert(
        t('coverLetter.missingRefTitle', 'Missing Reference'),
        t('coverLetter.missingRefMsg', 'Application reference not found.')
      );
      return;
    }

    if (submitInFlightRef.current || isUpdating) {
      return;
    }

    submitInFlightRef.current = true;
    setIsUpdating(true);
    setUpdateError(null);

    try {
      const updated = await submitApplication(applicationId, {
        cover_letter: text,
      });

      haptics.success();
      setCurrentStatus(updated.status || 'applied');

      Alert.alert(
        t('coverLetter.submittedSuccessTitle', 'Application Submitted'),
        t('coverLetter.submittedSuccessMsg', 'Your application and reviewed cover letter have been sent to the employer.'),
        [
          {
            text: t('coverLetter.goToApplications', 'View Applications'),
            onPress: () =>
              navigation.navigate('MainTabs', { screen: 'Applications' }),
          },
          { text: t('coverLetter.stayHere', 'OK'), style: 'cancel' },
        ]
      );
    } catch (err) {
      console.warn('Failed to submit application:', err);
      setUpdateError('APPLICATION_SUBMIT_FAILED');
      const msg = err instanceof ApiError && err.data?.detail
        ? err.data.detail
        : t('errors.applicationStatusUpdateFailed', 'Failed to submit application. Please try again.');
      Alert.alert(t('common.error', 'Error'), msg);
    } finally {
      submitInFlightRef.current = false;
      setIsUpdating(false);
    }
  };

  const statusLabel = t(`applications.statuses.${currentStatus}`, { defaultValue: currentStatus });

  return (
    <ScreenContainer edges={['top', 'bottom']}>
      <ScreenHeader
        title={t('coverLetter.title')}
        showBack={true}
        navigation={navigation}
      />

      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={styles.flex}
      >
        <ScrollView
          style={styles.screen}
          contentContainerStyle={styles.content}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          {/* Role & Company Header */}
          {(jobTitle || companyName) && (
            <Card style={styles.roleCard} padding="md">
              <Text style={styles.roleTitle}>{jobTitle || t('applications.defaultJobTitle')}</Text>
              {companyName ? (
                <Text style={styles.companyName}>{companyName}</Text>
              ) : null}
            </Card>
          )}

          {/* Tracker Status Pill */}
          <View style={styles.statusRow}>
            <Text style={styles.statusHeading}>{t('coverLetter.trackerStatus')}</Text>
            <View
              style={[
                styles.statusPill,
                currentStatus === 'applied' && styles.statusPillApplied,
                currentStatus === 'interviewing' && styles.statusPillInterviewing,
                currentStatus === 'accepted' && styles.statusPillAccepted,
              ]}
            >
              <Text
                style={[
                  styles.statusPillText,
                  currentStatus === 'applied' && styles.statusTextApplied,
                  currentStatus === 'interviewing' && styles.statusTextInterviewing,
                  currentStatus === 'accepted' && styles.statusTextAccepted,
                ]}
              >
                {statusLabel}
              </Text>
            </View>
          </View>

          {/* Notice on Edit Semantics */}
          <View style={styles.noticeBox}>
            <Ionicons
              name="information-circle-outline"
              size={16}
              color={colors.accentStrong || colors.tealDark}
              style={styles.noticeIcon}
            />
            <Text style={styles.noticeText}>
              {t('coverLetter.notice')}
            </Text>
          </View>

          {/* Editable Cover Letter Input */}
          <Card style={styles.draftCard} padding="md">
            <TextInput
              style={styles.input}
              value={text}
              onChangeText={setText}
              multiline
              textAlignVertical="top"
              placeholder={t('coverLetter.placeholder')}
              placeholderTextColor={colors.textTertiary || colors.textMuted}
            />
          </Card>

          {updateError && (
            <Text style={styles.errorBanner}>{t('errors.applicationStatusUpdateFailed')}</Text>
          )}

          {/* Actions */}
          {currentStatus === 'saved' ? (
            <View style={styles.actionContainer}>
              {isUpdating ? (
                <ActivityIndicator
                  size="small"
                  color={colors.accent || colors.teal}
                  style={{ marginTop: spacing.lg }}
                  accessibilityRole="progressbar"
                  accessibilityLabel={t('coverLetter.submitApplication', 'Submit Application')}
                />
              ) : (
                <GradientButton
                  title={t('coverLetter.submitApplication', 'Submit Application')}
                  color={colors.accent || colors.teal}
                  onPress={handleSubmitApplication}
                  style={{ marginTop: spacing.lg }}
                />
              )}
            </View>
          ) : (
            <View style={styles.actionContainer}>
              <TouchableOpacity
                style={styles.trackerBtn}
                onPress={() =>
                  navigation.navigate('MainTabs', { screen: 'Applications' })
                }
                accessibilityRole="button"
                accessibilityLabel={t('coverLetter.viewInTracker')}
              >
                <Ionicons
                  name="list-outline"
                  size={16}
                  color={colors.accentStrong || colors.tealDark}
                  style={styles.trackerIcon}
                />
                <Text style={styles.trackerBtnText}>
                  {t('coverLetter.viewInTracker')}
                </Text>
              </TouchableOpacity>
            </View>
          )}
        </ScrollView>
      </KeyboardAvoidingView>
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  flex: {
    flex: 1,
  },
  screen: {
    flex: 1,
    backgroundColor: colors.background || colors.screenBg,
  },
  content: {
    paddingHorizontal: spacing.screenHorizontalPadding,
    paddingTop: spacing.xs,
    paddingBottom: spacing.xxxl,
  },
  roleCard: {
    marginBottom: spacing.md,
  },
  roleTitle: {
    ...typography.cardTitle,
    color: colors.textPrimary || colors.textDark,
  },
  companyName: {
    ...typography.caption,
    color: colors.textSecondary || colors.textMuted,
    marginTop: spacing.xxs,
  },
  statusRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: spacing.md,
  },
  statusHeading: {
    ...typography.eyebrow,
    color: colors.textSecondary || colors.textMuted,
    marginEnd: spacing.sm,
  },
  statusPill: {
    backgroundColor: colors.surfaceMuted || '#F1F5F9',
    paddingHorizontal: spacing.sm + 2,
    paddingVertical: spacing.xxs + 1,
    borderRadius: spacing.radii.sm,
  },
  statusPillApplied: {
    backgroundColor: colors.infoSoft || '#E0F2FE',
  },
  statusPillInterviewing: {
    backgroundColor: colors.warningSoft || '#FEF3C7',
  },
  statusPillAccepted: {
    backgroundColor: colors.successSoft || '#DCFCE7',
  },
  statusPillText: {
    ...typography.badge,
    fontSize: 11,
    color: colors.textSecondary || colors.textMuted,
  },
  statusTextApplied: {
    color: colors.info || '#0369A1',
  },
  statusTextInterviewing: {
    color: colors.warning || '#B45309',
  },
  statusTextAccepted: {
    color: colors.success || '#15803D',
  },
  noticeBox: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    backgroundColor: colors.accentSoft || '#E6F4F6',
    borderRadius: spacing.radii.sm,
    padding: spacing.md,
    marginBottom: spacing.md,
  },
  noticeIcon: {
    marginEnd: spacing.xs,
    marginTop: spacing.xxs,
  },
  noticeText: {
    flex: 1,
    ...typography.caption,
    color: colors.accentStrong || colors.tealDark,
    lineHeight: 18,
  },
  draftCard: {
    minHeight: 260,
    borderWidth: 1.5,
    borderColor: colors.accent || colors.teal,
  },
  input: {
    ...typography.body,
    color: colors.textPrimary || colors.textDark,
    lineHeight: 22,
    flex: 1,
  },
  errorBanner: {
    ...typography.caption,
    color: colors.danger || '#EF4444',
    textAlign: 'center',
    marginTop: spacing.sm,
  },
  actionContainer: {
    marginTop: spacing.xs,
  },
  trackerBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: spacing.md,
    backgroundColor: colors.accentSoft || '#E6F4F6',
    borderRadius: spacing.radii.md,
    minHeight: spacing.minimumTouchTarget,
  },
  trackerBtnText: {
    ...typography.button,
    color: colors.accentStrong || colors.tealDark,
    fontSize: 14,
  },
  trackerIcon: {
    marginEnd: spacing.xs,
  },
});
