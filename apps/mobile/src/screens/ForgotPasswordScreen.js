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
  ScrollView,
} from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useTranslation } from 'react-i18next';
import { useLocalization } from '../localization/LocalizationContext';
import { useAppTheme } from '../context/ThemeProvider';
import { spacing } from '../theme/spacing';
import { typography } from '../theme/typography';
import InternMatchLogo from '../components/InternMatchLogo';
import AuthGlassPanel from '../components/AuthGlassPanel';
import GradientButton from '../components/GradientButton';
import BackButton from '../components/BackButton';
import PressableScale from '../components/PressableScale';
import motionTokens from '../motion/motionTokens';
import { sendPasswordResetEmail } from '../services/auth';
import { PASSWORD_RESET_REDIRECT_URL } from '../services/passwordRecovery';
import haptics from '../services/haptics';

export default function ForgotPasswordScreen({ navigation, route }) {
  const { colors, isDark } = useAppTheme();
  const styles = createStyles(colors);
  const { t } = useTranslation();
  const { isRTL } = useLocalization();
  const insets = useSafeAreaInsets();

  const initialEmail = typeof route?.params?.email === 'string' ? route.params.email.trim() : '';
  const [email, setEmail] = useState(initialEmail);
  const [focusedField, setFocusedField] = useState(null);
  const [loading, setLoading] = useState(false);
  const requestInFlightRef = useRef(false);
  const [isSubmitted, setIsSubmitted] = useState(false);

  const validateEmail = (input) => {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(input);
  };

  const handleSendReset = async () => {
    const normalizedEmail = email.trim().toLowerCase();

    if (!normalizedEmail || !validateEmail(normalizedEmail)) {
      haptics.error();
      Alert.alert(
        t('common.error'),
        t('passwordRecovery.forgotPassword.invalidEmail')
      );
      return;
    }

    if (requestInFlightRef.current) return;
    requestInFlightRef.current = true;
    setLoading(true);

    try {
      const { error } = await sendPasswordResetEmail(
        normalizedEmail,
        PASSWORD_RESET_REDIRECT_URL
      );

      if (error) {
        const errorMsg = (error.message || '').toLowerCase();
        if (errorMsg.includes('rate limit') || errorMsg.includes('too many requests')) {
          haptics.error();
          Alert.alert(t('common.error'), t('passwordRecovery.errors.rateLimit'));
          return;
        }
        if (errorMsg.includes('network') || errorMsg.includes('fetch') || errorMsg.includes('connection')) {
          haptics.error();
          Alert.alert(t('common.error'), t('passwordRecovery.errors.network'));
          return;
        }
        haptics.error();
        Alert.alert(t('common.error'), t('passwordRecovery.errors.generic'));
        return;
      }

      // Generic success state for all emails to prevent account enumeration
      haptics.success();
      setIsSubmitted(true);
    } catch (err) {
      const errorMsg = err instanceof Error ? err.message.toLowerCase() : '';
      haptics.error();
      if (errorMsg.includes('network') || errorMsg.includes('fetch') || errorMsg.includes('connection')) {
        Alert.alert(t('common.error'), t('passwordRecovery.errors.network'));
      } else if (errorMsg.includes('rate limit') || errorMsg.includes('too many requests')) {
        Alert.alert(t('common.error'), t('passwordRecovery.errors.rateLimit'));
      } else {
        Alert.alert(t('common.error'), t('passwordRecovery.errors.generic'));
      }
    } finally {
      requestInFlightRef.current = false;
      setLoading(false);
    }
  };

  const handleBackToSignIn = () => {
    navigation.navigate('SignIn');
  };

  return (
    <LinearGradient
      colors={
        isDark
          ? [
              colors.authGradientStart,
              colors.authGradientMid,
              colors.authGradientEnd,
            ]
          : [
              colors.authGradientStart,
              colors.authGradientMid,
              colors.authGradientEnd,
            ]
      }
      style={styles.container}
    >
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={styles.flex}
      >
        {/* Top Header with Back Navigation */}
        <View
          style={[
            styles.topNav,
            { paddingTop: Math.max(insets.top, 12) + spacing.xs },
            isRTL && styles.rowRTL,
          ]}
        >
          <BackButton
            navigation={navigation}
            onPress={() => navigation.goBack()}
            accessibilityLabel={t('navigation.back.label')}
          />
        </View>

        <ScrollView
          contentContainerStyle={[
            styles.scrollContent,
            {
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
            <Text style={[styles.title, isRTL && styles.textRTL]}>
              {isSubmitted
                ? t('passwordRecovery.forgotPassword.sentTitle')
                : t('passwordRecovery.forgotPassword.title')}
            </Text>
            <Text style={[styles.subtitle, isRTL && styles.textRTL]}>
              {isSubmitted
                ? t('passwordRecovery.forgotPassword.sentMessage')
                : t('passwordRecovery.forgotPassword.subtitle')}
            </Text>
          </View>

          {/* Glass Authentication Panel */}
          <AuthGlassPanel style={styles.authPanel}>
            {isSubmitted ? (
              <View style={styles.successContainer}>
                <View style={styles.iconCircle}>
                  <Ionicons
                    name="mail-outline"
                    size={38}
                    color={colors.accent || colors.teal}
                  />
                </View>

                <GradientButton
                  title={t('passwordRecovery.forgotPassword.backToSignIn')}
                  color={colors.accent || colors.teal}
                  onPress={handleBackToSignIn}
                  style={styles.primaryCta}
                  accessibilityLabel={t('passwordRecovery.accessibility.backToSignIn')}
                />

                <TouchableOpacity
                  style={styles.retryLink}
                  onPress={() => setIsSubmitted(false)}
                  hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
                  accessibilityRole="button"
                  accessibilityLabel={t('passwordRecovery.forgotPassword.sendButton')}
                >
                  <Text style={styles.retryLinkText}>
                    {t('passwordRecovery.forgotPassword.sendButton')}
                  </Text>
                </TouchableOpacity>
              </View>
            ) : (
              <>
                {/* Email Field */}
                <View style={styles.fieldGroup}>
                  <Text style={[styles.fieldLabel, isRTL && styles.textRTL]}>
                    {t('passwordRecovery.forgotPassword.emailLabel')}
                  </Text>
                  <TextInput
                    style={[
                      styles.input,
                      focusedField === 'email' && styles.inputFocused,
                      isRTL && styles.inputRTL,
                    ]}
                    value={email}
                    onChangeText={setEmail}
                    onFocus={() => setFocusedField('email')}
                    onBlur={() => setFocusedField(null)}
                    autoCapitalize="none"
                    autoCorrect={false}
                    keyboardType="email-address"
                    placeholder={t('passwordRecovery.forgotPassword.emailPlaceholder')}
                    placeholderTextColor={colors.textTertiary}
                    accessibilityLabel={t('passwordRecovery.accessibility.email')}
                  />
                </View>

                {/* Submit Reset Link CTA */}
                <GradientButton
                  title={
                    loading
                      ? t('passwordRecovery.forgotPassword.sendingButton')
                      : t('passwordRecovery.forgotPassword.sendButton')
                  }
                  color={colors.accent || colors.teal}
                  onPress={handleSendReset}
                  disabled={loading}
                  style={styles.primaryCta}
                  accessibilityLabel={t('passwordRecovery.accessibility.sendResetLink')}
                />

                {/* Back to Sign In Link */}
                <View style={styles.footerRow}>
                  <PressableScale
                    onPress={handleBackToSignIn}
                    scaleTo={motionTokens.scales.chipPressed}
                    activeOpacity={motionTokens.opacities.pressed}
                    haptic="none"
                    accessibilityRole="button"
                    accessibilityLabel={t('passwordRecovery.accessibility.backToSignIn')}
                    hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
                  >
                    <Text style={styles.backLink}>
                      {t('passwordRecovery.forgotPassword.backToSignIn')}
                    </Text>
                  </PressableScale>
                </View>
              </>
            )}
          </AuthGlassPanel>
        </ScrollView>
      </KeyboardAvoidingView>
    </LinearGradient>
  );
}

const createStyles = (colors) => StyleSheet.create({
  container: {
    flex: 1,
  },
  flex: {
    flex: 1,
  },
  topNav: {
    paddingHorizontal: spacing.screenHorizontalPadding,
    flexDirection: 'row',
    alignItems: 'center',
  },
  scrollContent: {
    paddingHorizontal: spacing.screenHorizontalPadding,
    alignItems: 'center',
    paddingTop: spacing.xs,
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
    marginBottom: spacing.lg,
  },
  fieldLabel: {
    ...typography.caption,
    fontWeight: '600',
    color: colors.textPrimary || colors.textDark,
    marginBottom: spacing.xs,
  },
  input: {
    backgroundColor: colors.surface,
    borderRadius: spacing.radii.md,
    minHeight: 48,
    paddingHorizontal: spacing.md,
    borderWidth: 1.5,
    borderColor: 'rgba(14, 116, 144, 0.16)',
    color: colors.textDark,
    ...typography.body,
  },
  inputFocused: {
    borderColor: colors.accent || colors.teal,
    backgroundColor: colors.surface,
    shadowColor: colors.accent || colors.teal,
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.12,
    shadowRadius: 4,
    elevation: 2,
  },
  inputRTL: {
    textAlign: 'right',
  },
  primaryCta: {
    marginTop: spacing.xs,
  },
  footerRow: {
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: spacing.xl,
    paddingTop: spacing.xs,
  },
  backLink: {
    ...typography.caption,
    color: colors.accentStrong || colors.tealDark,
    fontWeight: '600',
  },
  successContainer: {
    alignItems: 'center',
    paddingVertical: spacing.sm,
  },
  iconCircle: {
    width: 72,
    height: 72,
    borderRadius: 36,
    backgroundColor: 'rgba(14, 116, 144, 0.10)',
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: spacing.lg,
  },
  retryLink: {
    marginTop: spacing.lg,
    paddingVertical: spacing.xs,
  },
  retryLinkText: {
    ...typography.caption,
    color: colors.textSecondary || colors.textMuted,
    fontWeight: '600',
  },
  rowRTL: {
    flexDirection: 'row-reverse',
  },
  textRTL: {
    textAlign: 'right',
    writingDirection: 'rtl',
  },
});
