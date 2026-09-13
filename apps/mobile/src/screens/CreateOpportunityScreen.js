import React, { useEffect, useRef, useState } from 'react';
import {
  View,
  Text,
  TextInput,
  StyleSheet,
  ScrollView,
  KeyboardAvoidingView,
  Platform,
  Alert,
  ActivityIndicator,
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
import EmployerDescriptionAssistant from '../components/EmployerDescriptionAssistant';
import {
  createEmployerInternship,
  getEmployerOrganization,
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
  const [fieldErrors, setFieldErrors] = useState({});
  const [verificationChecking, setVerificationChecking] = useState(true);
  const [verifiedOrganization, setVerifiedOrganization] = useState(null);

  const scrollRef = useRef(null);
  const titleRef = useRef(null);
  const companyRef = useRef(null);
  const locationRef = useRef(null);
  const descriptionRef = useRef(null);
  const fieldPositions = useRef({});

  const rememberFieldPosition = (field) => (event) => {
    fieldPositions.current[field] = event.nativeEvent.layout.y;
  };

  const clearFieldError = (field) => {
    setFieldErrors((current) => {
      if (!current[field]) return current;

      const next = { ...current };
      delete next[field];
      return next;
    });
  };


  useEffect(() => {
    let active = true;

    const enforceVerifiedEmployer = async () => {
      setVerificationChecking(true);

      try {
        const organization = await getEmployerOrganization();

        if (!active) return;

        if (organization.verification_status !== 'verified') {
          navigation.replace('EmployerVerification');
          return;
        }

        setVerifiedOrganization(organization);
        setCompany(
          organization.display_name ||
          organization.legal_name
        );
      } catch (err) {
        if (!active) return;

        console.warn(
          'Failed to verify employer before opening opportunity editor:',
          err
        );

        navigation.replace('EmployerVerification');
      } finally {
        if (active) {
          setVerificationChecking(false);
        }
      }
    };

    enforceVerifiedEmployer();

    return () => {
      active = false;
    };
  }, [navigation]);

  useEffect(() => {
    if (!verifiedOrganization) {
      return undefined;
    }

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
        setCompany(
          verifiedOrganization.display_name ||
          verifiedOrganization.legal_name
        );
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
  }, [editingId, t, verifiedOrganization]);

  const handleSubmit = async () => {
    setErrorMessage(null);

    const trimmedTitle = title.trim();
    const trimmedCompany = company.trim();
    const trimmedLocation = location.trim();
    const trimmedDescription = description.trim();

    const missing = {};

    if (!trimmedTitle) {
      missing.title = t(
        'createOpportunity.requiredField',
        'This field is required.'
      );
    }

    if (!trimmedCompany) {
      missing.company = t(
        'createOpportunity.requiredField',
        'This field is required.'
      );
    }

    if (!trimmedLocation) {
      missing.location = t(
        'createOpportunity.requiredField',
        'This field is required.'
      );
    }

    if (!workType) {
      missing.workType = t(
        'createOpportunity.requiredField',
        'This field is required.'
      );
    }

    if (!trimmedDescription) {
      missing.description = t(
        'createOpportunity.requiredField',
        'This field is required.'
      );
    }

    const missingFields = Object.keys(missing);

    if (missingFields.length > 0) {
      setFieldErrors(missing);
      setErrorMessage(
        t(
          'createOpportunity.validationError',
          'Please complete the highlighted required fields.'
        )
      );
      haptics.error();

      const firstField = missingFields[0];

      requestAnimationFrame(() => {
        const position = fieldPositions.current[firstField];

        if (typeof position === 'number') {
          scrollRef.current?.scrollTo({
            y: Math.max(0, position - 24),
            animated: true,
          });
        }

        const inputRefs = {
          title: titleRef,
          company: companyRef,
          location: locationRef,
          description: descriptionRef,
        };

        inputRefs[firstField]?.current?.focus();
      });

      return;
    }

    setFieldErrors({});

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
      if (err instanceof ApiError && err.status === 403) {
        setErrorMessage(
          t(
            'createOpportunity.verificationRequired',
            'Your company must be verified before you can publish opportunities. Complete company verification or wait for administrator approval.'
          )
        );
        haptics.error();
      } else if (err instanceof ApiError && err.status === 503) {
        setErrorMessage(t('createOpportunity.error503'));
      } else {
        setErrorMessage(t('createOpportunity.errorGeneric'));
      }
    } finally {
      setSubmitting(false);
    }
  };

  if (verificationChecking || !verifiedOrganization) {
    return (
      <ScreenContainer edges={['top', 'bottom']}>
        <ScreenHeader
          title={t('createOpportunity.title')}
          showBack
          navigation={navigation}
          alignment="center"
          bordered
        />

        <View style={styles.verificationLoading}>
          <ActivityIndicator
            size="large"
            color={colors.accent || colors.teal}
          />
          <Text
            style={[
              styles.verificationLoadingText,
              isRTL && styles.rtlText,
            ]}
          >
            {t('employerVerification.loading')}
          </Text>
        </View>
      </ScreenContainer>
    );
  }

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
          ref={scrollRef}
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
            ref={titleRef}
            onLayout={rememberFieldPosition('title')}
            style={[
              styles.input,
              fieldErrors.title && styles.inputError,
              isRTL && styles.rtlWriting,
            ]}
            placeholder={t('createOpportunity.jobTitlePlaceholder')}
            placeholderTextColor={colors.textTertiary || colors.textMuted}
            value={title}
            onChangeText={(value) => {
              setTitle(value);
              clearFieldError('title');
            }}
            maxLength={200}
            editable={!submitting && !loadingExisting}
          />
          {fieldErrors.title ? (
            <Text style={[styles.fieldErrorText, isRTL && styles.rtlText]}>
              {fieldErrors.title}
            </Text>
          ) : null}

          <Text style={[styles.label, isRTL && styles.rtlText]}>
            {t('createOpportunity.company')} <Text style={styles.requiredStar}>*</Text>
          </Text>
          <TextInput
            ref={companyRef}
            onLayout={rememberFieldPosition('company')}
            style={[
              styles.input,
              styles.readOnlyInput,
              fieldErrors.company && styles.inputError,
              isRTL && styles.rtlWriting,
            ]}
            placeholder={t('createOpportunity.companyPlaceholder')}
            placeholderTextColor={colors.textTertiary || colors.textMuted}
            value={company}
            maxLength={200}
            editable={false}
          />
          {fieldErrors.company ? (
            <Text style={[styles.fieldErrorText, isRTL && styles.rtlText]}>
              {fieldErrors.company}
            </Text>
          ) : null}
          <Text style={[styles.identityNotice, isRTL && styles.rtlText]}>
            {t('employerVerification.verifiedCompanyNotice')}
          </Text>

          <Text style={[styles.label, isRTL && styles.rtlText]}>
            {t('createOpportunity.location')} <Text style={styles.requiredStar}>*</Text>
          </Text>
          <TextInput
            ref={locationRef}
            onLayout={rememberFieldPosition('location')}
            style={[
              styles.input,
              fieldErrors.location && styles.inputError,
              isRTL && styles.rtlWriting,
            ]}
            placeholder={t('createOpportunity.locationPlaceholder')}
            placeholderTextColor={colors.textTertiary || colors.textMuted}
            value={location}
            onChangeText={(value) => {
              setLocation(value);
              clearFieldError('location');
            }}
            maxLength={200}
            editable={!submitting && !loadingExisting}
          />
          {fieldErrors.location ? (
            <Text style={[styles.fieldErrorText, isRTL && styles.rtlText]}>
              {fieldErrors.location}
            </Text>
          ) : null}

          <Text style={[styles.label, isRTL && styles.rtlText]}>
            {t('createOpportunity.workType')} <Text style={styles.requiredStar}>*</Text>
          </Text>
          <View
            onLayout={rememberFieldPosition('workType')}
            style={[
              styles.workTypeRow,
              fieldErrors.workType && styles.workTypeError,
              isRTL && styles.rowRTL,
            ]}
          >
            {WORK_TYPES.map((typeObj) => {
              const isSelected = workType === typeObj.id;
              const label = t(`createOpportunity.workTypes.${typeObj.id}`, { defaultValue: typeObj.id });
              return (
                <Chip
                  key={typeObj.id}
                  label={label}
                  variant={isSelected ? 'skill' : 'neutral'}
                  selected={isSelected}
                  onPress={() => {
                    if (!submitting && !loadingExisting) {
                      setWorkType(typeObj.id);
                      clearFieldError('workType');
                    }
                  }}
                />
              );
            })}
          </View>
          {fieldErrors.workType ? (
            <Text style={[styles.fieldErrorText, isRTL && styles.rtlText]}>
              {fieldErrors.workType}
            </Text>
          ) : null}

          <Text style={[styles.label, isRTL && styles.rtlText]}>
            {t('createOpportunity.description')} <Text style={styles.requiredStar}>*</Text>
          </Text>
          <TextInput
            ref={descriptionRef}
            onLayout={rememberFieldPosition('description')}
            style={[
              styles.input,
              styles.multilineInput,
              fieldErrors.description && styles.inputError,
              isRTL && styles.rtlWriting,
            ]}
            placeholder={t('createOpportunity.descriptionPlaceholder')}
            placeholderTextColor={colors.textTertiary || colors.textMuted}
            value={description}
            onChangeText={(value) => {
              setDescription(value);
              clearFieldError('description');
            }}
            multiline
            numberOfLines={5}
            textAlignVertical="top"
            editable={!submitting && !loadingExisting}
          />
          {fieldErrors.description ? (
            <Text style={[styles.fieldErrorText, isRTL && styles.rtlText]}>
              {fieldErrors.description}
            </Text>
          ) : null}

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

        <EmployerDescriptionAssistant
          title={title}
          rawDescription={description}
          onApplyDescription={setDescription}
          navigation={navigation}
          isRTL={typeof isRTL !== 'undefined' ? isRTL : false}
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
  readOnlyInput: {
    opacity: 0.82,
  },
  identityNotice: {
    ...typography.caption,
    color: colors.textSecondary || colors.textMuted,
    marginTop: spacing.xxs,
    marginBottom: spacing.xs,
  },
  verificationLoading: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: spacing.xl,
  },
  verificationLoadingText: {
    ...typography.body,
    color: colors.textSecondary || colors.textMuted,
    marginTop: spacing.md,
    textAlign: 'center',
  },
  inputError: {
    borderColor: colors.danger || '#EF4444',
    borderWidth: 2,
  },
  fieldErrorText: {
    ...typography.caption,
    color: colors.danger || '#EF4444',
    marginTop: spacing.xxs,
    marginBottom: spacing.xs,
  },
  workTypeError: {
    borderWidth: 1,
    borderColor: colors.danger || '#EF4444',
    borderRadius: spacing.radii.sm,
    padding: spacing.xs,
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
