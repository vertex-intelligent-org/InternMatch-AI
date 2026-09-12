import React, { useEffect, useState } from 'react';
import { ActivityIndicator } from 'react-native';
import {
  View,
  Text,
  TextInput,
  StyleSheet,
  TouchableOpacity,
  KeyboardAvoidingView,
  Platform,
  Alert,
  ScrollView,
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
import {
  signInWithEmail,
  clearLocalSessionAfterAccountDeletion,
  resendSignupConfirmation,
  isEmailNotConfirmedError,
  isAuthRateLimitError,
} from '../services/auth';
import {
  ApiError,
  completeSignup,
  deleteAccount,
  syncAuthenticatedUser,
} from '../services/api';
import { useProfile } from '../context/ProfileContext';
import haptics from '../services/haptics';

export default function SignInScreen({ navigation, route }) {
  const { t } = useTranslation();
  const { isRTL } = useLocalization();
  const insets = useSafeAreaInsets();

  const initialConfirmationEmail = typeof route?.params?.confirmationEmail === 'string'
    ? route.params.confirmationEmail.trim().toLowerCase()
    : '';

  const [email, setEmail] = useState(initialConfirmationEmail || '');
  const [password, setPassword] = useState('');
  const [passwordVisible, setPasswordVisible] = useState(false);
  const [focusedField, setFocusedField] = useState(null);
  const [loading, setLoading] = useState(false);
  const [loadingSource, setLoadingSource] = useState(null);
  const [pendingConfirmationEmail, setPendingConfirmationEmail] = useState(initialConfirmationEmail || '');
  const [resendLoading, setResendLoading] = useState(false);
  const [resendCooldownSeconds, setResendCooldownSeconds] = useState(0);
  const { refreshProfile, setProfile } = useProfile();

  const rejectMissingCanonicalAccount = async () => {
    // Supabase OAuth may transiently create an Auth identity even when the
    // user entered through Sign In. Remove that identity server-side so
    // Sign In never leaves behind an implicit InternMatch registration.
    await deleteAccount();
    await clearLocalSessionAfterAccountDeletion();

    setProfile(null);
    haptics.error();
    Alert.alert(
      t('auth.noAccountTitle'),
      t('auth.noAccountMessage')
    );
  };

  useEffect(() => {
    const paramEmail = typeof route?.params?.confirmationEmail === 'string'
      ? route.params.confirmationEmail.trim().toLowerCase()
      : '';
    if (paramEmail) {
      setEmail(paramEmail);
      setPendingConfirmationEmail(paramEmail);
    }
  }, [route?.params?.confirmationEmail]);

  // 60 seconds is an InternMatch UX cooldown,
  // NOT a claim about Supabase's actual server quota window.
  useEffect(() => {
    if (resendCooldownSeconds <= 0) return;
    const interval = setInterval(() => {
      setResendCooldownSeconds((prev) => {
        if (prev <= 1) {
          clearInterval(interval);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(interval);
  }, [resendCooldownSeconds]);

  const handleResendConfirmation = async () => {
    const targetEmail = pendingConfirmationEmail.trim().toLowerCase();
    if (!targetEmail || resendLoading || resendCooldownSeconds > 0) {
      return;
    }

    setResendLoading(true);
    try {
      const { error } = await resendSignupConfirmation(targetEmail);
      if (error) {
        throw error;
      }
      // 60 seconds is an InternMatch UX cooldown,
      // NOT a claim about Supabase's actual server quota window.
      setResendCooldownSeconds(60);
      haptics.success();
      Alert.alert(
        t('auth.emailConfirmation.resentTitle'),
        t('auth.emailConfirmation.resentMessage', { email: targetEmail })
      );
    } catch (err) {
      if (isAuthRateLimitError(err)) {
        // 60 seconds is an InternMatch UX cooldown,
        // NOT a claim about Supabase's actual server quota window.
        setResendCooldownSeconds(60);
        haptics.error();
        Alert.alert(t('common.error'), t('auth.emailConfirmation.rateLimit'));
      } else {
        haptics.error();
        Alert.alert(t('common.error'), t('auth.emailConfirmation.resendFailed'));
      }
    } finally {
      setResendLoading(false);
    }
  };

  const handleContinue = async () => {
    const normalizedEmail = email.trim().toLowerCase();

    if (!normalizedEmail || !password) {
      haptics.error();
      Alert.alert(t('common.error'), t('auth.enterEmailPassword'));
      return;
    }

    if (loading) return;

    setLoading(true);
    setLoadingSource('email');

    try {
      const { data, error } = await signInWithEmail(normalizedEmail, password);

      if (error) {
        throw error;
      }

      if (!data.session?.access_token) {
        throw new Error(t('errors.unauthorized'));
      }

      setPendingConfirmationEmail('');

      const syncResult = await syncAuthenticatedUser();
      if (syncResult.has_profile) {
        await refreshProfile();
        navigation.replace('MainTabs');
      } else {
        const meta = data.session?.user?.user_metadata || {};
        const metaName =
          typeof meta.full_name === 'string'
            ? meta.full_name.trim()
            : '';
        const metaDept =
          typeof meta.department === 'string'
            ? meta.department.trim()
            : '';
        const metaAccountType =
          meta.account_type === 'intern' || meta.account_type === 'employer'
            ? meta.account_type
            : null;

        // Email confirmation may complete after the original sign-up session
        // has ended. Only explicit sign-up metadata may finish that account.
        if (!metaName || !metaAccountType) {
          await rejectMissingCanonicalAccount();
          return;
        }

        await completeSignup({
          full_name: metaName,
          department: metaDept || null,
          account_type: metaAccountType,
        });
        await refreshProfile();
        navigation.replace('MainTabs');
      }
    } catch (error) {
      if (isEmailNotConfirmedError(error)) {
        setPendingConfirmationEmail(normalizedEmail);
        Alert.alert(
          t('auth.emailConfirmation.pendingTitle'),
          t('auth.emailConfirmation.pendingMessage', { email: normalizedEmail })
        );
        return;
      }

      if (isAuthRateLimitError(error)) {
        Alert.alert(t('common.error'), t('errors.authTooManyRequests'));
        return;
      }

      let errorKey = 'errors.authSignInFailed';
      const msg = error instanceof Error ? error.message.toLowerCase() : '';
      if (msg.includes('invalid login') || msg.includes('invalid credentials') || msg.includes('user not found')) {
        errorKey = 'errors.authInvalidCredentials';
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

    try {
      const result = await signInWithGoogle();

      if (result.cancelled) {
        return;
      }

      if (!result.session?.access_token) {
        throw new Error(t('errors.unauthorized'));
      }

      const syncResult = await syncAuthenticatedUser();
      if (!syncResult.has_profile) {
        await rejectMissingCanonicalAccount();
        return;
      }

      setPendingConfirmationEmail('');
      await refreshProfile();
      navigation.replace('MainTabs');
    } catch (error) {
      console.warn('Google sign-in failed:', error);
      haptics.error();

      Alert.alert(
        t('auth.googleSignIn'),
        t('errors.authSignInFailed')
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

      const syncResult = await syncAuthenticatedUser();
      if (!syncResult.has_profile) {
        await rejectMissingCanonicalAccount();
        return;
      }

      setPendingConfirmationEmail('');
      await refreshProfile();
      navigation.replace('MainTabs');
    } catch (error) {
      console.warn('Apple sign-in failed:', error);
      haptics.error();

      Alert.alert(
        t('auth.appleSignIn'),
        t('errors.authSignInFailed')
      );
    } finally {
      setLoading(false);
      setLoadingSource(null);
    }
  };

  const handleForgotPassword = () => {
    navigation.navigate('ForgotPassword', {
      email: email ? email.trim() : undefined,
    });
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
            <Text style={styles.title}>{t('auth.welcomeBack')}</Text>
            <Text style={styles.subtitle}>
              {t('auth.signInSubtitle')}
            </Text>
          </View>

          {/* Glass Authentication Panel */}
          <AuthGlassPanel style={styles.authPanel}>
            {/* Segmented Control */}
            <AuthSegmentedControl
              activeTab="signIn"
              onTabChange={(tab) => {
                if (tab === 'signUp') {
                  navigation.replace('SignUp');
                }
              }}
            />

            {/* Inline Pending Confirmation Panel */}
            {Boolean(pendingConfirmationEmail) && (
              <View style={styles.confirmationPanel}>
                <View style={styles.confirmationPanelHeader}>
                  <Ionicons
                    name="mail-unread-outline"
                    size={18}
                    color={colors.accentStrong || colors.tealDark}
                    style={styles.confirmationPanelIcon}
                  />
                  <Text style={styles.confirmationPanelTitle}>
                    {t('auth.emailConfirmation.pendingTitle')}
                  </Text>
                </View>
                <Text style={styles.confirmationPanelMessage}>
                  {t('auth.emailConfirmation.pendingMessage', { email: pendingConfirmationEmail })}
                </Text>
                <TouchableOpacity
                  style={[
                    styles.resendBtn,
                    (resendLoading || resendCooldownSeconds > 0) && styles.resendBtnDisabled,
                  ]}
                  onPress={handleResendConfirmation}
                  disabled={resendLoading || resendCooldownSeconds > 0}
                  activeOpacity={0.7}
                  accessibilityRole="button"
                  accessibilityLabel={
                    resendLoading
                      ? t('auth.emailConfirmation.resending')
                      : resendCooldownSeconds > 0
                      ? t('auth.emailConfirmation.resendIn', { seconds: resendCooldownSeconds })
                      : t('auth.emailConfirmation.resend')
                  }
                >
                  <Text
                    style={[
                      styles.resendBtnText,
                      (resendLoading || resendCooldownSeconds > 0) && styles.resendBtnTextDisabled,
                    ]}
                  >
                    {resendLoading
                      ? t('auth.emailConfirmation.resending')
                      : resendCooldownSeconds > 0
                      ? t('auth.emailConfirmation.resendIn', { seconds: resendCooldownSeconds })
                      : t('auth.emailConfirmation.resend')}
                  </Text>
                </TouchableOpacity>
              </View>
            )}

            {/* Email Field */}
            <View style={styles.fieldGroup}>
              <Text style={styles.fieldLabel}>{t('auth.email')}</Text>
              <TextInput
                style={[
                  styles.input,
                  focusedField === 'email' && styles.inputFocused,
                ]}
                value={email}
                onChangeText={setEmail}
                onFocus={() => setFocusedField('email')}
                onBlur={() => setFocusedField(null)}
                autoCapitalize="none"
                autoCorrect={false}
                keyboardType="email-address"
                placeholder="name@example.com"
                placeholderTextColor="rgba(22, 35, 46, 0.40)"
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
                    isRTL && styles.passwordInputRTL,
                  ]}
                  value={password}
                  onChangeText={setPassword}
                  onFocus={() => setFocusedField('password')}
                  onBlur={() => setFocusedField(null)}
                  secureTextEntry={!passwordVisible}
                  placeholder={t('auth.passwordPlaceholder')}
                  placeholderTextColor="rgba(22, 35, 46, 0.40)"
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
            </View>

            {/* Forgot Password */}
            <TouchableOpacity
              style={styles.forgotBtn}
              onPress={handleForgotPassword}
              hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
              accessibilityRole="button"
              accessibilityLabel={t('auth.forgotPassword')}
            >
              <Text style={styles.forgotText}>{t('auth.forgotPassword')}</Text>
            </TouchableOpacity>

            {/* Primary CTA */}
            {loadingSource === 'email' ? (
  <View
    style={[styles.primaryCta, styles.authLoadingButton]}
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
<GradientButton
              title={t('auth.signIn')}
              color={colors.accent || colors.teal}
              onPress={handleContinue}
              disabled={loading}
              style={styles.primaryCta}
            />
)}

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
              label={t('auth.signInWithGoogle')}
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
                    AppleAuthentication.AppleAuthenticationButtonType.SIGN_IN
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
  forgotBtn: {
    alignSelf: 'flex-end',
    marginBottom: spacing.lg,
    paddingVertical: spacing.xxs,
    minHeight: 28,
  },
  forgotText: {
    ...typography.caption,
    color: colors.accentStrong || colors.tealDark,
    fontWeight: '600',
  },
  primaryCta: {
    marginTop: spacing.xs,
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
  confirmationPanel: {
    backgroundColor: 'rgba(14, 116, 144, 0.08)',
    borderRadius: spacing.radii.md,
    borderWidth: 1,
    borderColor: 'rgba(14, 116, 144, 0.20)',
    padding: spacing.md,
    marginTop: spacing.md,
    marginBottom: spacing.xs,
  },
  confirmationPanelHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: spacing.xxs,
  },
  confirmationPanelIcon: {
    marginEnd: spacing.xs,
  },
  confirmationPanelTitle: {
    ...typography.bodyEmphasis,
    fontSize: 14,
    fontWeight: '700',
    color: colors.textPrimary || colors.textDark,
  },
  confirmationPanelMessage: {
    ...typography.caption,
    color: colors.textSecondary || colors.textMuted,
    lineHeight: 18,
    marginBottom: spacing.sm,
  },
  resendBtn: {
    alignSelf: 'flex-start',
    paddingVertical: spacing.xs,
    paddingHorizontal: spacing.sm + 2,
    borderRadius: spacing.radii.sm,
    backgroundColor: 'rgba(14, 116, 144, 0.12)',
  },
  resendBtnDisabled: {
    backgroundColor: 'rgba(14, 116, 144, 0.05)',
  },
  resendBtnText: {
    ...typography.caption,
    fontWeight: '700',
    color: colors.accentStrong || colors.tealDark,
  },
  resendBtnTextDisabled: {
    color: colors.textTertiary || colors.textMuted,
  },
  authLoadingButton: {
    minHeight: 50,
    borderRadius: 14,
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
