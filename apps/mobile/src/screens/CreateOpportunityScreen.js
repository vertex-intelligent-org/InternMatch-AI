import React, { useEffect, useState } from 'react';
import {
  View,
  Text,
  TextInput,
  StyleSheet,
  ScrollView,
  KeyboardAvoidingView,
  Platform,
  Alert,
} from 'react-native';
import { useTranslation } from 'react-i18next';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import colors from '../theme/colors';
import { spacing } from '../theme/spacing';
import { typography } from '../theme/typography';
import { useLocalization } from '../localization/LocalizationContext';
import ScreenContainer from '../components/ScreenContainer';
import ScreenHeader from '../components/ScreenHeader';
import Chip from '../components/Chip';
import Card from '../components/Card';
import GradientButton from '../components/GradientButton';
import haptics from '../services/haptics';
import {
  createEmployerInternship,
  getInternshipDetail,
  updateEmployerInternship,
  ApiError,
} from '../services/api';

const WORK_TYPES = [
  { id: 'remote' },
  { id: 'onsite' },
  { id: 'hybrid' },
];

function normalizeSkillsInput(rawText) {
  if (!rawText || typeof rawText !== 'string') return [];
  const parts = rawText
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean);

  const seen = new Set();
  const result = [];
  for (const part of parts) {
    const lower = part.toLowerCase();
    if (!seen.has(lower)) {
      seen.add(lower);
      result.push(part);
    }
  }
  return result;
}

export default function CreateOpportunityScreen({ navigation, route }) {
  const { t } = useTranslation();
  const { isRTL } = useLocalization();
  const insets = useSafeAreaInsets();
  const editingOpportunity = route?.params?.opportunity || null;
  const editingId =
    route?.params?.internshipId || editingOpportunity?.id || null;
  const isEditing = Boolean(editingId);

  const [title, setTitle] = useState(editingOpportunity?.title || '');
  const [company, setCompany] = useState(editingOpportunity?.company || '');
  const [location, setLocation] = useState(editingOpportunity?.location || '');
  const [workType, setWorkType] = useState(editingOpportunity?.work_type || 'hybrid');
  const [description, setDescription] = useState('');
  const [requiredSkills, setRequiredSkills] = useState((editingOpportunity?.required_skills || []).join(', '));
  const [preferredSkills, setPreferredSkills] = useState((editingOpportunity?.preferred_skills || []).join(', '));
  const [language, setLanguage] = useState('English');
  const [educationRequirements, setEducationRequirements] = useState('');
  const [experienceRequirements, setExperienceRequirements] = useState('');

  const [loadingExisting, setLoadingExisting] = useState(Boolean(editingId));
  const [submitting, setSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState(null);

  useEffect(() => {
    if (!editingId) {
      setLoadingExisting(false);
      return undefined;
    }

    let active = true;

    const loadExistingOpportunity = async () => {
      setLoadingExisting(true);
      setErrorMessage(null);

      try {
        const detail = await getInternshipDetail(editingId);

        if (!active) return;

        setTitle(detail.title || '');
        setCompany(detail.company || '');
        setLocation(detail.location || '');
        setWorkType(detail.work_type || 'hybrid');
        setDescription(detail.description || '');
        setRequiredSkills((detail.required_skills || []).join(', '));
        setPreferredSkills((detail.preferred_skills || []).join(', '));
        setLanguage(detail.languages?.[0] || 'English');
        setEducationRequirements(detail.min_education || '');
        setExperienceRequirements(detail.experience_requirements || '');
      } catch (err) {
        console.warn('Failed to load employer opportunity for editing:', err);

        if (active) {
          setErrorMessage(
            t(
              'createOpportunity.editLoadError',
              'Failed to load this opportunity for editing. Please try again.'
            )
          );
        }
      } finally {
        if (active) {
          setLoadingExisting(false);
        }
      }
    };

    loadExistingOpportunity();

    return () => {
      active = false;
    };
  }, [editingId, t]);

  const handleSubmit = async () => {
    setErrorMessage(null);

    const trimmedTitle = title.trim();
    const trimmedCompany = company.trim();
    const trimmedLocation = location.trim();
    const trimmedDescription = description.trim();

    if (!trimmedTitle || !trimmedCompany || !trimmedLocation || !trimmedDescription) {
      setErrorMessage(t('createOpportunity.validationError'));
      haptics.selection();
      return;
    }

    const payload = {
      title: trimmedTitle,
      company: trimmedCompany,
      location: trimmedLocation,
      work_type: workType,
      description: trimmedDescription,
      required_skills: normalizeSkillsInput(requiredSkills),
      preferred_skills: normalizeSkillsInput(preferredSkills),
      language: language.trim() || 'English',
      education_requirements: educationRequirements.trim() || null,
      experience_requirements: experienceRequirements.trim() || null,
    };

    setSubmitting(true);

    try {
      if (isEditing) {
        await updateEmployerInternship(editingId, payload);
      } else {
        await createEmployerInternship(payload);
      }
      haptics.success();

      Alert.alert(
        isEditing
          ? t('createOpportunity.editSuccessTitle', 'Opportunity Updated')
          : t('createOpportunity.successTitle'),
        isEditing
          ? t(
              'createOpportunity.editSuccessMessage',
              'Your opportunity has been updated successfully.'
            )
          : t('createOpportunity.successMessage'),
        [
          {
            text: 'OK',
            onPress: () => {
              if (navigation.canGoBack()) {
                navigation.goBack();
              } else {
                navigation.navigate('MainTabs', { screen: 'Opportunities' });
              }
            },
          },
        ]
      );
    } catch (err) {
      console.warn(
        isEditing
          ? 'Failed to update employer opportunity:'
          : 'Failed to publish employer opportunity:',
        err
      );
      if (err instanceof ApiError && err.status === 503) {
        setErrorMessage(t('createOpportunity.error503'));
      } else {
        setErrorMessage(t('createOpportunity.errorGeneric'));
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <ScreenContainer edges={['top', 'bottom']}>
      <ScreenHeader
        title={
          isEditing
            ? t('createOpportunity.editTitle', 'Edit Opportunity')
            : t('createOpportunity.title')
        }
        subtitle={
          isEditing
            ? t(
                'createOpportunity.editSubtitle',
                'Update the opportunity details candidates will see.'
              )
            : t('createOpportunity.subtitle')
        }
        showBack
        navigation={navigation}
        alignment="center"
        bordered
      />

      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        keyboardVerticalOffset={Platform.OS === 'ios' ? 64 : 0}
      >
        <ScrollView
          style={styles.screen}
          contentContainerStyle={[styles.content, { paddingBottom: insets.bottom + 48 }]}
          showsVerticalScrollIndicator={false}
          keyboardShouldPersistTaps="handled"
        >
          {errorMessage && (
            <Card style={styles.errorBanner} padding="md">
              <Text style={[styles.errorBannerText, isRTL && styles.rtlText]}>
                {errorMessage}
              </Text>
            </Card>
          )}

          {/* Section 1: Basic Information */}
          <Text style={[styles.sectionHeading, isRTL && styles.rtlText]}>
            {t('createOpportunity.sectionBasic')}
          </Text>

          <Text style={[styles.label, isRTL && styles.rtlText]}>
            {t('createOpportunity.jobTitle')} <Text style={styles.requiredStar}>*</Text>
          </Text>
          <TextInput
            style={[styles.input, isRTL && styles.rtlWriting]}
            placeholder={t('createOpportunity.jobTitlePlaceholder')}
            placeholderTextColor={colors.textTertiary || colors.textMuted}
            value={title}
            onChangeText={setTitle}
            maxLength={200}
            editable={!submitting && !loadingExisting}
          />

          <Text style={[styles.label, isRTL && styles.rtlText]}>
            {t('createOpportunity.company')} <Text style={styles.requiredStar}>*</Text>
          </Text>
          <TextInput
            style={[styles.input, isRTL && styles.rtlWriting]}
            placeholder={t('createOpportunity.companyPlaceholder')}
            placeholderTextColor={colors.textTertiary || colors.textMuted}
            value={company}
            onChangeText={setCompany}
            maxLength={200}
            editable={!submitting && !loadingExisting}
          />

          <Text style={[styles.label, isRTL && styles.rtlText]}>
            {t('createOpportunity.location')} <Text style={styles.requiredStar}>*</Text>
          </Text>
          <TextInput
            style={[styles.input, isRTL && styles.rtlWriting]}
            placeholder={t('createOpportunity.locationPlaceholder')}
            placeholderTextColor={colors.textTertiary || colors.textMuted}
            value={location}
            onChangeText={setLocation}
            maxLength={200}
            editable={!submitting && !loadingExisting}
          />

          <Text style={[styles.label, isRTL && styles.rtlText]}>
            {t('createOpportunity.workType')} <Text style={styles.requiredStar}>*</Text>
          </Text>
          <View style={[styles.workTypeRow, isRTL && styles.rowRTL]}>
            {WORK_TYPES.map((typeObj) => {
              const isSelected = workType === typeObj.id;
              const label = t(`createOpportunity.workTypes.${typeObj.id}`, { defaultValue: typeObj.id });
              return (
                <Chip
                  key={typeObj.id}
                  label={label}
                  variant={isSelected ? 'skill' : 'neutral'}
                  selected={isSelected}
                  onPress={() => !submitting && !loadingExisting && setWorkType(typeObj.id)}
                />
              );
            })}
          </View>

          <Text style={[styles.label, isRTL && styles.rtlText]}>
            {t('createOpportunity.description')} <Text style={styles.requiredStar}>*</Text>
          </Text>
          <TextInput
            style={[styles.input, styles.multilineInput, isRTL && styles.rtlWriting]}
            placeholder={t('createOpportunity.descriptionPlaceholder')}
            placeholderTextColor={colors.textTertiary || colors.textMuted}
            value={description}
            onChangeText={setDescription}
            multiline
            numberOfLines={5}
            textAlignVertical="top"
            editable={!submitting && !loadingExisting}
          />

          {/* Section 2: Skills & Requirements (Optional) */}
          <Text style={[styles.sectionHeading, styles.sectionHeadingSpaced, isRTL && styles.rtlText]}>
            {t('createOpportunity.sectionSkills')}
          </Text>

          <Text style={[styles.label, isRTL && styles.rtlText]}>
            {t('createOpportunity.requiredSkills')}
          </Text>
          <TextInput
            style={[styles.input, isRTL && styles.rtlWriting]}
            placeholder={t('createOpportunity.requiredSkillsPlaceholder')}
            placeholderTextColor={colors.textTertiary || colors.textMuted}
            value={requiredSkills}
            onChangeText={setRequiredSkills}
            editable={!submitting && !loadingExisting}
          />

          <Text style={[styles.label, isRTL && styles.rtlText]}>
            {t('createOpportunity.preferredSkills')}
          </Text>
          <TextInput
            style={[styles.input, isRTL && styles.rtlWriting]}
            placeholder={t('createOpportunity.preferredSkillsPlaceholder')}
            placeholderTextColor={colors.textTertiary || colors.textMuted}
            value={preferredSkills}
            onChangeText={setPreferredSkills}
            editable={!submitting && !loadingExisting}
          />

          <Text style={[styles.label, isRTL && styles.rtlText]}>
            {t('createOpportunity.language')}
          </Text>
          <TextInput
            style={[styles.input, isRTL && styles.rtlWriting]}
            placeholder={t('createOpportunity.languagePlaceholder')}
            placeholderTextColor={colors.textTertiary || colors.textMuted}
            value={language}
            onChangeText={setLanguage}
            editable={!submitting && !loadingExisting}
          />

          <Text style={[styles.label, isRTL && styles.rtlText]}>
            {t('createOpportunity.educationRequirements')}
          </Text>
          <TextInput
            style={[styles.input, isRTL && styles.rtlWriting]}
            placeholder={t('createOpportunity.educationPlaceholder')}
            placeholderTextColor={colors.textTertiary || colors.textMuted}
            value={educationRequirements}
            onChangeText={setEducationRequirements}
            editable={!submitting && !loadingExisting}
          />

          <Text style={[styles.label, isRTL && styles.rtlText]}>
            {t('createOpportunity.experienceRequirements')}
          </Text>
          <TextInput
            style={[styles.input, isRTL && styles.rtlWriting]}
            placeholder={t('createOpportunity.experiencePlaceholder')}
            placeholderTextColor={colors.textTertiary || colors.textMuted}
            value={experienceRequirements}
            onChangeText={setExperienceRequirements}
            editable={!submitting && !loadingExisting}
          />

          <GradientButton
            title={
              loadingExisting
                ? t('common.loading', 'Loading...')
                : submitting
                  ? isEditing
                    ? t('createOpportunity.updating', 'Updating...')
                    : t('createOpportunity.publishing')
                  : isEditing
                    ? t('createOpportunity.updateBtn', 'Update Opportunity')
                    : t('createOpportunity.publishBtn')
            }
            color={colors.accent || colors.teal}
            onPress={handleSubmit}
            disabled={submitting || loadingExisting}
            loading={submitting || loadingExisting}
            style={styles.publishBtn}
          />
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
    paddingTop: spacing.md,
  },
  errorBanner: {
    backgroundColor: '#FEF2F2',
    borderColor: colors.dangerSoft || '#FEE2E2',
    marginBottom: spacing.md,
  },
  errorBannerText: {
    ...typography.caption,
    color: colors.danger || '#EF4444',
    lineHeight: 18,
  },
  sectionHeading: {
    ...typography.label,
    fontSize: 14,
    fontWeight: '700',
    color: colors.textPrimary || colors.textDark,
    marginBottom: spacing.sm,
    letterSpacing: 0.2,
  },
  sectionHeadingSpaced: {
    marginTop: spacing.lg,
  },
  label: {
    ...typography.caption,
    fontWeight: '600',
    color: colors.textSecondary || colors.textMuted,
    marginBottom: spacing.xs,
    marginTop: spacing.sm,
  },
  requiredStar: {
    color: colors.danger || '#EF4444',
  },
  input: {
    backgroundColor: colors.surface || colors.cardBg,
    borderRadius: spacing.radii.sm,
    borderWidth: 1,
    borderColor: colors.borderSubtle || colors.border,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm + 2,
    fontSize: 14,
    color: colors.textPrimary || colors.textDark,
    minHeight: spacing.minimumTouchTarget,
  },
  multilineInput: {
    minHeight: 110,
    paddingTop: spacing.sm + 2,
  },
  workTypeRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    marginTop: spacing.xxs,
    marginBottom: spacing.xs,
  },
  publishBtn: {
    marginTop: spacing.xl,
    width: '100%',
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
