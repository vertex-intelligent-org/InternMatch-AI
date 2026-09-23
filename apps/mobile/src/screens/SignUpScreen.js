import React, { useRef, useState } from 'react';
import {
  ActivityIndicator,
  View,
  Text,
  TextInput,
  StyleSheet,
  TouchableOpacity,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  Alert,
} from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import * as AppleAuthentication from 'expo-apple-authentication';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useTranslation } from 'react-i18next';
import { useLocalization } from '../localization/LocalizationContext';
import colors from '../theme/colors';
import { spacing } from '../theme/spacing';
import { typography } from '../theme/typography';
import InternMatchLogo from '../components/InternMatchLogo';
import PreAuthLanguageSwitcher from '../components/PreAuthLanguageSwitcher';
import AuthGlassPanel from '../components/AuthGlassPanel';
import AuthSegmentedControl from '../components/AuthSegmentedControl';
import SocialAuthButton from '../components/SocialAuthButton';
import GradientButton from '../components/GradientButton';
import PressableScale from '../components/PressableScale';
import motionTokens from '../motion/motionTokens';
import { signInWithGoogle } from '../services/googleAuth';
import { signInWithApple } from '../services/appleAuth';
import { signUpWithEmail, signOut, isAuthRateLimitError } from '../services/auth';
import {
  ApiError,
  completeSignup,
  syncAuthenticatedUser,
} from '../services/api';
import { useProfile } from '../context/ProfileContext';
import haptics from '../services/haptics';

export default function SignUpScreen({ navigation }) {
  const { t } = useTranslation();
  const { isRTL } = useLocalization();
  const insets = useSafeAreaInsets();
  const [accountType, setAccountType] = useState(null); // null | 'intern' | 'employer'
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [passwordVisible, setPasswordVisible] = useState(false);
  const [department, setDepartment] = useState('');
  const [focusedField, setFocusedField] = useState(null);
  const [loading, setLoading] = useState(false);
  const [loadingSource, setLoadingSource] = useState(null);
  const [fieldErrors, setFieldErrors] = useState({});

  const scrollRef = useRef(null);
  const fullNameRef = useRef(null);
  const emailRef = useRef(null);
  const passwordRef = useRef(null);
  const fieldPositions = useRef({});
  const authActionInFlightRef = useRef(false);

  const { refreshProfile, setProfile } = useProfile();

  const clearFieldError = (field) => {
    setFieldErrors((current) => {
      if (!current[field]) return current;

      const next = { ...current };
      delete next[field];
      return next;
    });
  };

  const focusValidationField = (field) => {
    const position = fieldPositions.current[field];

    if (typeof position === 'number') {
      scrollRef.current?.scrollTo({
        y: Math.max(position - spacing.lg, 0),
        animated: true,
      });
    }

    const refs = {
      fullName: fullNameRef,
      email: emailRef,
      password: passwordRef,
    };

    setTimeout(() => {
      refs[field]?.current?.focus();
    }, 180);
  };

  const showValidationErrors = (errors) => {
    setFieldErrors(errors);

    const firstInvalid = ['fullName', 'email', 'password'].find(
      (field) => Boolean(errors[field])
    );

    if (firstInvalid) {
      haptics.error();
      focusValidationField(firstInvalid);
      return false;
    }

    return true;
  };

  const ensureAccountTypeSelected = () => {
    if (accountType === 'intern' || accountType === 'employer') {
      return true;
    }

    haptics.error();
    Alert.alert(
      t('common.error'),
      t('auth.selectAccountType')
    );
    return false;
  };

  const ensureSocialSignupReady = () => {
    if (!ensureAccountTypeSelected()) {
      return false;
    }

    // Social sign-up is currently available
    // for student accounts only.
    if (accountType === 'employer') {
      return false;
    }

    return true;
  };

  const rejectExistingSignupAccount = async () => {
    const { error: signOutError } = await signOut();
    if (signOutError) {
      throw signOutError;
    }

    setProfile(null);
    haptics.error();
    Alert.alert(
      t('auth.accountAlreadyExistsTitle'),
      t('auth.accountAlreadyExistsMessage')
    );
  };

  const completeSocialSignup = async (socialFullName = null) => {
    const syncResult = await syncAuthenticatedUser();

    if (syncResult.has_profile) {
      await rejectExistingSignupAccount();
      return;
    }

    const resolvedFullName =
      typeof socialFullName === 'string'
      && socialFullName.trim()
        ? socialFullName.trim()
        : fullName.trim();

    const canonicalFullName =
      resolvedFullName
      || 'InternMatch User';

    try {
      await completeSignup({
        full_name: canonicalFullName,
        department: department.trim() || null,
        account_type: accountType,
      });
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        await rejectExistingSignupAccount();
        return;
      }
      throw error;
    }

    const createdProfile = await refreshProfile();
    if (!createdProfile) {
      throw new Error(t('errors.profileSaveFailed'));
    }

    setProfile(createdProfile);
    navigation.replace('MainTabs');
  };

  const handleCreateAccount = async () => {
    const normalizedEmail = email.trim().toLowerCase();
    const normalizedName = fullName.trim();
    const normalizedDepartment = department.trim();

    if (!ensureAccountTypeSelected()) {
      return;
    }

    const validationErrors = {};

    if (!normalizedName) {
      validationErrors.fullName = t('onboarding.enterFullName');
    }

    if (!normalizedEmail) {
      validationErrors.email = t('auth.emailRequired');
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(normalizedEmail)) {
      validationErrors.email = t('errors.authInvalidEmail');
    }

    if (!password) {
      validationErrors.password = t('auth.passwordRequired');
    } else if (password.length < 6) {
      validationErrors.password = t('auth.passwordMinLength');
    }

    if (!showValidationErrors(validationErrors)) {
      return;
    }

    if (authActionInFlightRef.current || loading) return;

    authActionInFlightRef.current = true;
    setLoading(true);
    setLoadingSource('email');

    try {
      const metadata = {
        full_name: normalizedName,
        department: normalizedDepartment || null,
        account_type: accountType,
      };

      const { data, error } = await signUpWithEmail(normalizedEmail, password, metadata);

      if (error) {
        throw error;
      }

      if (!data.session?.access_token) {
        Alert.alert(
          t('auth.checkEmailTitle'),
          t('auth.checkEmailMessage')
        );
        navigation.replace('SignIn', {
          confirmationEmail: normalizedEmail,
        });
        return;
      }

      await completeSignup({
        full_name: normalizedName,
        department: normalizedDepartment || null,
        account_type: accountType,
      });

      const createdProfile = await refreshProfile();
      if (!createdProfile) {
        throw new Error(t('errors.profileSaveFailed'));
      }

      setProfile(createdProfile);
      navigation.replace('MainTabs');
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        await rejectExistingSignupAccount();
        return;
      }

      if (isAuthRateLimitError(error)) {
        Alert.alert(t('common.error'), t('auth.emailConfirmation.rateLimit'));
        return;
      }
      let errorKey = 'errors.authSignUpFailed';
      const msg = error instanceof Error ? error.message.toLowerCase() : '';
      if (msg.includes('already registered') || msg.includes('email in use') || msg.includes('user already exists')) {
        errorKey = 'errors.authEmailInUse';
      } else if (msg.includes('weak') || msg.includes('password should be')) {
        errorKey = 'errors.authWeakPassword';
      } else if (msg.includes('invalid email')) {
        errorKey = 'errors.authInvalidEmail';
      }
      Alert.alert(t('common.error'), t(errorKey));
    } finally {
      authActionInFlightRef.current = false;
      setLoading(false);
      setLoadingSource(null);
    }
  };

  const handleGoogle = async () => {
    if (authActionInFlightRef.current || loading) return;
    if (!ensureSocialSignupReady()) return;

    authActionInFlightRef.current = true;
    setLoading(true);
    setLoadingSource('google');

    try {
      const result = await signInWithGoogle();

      if (result.cancelled) {
        return;
      }

      if (!result.session?.access_token) {
        throw new Error(t('errors.unauthorized'));
      }

      await completeSocialSignup(
        result.fullName
      );
    } catch (error) {
      console.warn('Google sign-up failed:', error);
      haptics.error();

      Alert.alert(
        t('auth.googleSignIn'),
        t('errors.authSignUpFailed')
      );
    } finally {
      authActionInFlightRef.current = false;
      setLoading(false);
      setLoadingSource(null);
    }
  };
  const handleApple = async () => {
    if (authActionInFlightRef.current || loading) return;
    if (!ensureSocialSignupReady()) return;

    authActionInFlightRef.current = true;
    setLoading(true);
    setLoadingSource('apple');

    try {
      // Canonical account role is created by the InternMatch backend below.
      // Do not write role metadata into an existing Apple Auth identity.
      const result = await signInWithApple();

      if (result.cancelled) {
        return;
      }

      if (result.unavailable) {
        Alert.alert(
          t('auth.appleSignIn'),
          t('auth.appleNotAvailable')
        );
        return;
      }

      if (!result.session?.access_token) {
        throw new Error(t('errors.unauthorized'));
      }

      await completeSocialSignup(
        result.fullName
      );
    } catch (error) {
      console.warn('Apple sign-up failed:', error);
      haptics.error();

      Alert.alert(
        t('auth.appleSignIn'),
        t('errors.authSignUpFailed')
      );
    } finally {
      authActionInFlightRef.current = false;
      setLoading(false);
      setLoadingSource(null);
    }
  };

  return (
    <LinearGradient
      colors={['#DBF1F5', '#EAF6F8', '#E3F4F6']}
      style={styles.container}
    >
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={styles.flex}
      >
        <ScrollView
          ref={scrollRef}
          contentContainerStyle={[
            styles.scrollContent,
            {
              paddingTop: Math.max(insets.top, 16) + spacing.md,
              paddingBottom: Math.max(insets.bottom, 20) + spacing.xl,
            },
          ]}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          <PreAuthLanguageSwitcher
            disabled={loading}
            style={styles.languageSwitcher}
          />

          {/* Brand Logo Zone */}
          <View style={styles.brandZone}>
            <InternMatchLogo style={styles.brandLogo} />
          </View>

          {/* Heading Zone */}
          <View style={styles.headingZone}>
            <Text style={styles.title}>{t('auth.createAccountTitle')}</Text>
            <Text style={styles.subtitle}>
              {t('auth.signUpSubtitle')}
            </Text>
          </View>

          {/* Glass Authentication Panel */}
          <AuthGlassPanel style={styles.authPanel}>
            {/* Segmented Control */}
            <AuthSegmentedControl
              activeTab="signUp"
              onTabChange={(tab) => {
                if (tab === 'signIn') {
                  navigation.replace('SignIn');
                }
              }}
            />

            {/* Role / Account Type Selector */}
            <View style={styles.fieldGroup}>
              <Text style={styles.fieldLabel}>{t('auth.accountType')}</Text>
              <View style={styles.typeRow} accessibilityRole="radiogroup">
                {/* Intern Option */}
                <PressableScale
                  style={[
                    styles.typeCard,
                    accountType === 'intern' ? styles.typeCardActive : styles.typeCardInactive,
                  ]}
                  onPress={() => setAccountType('intern')}
                  scaleTo={
                    accountType === 'intern'
                      ? 1
                      : motionTokens.scales.chipPressed
                  }
                  activeOpacity={
                    accountType === 'intern'
                      ? 1
                      : motionTokens.opacities.pressed
                  }
                  haptic={
                    accountType === 'intern'
                      ? 'none'
                      : 'selection'
                  }
                  accessibilityRole="radio"
                  accessibilityState={{ selected: accountType === 'intern' }}
                  accessibilityLabel={`${t('auth.accountType')}: ${t('auth.intern')}`}
                  hitSlop={{ top: 6, bottom: 6, left: 6, right: 6 }}
                >
                  <Ionicons
                    name="school-outline"
                    size={18}
                    color={
                      accountType === 'intern'
                        ? colors.accentStrong || colors.tealDark
                        : colors.textSecondary || colors.textMuted
                    }
                  />
                  <Text
                    style={[
                      styles.typeText,
                      accountType === 'intern' ? styles.typeTextActive : styles.typeTextInactive,
                    ]}
                  >
                    {t('auth.intern')}
                  </Text>
                </PressableScale>

                {/* Employer Option */}
                <PressableScale
                  style={[
                    styles.typeCard,
                    accountType === 'employer' ? styles.typeCardActive : styles.typeCardInactive,
                  ]}
                  onPress={() => setAccountType('employer')}
                  scaleTo={
                    accountType === 'employer'
                      ? 1
                      : motionTokens.scales.chipPressed
                  }
                  activeOpacity={
                    accountType === 'employer'
                      ? 1
                      : motionTokens.opacities.pressed
                  }
                  haptic={
                    accountType === 'employer'
                      ? 'none'
                      : 'selection'
                  }
                  accessibilityRole="radio"
                  accessibilityState={{ selected: accountType === 'employer' }}
                  accessibilityLabel={`${t('auth.accountType')}: ${t('auth.employer')}`}
                  hitSlop={{ top: 6, bottom: 6, left: 6, right: 6 }}
                >
                  <Ionicons
                    name="briefcase-outline"
                    size={18}
                    color={
                      accountType === 'employer'
                        ? colors.accentStrong || colors.tealDark
                        : colors.textSecondary || colors.textMuted
                    }
                  />
                  <Text
                    style={[
                      styles.typeText,
                      accountType === 'employer' ? styles.typeTextActive : styles.typeTextInactive,
                    ]}
                  >
                    {t('auth.employer')}
                  </Text>
                </PressableScale>
              </View>
            </View>

            {/* Full Name */}
            <View
              style={styles.fieldGroup}
              onLayout={(event) => {
                fieldPositions.current.fullName = event.nativeEvent.layout.y;
              }}
            >
              <Text style={styles.fieldLabel}>{t('auth.fullName')}</Text>
              <TextInput
                style={[
                  styles.input,
                  focusedField === 'fullName' && styles.inputFocused,
                  fieldErrors.fullName && styles.inputError,
                ]}
                placeholder={t('auth.fullNamePlaceholder')}
                placeholderTextColor="rgba(22, 35, 46, 0.40)"
                ref={fullNameRef}
                value={fullName}
                onChangeText={(value) => {
                  setFullName(value);
                  clearFieldError('fullName');
                }}
                onFocus={() => setFocusedField('fullName')}
                onBlur={() => setFocusedField(null)}
                accessibilityLabel={t('auth.fullName')}
              />
              {fieldErrors.fullName ? (
                <Text
                  style={[
                    styles.fieldErrorText,
                    { textAlign: isRTL ? 'right' : 'left' },
                  ]}
                  accessibilityLiveRegion="polite"
                >
                  {fieldErrors.fullName}
                </Text>
              ) : null}
            </View>

            {/* Email Field */}
            <View
              style={styles.fieldGroup}
              onLayout={(event) => {
                fieldPositions.current.email = event.nativeEvent.layout.y;
              }}
            >
              <Text style={styles.fieldLabel}>{t('auth.email')}</Text>
              <TextInput
                style={[
                  styles.input,
                  focusedField === 'email' && styles.inputFocused,
                  fieldErrors.email && styles.inputError,
                ]}
                placeholder={t('auth.emailPlaceholder')}
                placeholderTextColor="rgba(22, 35, 46, 0.40)"
                autoCapitalize="none"
                autoCorrect={false}
                keyboardType="email-address"
                ref={emailRef}
                value={email}
                onChangeText={(value) => {
                  setEmail(value);
                  clearFieldError('email');
                }}
                onFocus={() => setFocusedField('email')}
                onBlur={() => setFocusedField(null)}
                accessibilityLabel={t('auth.email')}
              />
              {fieldErrors.email ? (
                <Text
                  style={[
                    styles.fieldErrorText,
                    { textAlign: isRTL ? 'right' : 'left' },
                  ]}
                  accessibilityLiveRegion="polite"
                >
                  {fieldErrors.email}
                </Text>
              ) : null}
            </View>

            {/* Password Field */}
            <View
              style={styles.fieldGroup}
              onLayout={(event) => {
                fieldPositions.current.password = event.nativeEvent.layout.y;
              }}
            >
              <Text style={styles.fieldLabel}>{t('auth.password')}</Text>
              <View style={styles.passwordInputWrap}>
                <TextInput
                  style={[
                    styles.input,
                    styles.passwordInput,
                    focusedField === 'password' && styles.inputFocused,
                    fieldErrors.password && styles.inputError,
                    isRTL && styles.passwordInputRTL,
                  ]}
                  placeholder={t('auth.passwordMin')}
                  placeholderTextColor="rgba(22, 35, 46, 0.40)"
                  secureTextEntry={!passwordVisible}
                  ref={passwordRef}
                  value={password}
                  onChangeText={(value) => {
                    setPassword(value);
                    clearFieldError('password');
                  }}
                  onFocus={() => setFocusedField('password')}
                  onBlur={() => setFocusedField(null)}
                  accessibilityLabel={t('auth.password')}
                />
                <TouchableOpacity
                  style={[styles.eyeButton, isRTL && styles.eyeButtonRTL]}
                  onPress={() => {
                    haptics.selection();
                    setPasswordVisible((prev) => !prev);
                  }}
                  hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
                  accessibilityRole="button"
                  accessibilityLabel={passwordVisible ? 'Hide password' : 'Show password'}
                  accessibilityState={{ expanded: passwordVisible }}
                >
                  <Ionicons
                    name={passwordVisible ? 'eye-outline' : 'eye-off-outline'}
                    size={20}
                    color={colors.textSecondary || colors.textMuted}
                  />
                </TouchableOpacity>
              </View>
              {fieldErrors.password ? (
                <Text
                  style={[
                    styles.fieldErrorText,
                    { textAlign: isRTL ? 'right' : 'left' },
                  ]}
                  accessibilityLiveRegion="polite"
                >
                  {fieldErrors.password}
                </Text>
              ) : null}
            </View>

            {/* Department Field */}
            <View style={styles.fieldGroup}>
              <Text style={styles.fieldLabel}>{t('auth.departmentField')}</Text>
              <TextInput
                style={[
                  styles.input,
                  focusedField === 'department' && styles.inputFocused,
                ]}
                placeholder={t('auth.departmentPlaceholder')}
                placeholderTextColor="rgba(22, 35, 46, 0.40)"
                value={department}
                onChangeText={setDepartment}
                onFocus={() => setFocusedField('department')}
                onBlur={() => setFocusedField(null)}
                accessibilityLabel={t('auth.departmentField')}
              />
            </View>

            {/* Primary CTA */}
            <GradientButton
              title={
                loadingSource === 'email'
                  ? t('auth.creatingAccount')
                  : t('auth.createAccount')
              }
              color={colors.accent || colors.teal}
              onPress={handleCreateAccount}
              disabled={loading}
              loading={loadingSource === 'email'}
              style={styles.primaryCta}
            />

            {accountType === 'intern' ? (
              <>
                {/* Social providers use provider identity.
                    Manual fields above are not required for social signup. */}
                {loadingSource === 'google' ? (
                  <View
                    style={styles.authLoadingButton}
                    accessibilityRole="progressbar"
                    accessibilityLiveRegion="polite"
                  >
                    <ActivityIndicator
                      size="small"
                      color={
                        colors.textInverse
                        || '#FFFFFF'
                      }
                    />
                    <Text
                      style={
                        styles.authLoadingButtonText
                      }
                    >
                      {t('auth.signingIn')}
                    </Text>
                  </View>
                ) : (
                  <SocialAuthButton
                    provider="google"
                    label={
                      t('auth.signUpWithGoogle')
                    }
                    onPress={handleGoogle}
                    disabled={loading}
                  />
                )}

                {Platform.OS === 'ios' ? (
                  loadingSource === 'apple' ? (
                    <View
                      style={[
                        styles.authLoadingButton,
                        styles.appleAuthButton,
                      ]}
                      accessibilityRole="progressbar"
                      accessibilityLiveRegion="polite"
                    >
                      <ActivityIndicator
                        size="small"
                        color={
                          colors.textInverse
                          || '#FFFFFF'
                        }
                      />
                      <Text
                        style={
                          styles.authLoadingButtonText
                        }
                      >
                        {t('auth.signingIn')}
                      </Text>
                    </View>
                  ) : (
                    <AppleAuthentication.AppleAuthenticationButton
                      buttonType={
                        AppleAuthentication
                          .AppleAuthenticationButtonType
                          .SIGN_UP
                      }
                      buttonStyle={
                        AppleAuthentication
                          .AppleAuthenticationButtonStyle
                          .BLACK
                      }
                      cornerRadius={24}
                      style={
                        styles.appleAuthButton
                      }
                      onPress={handleApple}
                      pointerEvents={
                        loading
                          ? 'none'
                          : 'auto'
                      }
                      accessibilityState={{
                        disabled: loading,
                      }}
                    />
                  )
                ) : null}

                <View
                  style={styles.dividerRow}
                >
                  <View
                    style={styles.divider}
                  />
                  <Text
                    style={styles.dividerText}
                  >
                    {t('auth.or')}
                  </Text>
                  <View
                    style={styles.divider}
                  />
                </View>
              </>
            ) : null}



            {/* Legal Footer inside Panel */}
            <View style={styles.legalFooter}>
              <PressableScale
                onPress={() => navigation.navigate('PrivacyPolicy')}
                scaleTo={motionTokens.scales.chipPressed}
                activeOpacity={motionTokens.opacities.pressed}
                haptic="none"
                accessibilityRole="button"
                accessibilityLabel={t('auth.privacyPolicy')}
                hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
              >
                <Text style={styles.legalLink}>{t('auth.privacyPolicy')}</Text>
              </PressableScale>

              <Text style={styles.legalDot}>{'\u00b7'}</Text>

              <PressableScale
                onPress={() => navigation.navigate('TermsOfUse')}
                scaleTo={motionTokens.scales.chipPressed}
                activeOpacity={motionTokens.opacities.pressed}
                haptic="none"
                accessibilityRole="button"
                accessibilityLabel={t('auth.termsOfUse')}
                hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
              >
                <Text style={styles.legalLink}>{t('auth.termsOfUse')}</Text>
              </PressableScale>
            </View>
          </AuthGlassPanel>
        </ScrollView>
      </KeyboardAvoidingView>
    </LinearGradient>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  flex: {
    flex: 1,
  },
  scrollContent: {
    paddingHorizontal: spacing.screenHorizontalPadding,
    alignItems: 'center',
  },
  languageSwitcher: {
    marginBottom: spacing.sm,
  },

  brandZone: {
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: spacing.lg,
  },
  brandLogo: {
    alignSelf: 'center',
  },
  headingZone: {
    alignItems: 'center',
    marginBottom: spacing.lg,
    paddingHorizontal: spacing.sm,
  },
  title: {
    ...typography.display,
    fontSize: 24,
    lineHeight: 30,
    color: colors.textPrimary || colors.textDark,
    textAlign: 'center',
    fontWeight: '800',
  },
  subtitle: {
    ...typography.body,
    fontSize: 14,
    color: colors.textSecondary || colors.textMuted,
    textAlign: 'center',
    marginTop: spacing.xxs,
  },
  authPanel: {
    width: '100%',
  },
  fieldGroup: {
    marginBottom: spacing.md,
  },
  fieldLabel: {
    ...typography.caption,
    fontWeight: '600',
    color: colors.textPrimary || colors.textDark,
    marginBottom: spacing.xs,
  },
  typeRow: {
    flexDirection: 'row',
    gap: spacing.sm,
  },
  typeCard: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: 44,
    borderRadius: spacing.radii.md,
    borderWidth: 1.5,
    paddingHorizontal: spacing.md,
    overflow: 'hidden',
  },
  typeCardActive: {
    backgroundColor: 'rgba(14, 116, 144, 0.12)',
    borderColor: colors.accent || colors.teal,
  },
  typeCardInactive: {
    backgroundColor: 'rgba(255, 255, 255, 0.70)',
    borderColor: 'rgba(14, 116, 144, 0.14)',
  },
  typeText: {
    marginStart: spacing.xs + 2,
    ...typography.button,
    fontSize: 13,
  },
  typeTextActive: {
    color: colors.accentStrong || colors.tealDark,
    fontWeight: '700',
  },
  typeTextInactive: {
    color: colors.textSecondary || colors.textMuted,
    fontWeight: '500',
  },
  input: {
    backgroundColor: '#FFFFFF',
    borderRadius: spacing.radii.md,
    minHeight: 48,
    paddingHorizontal: spacing.md,
    borderWidth: 1.5,
    borderColor: 'rgba(14, 116, 144, 0.16)',
    color: colors.textDark,
    ...typography.body,
  },
  passwordInputWrap: {
    position: 'relative',
    justifyContent: 'center',
  },
  passwordInput: {
    paddingRight: 48,
  },
  passwordInputRTL: {
    paddingRight: spacing.md,
    paddingLeft: 48,
    textAlign: 'right',
    writingDirection: 'rtl',
  },
  eyeButton: {
    position: 'absolute',
    right: 12,
    height: 48,
    width: 40,
    justifyContent: 'center',
    alignItems: 'center',
  },
  eyeButtonRTL: {
    right: undefined,
    left: 12,
  },
  inputFocused: {
    borderColor: colors.accent || colors.teal,
    backgroundColor: '#FFFFFF',
    shadowColor: colors.accent || colors.teal,
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.12,
    shadowRadius: 4,
    elevation: 2,
  },
  primaryCta: {
    marginTop: spacing.sm,
  },
  dividerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginVertical: spacing.lg,
  },
  divider: {
    flex: 1,
    height: 1,
    backgroundColor: 'rgba(14, 116, 144, 0.15)',
  },
  dividerText: {
    ...typography.caption,
    color: colors.textTertiary || colors.textMuted,
    marginHorizontal: spacing.md,
    fontWeight: '600',
  },
  legalFooter: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: spacing.xl,
    paddingTop: spacing.sm,
  },
  legalLink: {
    ...typography.caption,
    color: colors.textSecondary || colors.textMuted,
    fontWeight: '500',
  },
  legalDot: {
    marginHorizontal: spacing.sm,
    color: colors.textTertiary || colors.textMuted,
    fontSize: 14,
    fontWeight: '700',
  },
  authLoadingButton: {
    minHeight: 48,
    borderRadius: spacing.radii.pill,
    backgroundColor: '#94A3B8',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.sm,
    paddingHorizontal: spacing.lg,
    opacity: 0.92,
  },
  authLoadingButtonText: {
    color: colors.textInverse || '#FFFFFF',
    fontSize: 15,
    fontWeight: '700',
  },
  appleAuthButton: {
    width: '100%',
    height: 48,
    marginTop: spacing.md,
  },

  inputError: {
    borderColor: colors.error || '#B42318',
    borderWidth: 1.5,
  },
  fieldErrorText: {
    ...typography.caption,
    color: colors.error || '#B42318',
    fontSize: 12,
    lineHeight: 17,
    marginTop: spacing.xs,
  },
});
