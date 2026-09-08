import React, { useState } from 'react';
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
import colors from '../theme/colors';
import { spacing } from '../theme/spacing';
import { typography } from '../theme/typography';
import InternMatchLogo from '../components/InternMatchLogo';
import AuthGlassPanel from '../components/AuthGlassPanel';
import AuthSegmentedControl from '../components/AuthSegmentedControl';
import SocialAuthButton from '../components/SocialAuthButton';
import GradientButton from '../components/GradientButton';
import PressableScale from '../components/PressableScale';
import motionTokens from '../motion/motionTokens';
import { signInWithGoogle } from '../services/googleAuth';
import { signInWithApple } from '../services/appleAuth';
import { signUpWithEmail, isAuthRateLimitError } from '../services/auth';
import { ApiError, syncAuthenticatedUser, upsertProfile } from '../services/api';
import { useProfile } from '../context/ProfileContext';
import haptics from '../services/haptics';

export default function SignUpScreen({ navigation }) {
  const { t } = useTranslation();
  const insets = useSafeAreaInsets();
  const [accountType, setAccountType] = useState('intern'); // 'intern' | 'employer'
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [passwordVisible, setPasswordVisible] = useState(false);
  const [department, setDepartment] = useState('');
  const [focusedField, setFocusedField] = useState(null);
  const [loading, setLoading] = useState(false);
  const [loadingSource, setLoadingSource] = useState(null);
  const { refreshProfile, setProfile } = useProfile();

  const handleCreateAccount = async () => {
    const normalizedEmail = email.trim().toLowerCase();
    const normalizedName = fullName.trim();
    const normalizedDepartment = department.trim();

    if (!normalizedName || !normalizedEmail || !password) {
      haptics.error();
      Alert.alert(t('common.error'), t('auth.enterSignUpFields'));
      return;
    }

    if (password.length < 6) {
      haptics.error();
      Alert.alert(t('common.error'), t('auth.passwordMinLength'));
      return;
    }

    if (loading) return;

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

      await syncAuthenticatedUser();

      const createdProfile = await upsertProfile({
        full_name: normalizedName,
        headline: null,
        preferences: {
          account_type: accountType,
          department: normalizedDepartment || null,
        },
      });

      setProfile(createdProfile);

      navigation.replace('MainTabs');
    } catch (error) {
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
      setLoading(false);
      setLoadingSource(null);
    }
  };

  const handleGoogle = async () => {
    if (loading) return;

    setLoading(true);
    setLoadingSource('google');
    let providerAuthenticated = false;

    try {
      const result = await signInWithGoogle();

      if (result.cancelled) {
        return;
      }

      const session = result.session;

      if (!session?.access_token) {
        throw new Error(t('errors.unauthorized'));
      }

      providerAuthenticated = true;
      const syncResult = await syncAuthenticatedUser();

      if (syncResult.has_profile) {
        await refreshProfile();
        navigation.replace('MainTabs');
        return;
      }

      const normalizedName = fullName.trim();
      const normalizedDepartment = department.trim();
      const meta = session.user?.user_metadata || {};

      const googleName =
        typeof meta.full_name === 'string'
          ? meta.full_name.trim()
          : typeof meta.name === 'string'
            ? meta.name.trim()
            : '';

      const canonicalName = normalizedName || googleName;

      if (!canonicalName) {
        navigation.replace('OnboardingProfile');
        return;
      }

      const createdProfile = await upsertProfile({
        full_name: canonicalName,
        headline: null,
        preferences: {
          account_type: accountType,
          department: normalizedDepartment || null,
        },
      });

      setProfile(createdProfile);
      navigation.replace('MainTabs');
    } catch (error) {
      console.warn('Google sign-up failed:', error);
      haptics.error();

      let errorKey = 'errors.authSignUpFailed';

      if (providerAuthenticated) {
        if (error instanceof ApiError && error.status === 0) {
          errorKey = 'errors.network';
        } else if (
          error instanceof ApiError &&
          (error.status === 401 || error.status === 403)
        ) {
          errorKey = 'errors.unauthorized';
        } else {
          errorKey = 'errors.authAccountSetupFailed';
        }
      }

      Alert.alert(
        t('auth.googleSignIn'),
        t(errorKey)
      );
    } finally {
      setLoading(false);
      setLoadingSource(null);
    }
  };

  const handleApple = async () => {
    if (loading) return;

    setLoading(true);
    setLoadingSource('apple');

    try {
      const result = await signInWithApple({
        full_name: fullName.trim(),
        department: department.trim(),
        account_type: accountType,
      });

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

      navigation.replace('Splash');
    } catch (error) {
      console.warn('Apple sign-up failed:', error);
      haptics.error();

      Alert.alert(
        t('auth.appleSignIn'),
        t('errors.authSignUpFailed')
      );
    } finally {
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
            <View style={styles.fieldGroup}>
              <Text style={styles.fieldLabel}>{t('auth.fullName')}</Text>
              <TextInput
                style={[
                  styles.input,
                  focusedField === 'fullName' && styles.inputFocused,
                ]}
                placeholder={t('auth.fullNamePlaceholder')}
                placeholderTextColor="rgba(22, 35, 46, 0.40)"
                value={fullName}
                onChangeText={setFullName}
                onFocus={() => setFocusedField('fullName')}
                onBlur={() => setFocusedField(null)}
                accessibilityLabel={t('auth.fullName')}
              />
            </View>

            {/* Email Field */}
            <View style={styles.fieldGroup}>
              <Text style={styles.fieldLabel}>{t('auth.email')}</Text>
              <TextInput
                style={[
                  styles.input,
                  focusedField === 'email' && styles.inputFocused,
                ]}
                placeholder={t('auth.emailPlaceholder')}
                placeholderTextColor="rgba(22, 35, 46, 0.40)"
                autoCapitalize="none"
                autoCorrect={false}
                keyboardType="email-address"
                value={email}
                onChangeText={setEmail}
                onFocus={() => setFocusedField('email')}
                onBlur={() => setFocusedField(null)}
                accessibilityLabel={t('auth.email')}
              />
            </View>

            {/* Password Field */}
            <View style={styles.fieldGroup}>
              <Text style={styles.fieldLabel}>{t('auth.password')}</Text>
              <View style={styles.passwordInputWrap}>
                <TextInput
                  style={[
                    styles.input,
                    styles.passwordInput,
                    focusedField === 'password' && styles.inputFocused,
                  ]}
                  placeholder={t('auth.passwordMin')}
                  placeholderTextColor="rgba(22, 35, 46, 0.40)"
                  secureTextEntry={!passwordVisible}
                  value={password}
                  onChangeText={setPassword}
                  onFocus={() => setFocusedField('password')}
                  onBlur={() => setFocusedField(null)}
                  accessibilityLabel={t('auth.password')}
                />
                <TouchableOpacity
                  style={styles.eyeButton}
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

            {/* Divider */}
            <View style={styles.dividerRow}>
              <View style={styles.divider} />
              <Text style={styles.dividerText}>{t('auth.or')}</Text>
              <View style={styles.divider} />
            </View>

            {/* Social Providers */}
            {loadingSource === 'google' ? (
              <View
                style={styles.authLoadingButton}
                accessibilityRole="progressbar"
                accessibilityLiveRegion="polite"
              >
                <ActivityIndicator
                  size="small"
                  color={colors.textInverse || '#FFFFFF'}
                />
                <Text style={styles.authLoadingButtonText}>
                  {t('auth.signingIn')}
                </Text>
              </View>
            ) : (
              <SocialAuthButton
                provider="google"
                onPress={handleGoogle}
                disabled={loading}
              />
            )}

            {Platform.OS === 'ios' && (
              loadingSource === 'apple' ? (
                <View
                  style={[styles.authLoadingButton, styles.appleAuthButton]}
                  accessibilityRole="progressbar"
                  accessibilityLiveRegion="polite"
                >
                  <ActivityIndicator
                    size="small"
                    color={colors.textInverse || '#FFFFFF'}
                  />
                  <Text style={styles.authLoadingButtonText}>
                    {t('auth.signingIn')}
                  </Text>
                </View>
              ) : (
                <AppleAuthentication.AppleAuthenticationButton
                  buttonType={
                    AppleAuthentication.AppleAuthenticationButtonType.SIGN_UP
                  }
                  buttonStyle={
                    AppleAuthentication.AppleAuthenticationButtonStyle.BLACK
                  }
                  cornerRadius={24}
                  style={styles.appleAuthButton}
                  onPress={handleApple}
                />
              )
            )}

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
  eyeButton: {
    position: 'absolute',
    right: 12,
    height: 48,
    width: 40,
    justifyContent: 'center',
    alignItems: 'center',
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

});
