import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { useTranslation } from 'react-i18next';
import { Ionicons } from '@expo/vector-icons';

import ScreenContainer from '../components/ScreenContainer';
import ScreenHeader from '../components/ScreenHeader';
import Card from '../components/Card';
import GradientButton from '../components/GradientButton';
import colors from '../theme/colors';
import { spacing } from '../theme/spacing';
import { typography } from '../theme/typography';
import { useLocalization } from '../localization/LocalizationContext';
import haptics from '../services/haptics';
import {
  ApiError,
  createEmployerOrganization,
  getEmployerOrganization,
  submitEmployerOrganizationForReview,
  updateEmployerOrganization,
} from '../services/api';

const EMPTY_FORM = {
  legal_name: '',
  display_name: '',
  website_url: '',
  business_email: '',
  country_code: '',
  registration_number: '',
  tax_number: '',
  representative_name: '',
  representative_role: '',
};

const REQUIRED_FIELDS = [
  'legal_name',
  'display_name',
  'website_url',
  'business_email',
  'country_code',
  'representative_name',
  'representative_role',
];

function normalizeForm(organization) {
  if (!organization) return { ...EMPTY_FORM };

  return {
    legal_name: organization.legal_name || '',
    display_name: organization.display_name || '',
    website_url: organization.website_url || '',
    business_email: organization.business_email || '',
    country_code: organization.country_code || '',
    registration_number: organization.registration_number || '',
    tax_number: organization.tax_number || '',
    representative_name: organization.representative_name || '',
    representative_role: organization.representative_role || '',
  };
}

function isValidUrl(value) {
  try {
    const url = new URL(value);
    return url.protocol === 'https:' || url.protocol === 'http:';
  } catch {
    return false;
  }
}

function isValidEmail(value) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
}

export default function EmployerVerificationScreen({ navigation }) {
  const { t } = useTranslation();
  const { isRTL } = useLocalization();

  const scrollRef = useRef(null);
  const inputRefs = useRef({});
  const fieldPositions = useRef({});
  const submitInFlightRef = useRef(false);

  const [organization, setOrganization] = useState(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [fieldErrors, setFieldErrors] = useState({});
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const [actionMessage, setActionMessage] = useState(null);
  const [actionError, setActionError] = useState(null);

  const status = organization?.verification_status || 'not_started';
  const editable =
    status === 'not_started' ||
    status === 'unverified' ||
    status === 'rejected';

  const loadOrganization = useCallback(async () => {
    setLoading(true);
    setLoadError(false);
    setActionError(null);

    try {
      const result = await getEmployerOrganization();
      setOrganization(result);
      setForm(normalizeForm(result));
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) {
        setOrganization(null);
        setForm({ ...EMPTY_FORM });
      } else {
        console.warn('Failed to load employer organization:', error);
        setLoadError(true);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadOrganization();

    const unsubscribe = navigation.addListener('focus', loadOrganization);
    return unsubscribe;
  }, [loadOrganization, navigation]);

  const rememberFieldPosition = (field) => (event) => {
    fieldPositions.current[field] = event.nativeEvent.layout.y;
  };

  const setField = (field, value) => {
    setForm((current) => ({
      ...current,
      [field]: field === 'country_code' ? value.toUpperCase() : value,
    }));

    setFieldErrors((current) => {
      if (!current[field]) return current;

      const next = { ...current };
      delete next[field];
      return next;
    });

    setActionError(null);
    setActionMessage(null);
  };

  const focusFirstError = (errors) => {
    const firstField = Object.keys(errors)[0];
    if (!firstField) return;

    requestAnimationFrame(() => {
      const position = fieldPositions.current[firstField];

      if (typeof position === 'number') {
        scrollRef.current?.scrollTo({
          y: Math.max(0, position - 24),
          animated: true,
        });
      }

      inputRefs.current[firstField]?.focus?.();
    });
  };

  const validate = () => {
    const errors = {};

    for (const field of REQUIRED_FIELDS) {
      if (!form[field]?.trim()) {
        errors[field] = t(
          'employerVerification.requiredField',
          'This field is required.'
        );
      }
    }

    if (form.website_url.trim() && !isValidUrl(form.website_url.trim())) {
      errors.website_url = t(
        'employerVerification.invalidWebsite',
        'Enter a valid company website URL.'
      );
    }

    if (
      form.business_email.trim() &&
      !isValidEmail(form.business_email.trim())
    ) {
      errors.business_email = t(
        'employerVerification.invalidEmail',
        'Enter a valid business email address.'
      );
    }

    const countryCode = form.country_code.trim().toUpperCase();
    if (countryCode && !/^[A-Z]{2}$/.test(countryCode)) {
      errors.country_code = t(
        'employerVerification.invalidCountry',
        'Use the two-letter country code, such as TR, DE, or US.'
      );
    }

    setFieldErrors(errors);

    if (Object.keys(errors).length > 0) {
      haptics.error();
      focusFirstError(errors);
      return false;
    }

    return true;
  };

  const buildPayload = () => ({
    legal_name: form.legal_name.trim(),
    display_name: form.display_name.trim(),
    website_url: form.website_url.trim(),
    business_email: form.business_email.trim(),
    country_code: form.country_code.trim().toUpperCase(),
    registration_number: form.registration_number.trim() || null,
    tax_number: form.tax_number.trim() || null,
    representative_name: form.representative_name.trim(),
    representative_role: form.representative_role.trim(),
  });

  const handleSubmit = async () => {
    if (
      submitInFlightRef.current ||
      submitting ||
      !editable ||
      !validate()
    ) {
      return;
    }

    submitInFlightRef.current = true;
    setSubmitting(true);
    setActionError(null);
    setActionMessage(null);

    try {
      const payload = buildPayload();

      const savedOrganization = organization
        ? await updateEmployerOrganization(payload)
        : await createEmployerOrganization(payload);

      setOrganization(savedOrganization);
      setForm(normalizeForm(savedOrganization));

      const submittedOrganization =
        await submitEmployerOrganizationForReview();

      setOrganization(submittedOrganization);
      setForm(normalizeForm(submittedOrganization));
      setFieldErrors({});
      setActionMessage(
        t(
          'employerVerification.submittedMessage',
          'Your organization has been submitted for verification. You can publish internship opportunities after approval.'
        )
      );

      haptics.success();
      scrollRef.current?.scrollTo({ y: 0, animated: true });
    } catch (error) {
      console.warn('Failed to submit employer verification:', error);

      if (error instanceof ApiError) {
        setActionError(
          error.status === 409
            ? t(
                'employerVerification.conflictError',
                'Your organization status changed while this request was being processed. Refresh and try again.'
              )
            : t(
                'employerVerification.submitError',
                'We could not submit your organization for verification. Review the information and try again.'
              )
        );
      } else {
        setActionError(
          t(
            'employerVerification.submitError',
            'We could not submit your organization for verification. Review the information and try again.'
          )
        );
      }

      haptics.error();
    } finally {
      submitInFlightRef.current = false;
      setSubmitting(false);
    }
  };

  const getStatusTitle = () => {
    switch (status) {
      case 'unverified':
        return t('employerVerification.statusDraft', 'Verification required');
      case 'pending':
        return t('employerVerification.statusPending', 'Under review');
      case 'verified':
        return t('employerVerification.statusVerified', 'Organization verified');
      case 'rejected':
        return t('employerVerification.statusRejected', 'Action required');
      case 'suspended':
        return t('employerVerification.statusSuspended', 'Verification suspended');
      default:
        return t('employerVerification.statusNotStarted', 'Verification required');
    }
  };

  const getStatusDescription = () => {
    switch (status) {
      case 'unverified':
        return t(
          'employerVerification.draftDescription',
          'Complete your organization details and submit them for review before publishing internship opportunities.'
        );
      case 'pending':
        return t(
          'employerVerification.pendingDescription',
          'Your organization information is being reviewed. Publishing remains unavailable until verification is approved.'
        );
      case 'verified':
        return t(
          'employerVerification.verifiedDescription',
          'Your organization has been verified. You can publish and manage internship opportunities.'
        );
      case 'rejected':
        return t(
          'employerVerification.rejectedDescription',
          'We could not verify the submitted information. Review the reason below, correct your organization details, and submit again.'
        );
      case 'suspended':
        return t(
          'employerVerification.suspendedDescription',
          'Organization verification is currently suspended. Publishing and reopening internship opportunities are unavailable while this status is active.'
        );
      default:
        return t(
          'employerVerification.notStartedDescription',
          'Verify your organization before publishing internships. InternMatch reviews organization identity and business information to help protect candidates.'
        );
    }
  };

  const rejectionReason = organization?.rejection_reason_code
    ? t(
        `employerVerification.rejectionReasons.${organization.rejection_reason_code}`,
        t(
          'employerVerification.rejectionReasons.other',
          'The submitted information did not meet the verification requirements.'
        )
      )
    : null;

  const renderField = ({
    field,
    label,
    placeholder,
    keyboardType = 'default',
    autoCapitalize = 'sentences',
    optional = false,
    maxLength = 200,
  }) => (
    <View
      style={styles.fieldGroup}
      onLayout={rememberFieldPosition(field)}
    >
      <Text style={[styles.label, isRTL && styles.rtlText]}>
        {label}
        {!optional ? <Text style={styles.requiredStar}> *</Text> : null}
      </Text>

      <TextInput
        ref={(ref) => {
          inputRefs.current[field] = ref;
        }}
        style={[
          styles.input,
          fieldErrors[field] && styles.inputError,
          isRTL && styles.rtlWriting,
          !editable && styles.inputReadOnly,
        ]}
        value={form[field]}
        placeholder={placeholder}
        placeholderTextColor={colors.textTertiary || colors.textMuted}
        onChangeText={(value) => setField(field, value)}
        editable={editable && !submitting}
        keyboardType={keyboardType}
        autoCapitalize={autoCapitalize}
        autoCorrect={false}
        maxLength={maxLength}
      />

      {fieldErrors[field] ? (
        <Text style={[styles.fieldError, isRTL && styles.rtlText]}>
          {fieldErrors[field]}
        </Text>
      ) : null}
    </View>
  );

  return (
    <ScreenContainer edges={['top', 'bottom']}>
      <ScreenHeader
        title={t('employerVerification.title', 'Organization Verification')}
        showBack
        navigation={navigation}
        alignment="center"
        bordered
      />

      <TouchableOpacity
        style={[
          styles.guidanceLink,
          isRTL && styles.guidanceLinkRTL,
        ]}
        onPress={() => {
          navigation.navigate(
            'EmployerGuidance',
            {
              topic: 'organization',
            }
          );
        }}
        accessibilityRole="button"
        accessibilityLabel={t(
          'employerGuidance.organization.linkLabel'
        )}
      >
        <View style={styles.guidanceIcon}>
          <Ionicons
            name="help"
            size={14}
            color={colors.accentStrong || colors.tealDark}
          />
        </View>

        <Text
          style={[
            styles.guidanceLinkText,
            isRTL && styles.rtlText,
          ]}
        >
          {t(
            'employerGuidance.organization.linkLabel'
          )}
        </Text>
      </TouchableOpacity>

      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        <ScrollView
          ref={scrollRef}
          contentContainerStyle={styles.content}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          {loading ? (
            <View style={styles.loadingState}>
              <ActivityIndicator
                size="large"
                color={colors.accent || colors.teal}
              />
              <Text style={[styles.loadingText, isRTL && styles.rtlText]}>
                {t(
                  'employerVerification.loading',
                  'Loading organization verification...'
                )}
              </Text>
            </View>
          ) : loadError ? (
            <Card style={styles.stateCard} padding="lg">
              <Text style={[styles.stateTitle, isRTL && styles.rtlText]}>
                {t(
                  'employerVerification.loadErrorTitle',
                  'Could not load verification'
                )}
              </Text>
              <Text style={[styles.stateDescription, isRTL && styles.rtlText]}>
                {t(
                  'employerVerification.loadError',
                  'We could not load your organization verification status. Check your connection and try again.'
                )}
              </Text>

              <GradientButton
                title={t('employerVerification.retry', 'Try Again')}
                color={colors.accent || colors.teal}
                onPress={loadOrganization}
                style={styles.fullWidthButton}
              />
            </Card>
          ) : (
            <>
              <Card style={styles.statusCard} padding="lg">
                <View style={[styles.statusRow, isRTL && styles.rowRTL]}>
                  <View
                    style={[
                      styles.statusDot,
                      status === 'verified' && styles.statusDotVerified,
                      status === 'pending' && styles.statusDotPending,
                      status === 'rejected' && styles.statusDotDanger,
                      status === 'suspended' && styles.statusDotDanger,
                    ]}
                  />
                  <Text style={[styles.statusTitle, isRTL && styles.rtlText]}>
                    {getStatusTitle()}
                  </Text>
                </View>

                <Text
                  style={[
                    styles.statusDescription,
                    isRTL && styles.rtlText,
                  ]}
                >
                  {getStatusDescription()}
                </Text>

                {status === 'rejected' && rejectionReason ? (
                  <View style={styles.reasonBox}>
                    <Text style={[styles.reasonLabel, isRTL && styles.rtlText]}>
                      {t(
                        'employerVerification.reviewReason',
                        'Review reason'
                      )}
                    </Text>
                    <Text style={[styles.reasonText, isRTL && styles.rtlText]}>
                      {rejectionReason}
                    </Text>
                  </View>
                ) : null}

                {actionMessage ? (
                  <Text
                    style={[
                      styles.successMessage,
                      isRTL && styles.rtlText,
                    ]}
                  >
                    {actionMessage}
                  </Text>
                ) : null}

                {actionError ? (
                  <Text
                    style={[
                      styles.actionError,
                      isRTL && styles.rtlText,
                    ]}
                  >
                    {actionError}
                  </Text>
                ) : null}
              </Card>

              {(editable || organization) && (
                <Card style={styles.formCard} padding="lg">
                  <Text style={[styles.sectionTitle, isRTL && styles.rtlText]}>
                    {t(
                      'employerVerification.organizationDetails',
                      'Organization details'
                    )}
                  </Text>

                  <Text
                    style={[
                      styles.sectionDescription,
                      isRTL && styles.rtlText,
                    ]}
                  >
                    {t(
                      'employerVerification.organizationDetailsDescription',
                      'Provide accurate legal and business information that can be reviewed against official or independently verifiable sources.'
                    )}
                  </Text>

                  {renderField({
                    field: 'legal_name',
                    label: t(
                      'employerVerification.fields.legalName',
                      'Legal organization name'
                    ),
                    placeholder: t(
                      'employerVerification.placeholders.legalName',
                      'Registered legal name'
                    ),
                  })}

                  {renderField({
                    field: 'display_name',
                    label: t(
                      'employerVerification.fields.displayName',
                      'Organization display name'
                    ),
                    placeholder: t(
                      'employerVerification.placeholders.displayName',
                      'Name shown to candidates'
                    ),
                  })}

                  {renderField({
                    field: 'website_url',
                    label: t(
                      'employerVerification.fields.website',
                      'Official website'
                    ),
                    placeholder: 'https://example.com',
                    keyboardType: 'url',
                    autoCapitalize: 'none',
                  })}

                  {renderField({
                    field: 'business_email',
                    label: t(
                      'employerVerification.fields.businessEmail',
                      'Official business email'
                    ),
                    placeholder: 'hr@example.com',
                    keyboardType: 'email-address',
                    autoCapitalize: 'none',
                  })}

                  {renderField({
                    field: 'country_code',
                    label: t(
                      'employerVerification.fields.countryCode',
                      'Country code'
                    ),
                    placeholder: t(
                      'employerVerification.placeholders.countryCode',
                      'TR'
                    ),
                    autoCapitalize: 'characters',
                    maxLength: 2,
                  })}

                  {renderField({
                    field: 'registration_number',
                    label: t(
                      'employerVerification.fields.registrationNumber',
                      'Registration number'
                    ),
                    placeholder: t(
                      'employerVerification.placeholders.registrationNumber',
                      'Official registration number, if applicable'
                    ),
                    optional: true,
                  })}

                  {renderField({
                    field: 'tax_number',
                    label: t(
                      'employerVerification.fields.taxNumber',
                      'Tax number'
                    ),
                    placeholder: t(
                      'employerVerification.placeholders.taxNumber',
                      'Tax identifier, if applicable'
                    ),
                    optional: true,
                  })}

                  {renderField({
                    field: 'representative_name',
                    label: t(
                      'employerVerification.fields.representativeName',
                      'Authorized representative'
                    ),
                    placeholder: t(
                      'employerVerification.placeholders.representativeName',
                      'Full name'
                    ),
                  })}

                  {renderField({
                    field: 'representative_role',
                    label: t(
                      'employerVerification.fields.representativeRole',
                      'Representative role'
                    ),
                    placeholder: t(
                      'employerVerification.placeholders.representativeRole',
                      'e.g. HR Manager'
                    ),
                  })}

                  {editable ? (
                    <GradientButton
                      title={
                        submitting
                          ? t(
                              'employerVerification.submitting',
                              'Submitting...'
                            )
                          : status === 'rejected'
                            ? t(
                                'employerVerification.resubmit',
                                'Correct & Resubmit'
                              )
                            : t(
                                'employerVerification.submitForReview',
                                'Submit for Verification'
                              )
                      }
                      color={colors.accent || colors.teal}
                      onPress={handleSubmit}
                      disabled={submitting}
                      loading={submitting}
                      style={styles.fullWidthButton}
                    />
                  ) : null}
                </Card>
              )}

              {status === 'verified' ? (
                <GradientButton
                  title={t(
                    'employerVerification.backToOpportunities',
                    'Go to My Opportunities'
                  )}
                  color={colors.accent || colors.teal}
                  onPress={() =>
                    navigation.navigate('MainTabs', {
                      screen: 'Opportunities',
                    })
                  }
                  style={styles.bottomButton}
                />
              ) : null}

              {(status === 'pending' || status === 'suspended') ? (
                <TouchableOpacity
                  style={styles.refreshButton}
                  onPress={loadOrganization}
                  disabled={loading}
                  accessibilityRole="button"
                >
                  <Text
                    style={[
                      styles.refreshButtonText,
                      isRTL && styles.rtlText,
                    ]}
                  >
                    {t(
                      'employerVerification.refreshStatus',
                      'Refresh Verification Status'
                    )}
                  </Text>
                </TouchableOpacity>
              ) : null}
            </>
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
  guidanceLink: {
    alignSelf: 'flex-start',
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    marginHorizontal: spacing.screenHorizontalPadding,
    marginTop: spacing.sm,
    paddingVertical: spacing.xs,
  },
  guidanceLinkRTL: {
    alignSelf: 'flex-end',
    flexDirection: 'row-reverse',
  },
  guidanceIcon: {
    width: 22,
    height: 22,
    borderRadius: 11,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.accentSoft || '#E6F7F5',
  },
  guidanceLinkText: {
    color: colors.accentStrong || colors.tealDark,
    fontSize: 12,
    fontWeight: '700',
  },
  content: {
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.md,
    paddingBottom: spacing.xxxl,
  },
  loadingState: {
    minHeight: 280,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: spacing.xl,
  },
  loadingText: {
    ...typography.body,
    color: colors.textSecondary || colors.textMuted,
    marginTop: spacing.md,
    textAlign: 'center',
  },
  stateCard: {
    marginTop: spacing.md,
  },
  stateTitle: {
    ...typography.h3,
    color: colors.textPrimary,
  },
  stateDescription: {
    ...typography.body,
    color: colors.textSecondary || colors.textMuted,
    marginTop: spacing.sm,
  },
  statusCard: {
    marginBottom: spacing.md,
  },
  statusRow: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  rowRTL: {
    flexDirection: 'row-reverse',
  },
  statusDot: {
    width: 10,
    height: 10,
    borderRadius: 5,
    marginHorizontal: spacing.xs,
    backgroundColor: colors.textMuted || '#64748B',
  },
  statusDotVerified: {
    backgroundColor: '#16A34A',
  },
  statusDotPending: {
    backgroundColor: '#D97706',
  },
  statusDotDanger: {
    backgroundColor: colors.danger || '#DC2626',
  },
  statusTitle: {
    ...typography.h3,
    color: colors.textPrimary,
    flex: 1,
  },
  statusDescription: {
    ...typography.body,
    color: colors.textSecondary || colors.textMuted,
    marginTop: spacing.sm,
  },
  reasonBox: {
    marginTop: spacing.md,
    padding: spacing.md,
    borderRadius: spacing.radii.sm,
    borderWidth: 1,
    borderColor: colors.danger || '#DC2626',
    backgroundColor: colors.surface || colors.cardBg,
  },
  reasonLabel: {
    ...typography.caption,
    color: colors.danger || '#DC2626',
    fontWeight: '700',
  },
  reasonText: {
    ...typography.body,
    color: colors.textPrimary,
    marginTop: spacing.xxs,
  },
  successMessage: {
    ...typography.body,
    color: '#15803D',
    marginTop: spacing.md,
  },
  actionError: {
    ...typography.body,
    color: colors.danger || '#DC2626',
    marginTop: spacing.md,
  },
  formCard: {
    marginBottom: spacing.md,
  },
  sectionTitle: {
    ...typography.h3,
    color: colors.textPrimary,
  },
  sectionDescription: {
    ...typography.body,
    color: colors.textSecondary || colors.textMuted,
    marginTop: spacing.xs,
    marginBottom: spacing.md,
  },
  fieldGroup: {
    marginBottom: spacing.md,
  },
  label: {
    ...typography.body,
    color: colors.textPrimary,
    fontWeight: '600',
    marginBottom: spacing.xs,
  },
  requiredStar: {
    color: colors.danger || '#DC2626',
  },
  input: {
    minHeight: 48,
    borderRadius: spacing.radii.sm,
    borderWidth: 1,
    borderColor: colors.borderSubtle || colors.border,
    backgroundColor: colors.surface || colors.cardBg,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    color: colors.textPrimary,
    fontSize: 15,
  },
  inputError: {
    borderColor: colors.danger || '#DC2626',
    borderWidth: 2,
  },
  inputReadOnly: {
    opacity: 0.8,
  },
  fieldError: {
    ...typography.caption,
    color: colors.danger || '#DC2626',
    marginTop: spacing.xxs,
  },
  fullWidthButton: {
    width: '100%',
    marginTop: spacing.md,
  },
  bottomButton: {
    width: '100%',
    marginTop: spacing.sm,
  },
  refreshButton: {
    minHeight: 48,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: spacing.sm,
    borderRadius: spacing.radii.sm,
    borderWidth: 1,
    borderColor: colors.borderSubtle || colors.border,
  },
  refreshButtonText: {
    ...typography.body,
    color: colors.accentStrong || colors.tealDark || colors.textPrimary,
    fontWeight: '600',
  },
  rtlText: {
    textAlign: 'right',
    writingDirection: 'rtl',
  },
  rtlWriting: {
    textAlign: 'right',
    writingDirection: 'rtl',
  },
});
