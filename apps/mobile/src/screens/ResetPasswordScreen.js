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
import PressableScale from '../components/PressableScale';
import motionTokens from '../motion/motionTokens';
import { updatePassword } from '../services/auth';
import { useProfile } from '../context/ProfileContext';
import haptics from '../services/haptics';

export default function ResetPasswordScreen({ navigation, route }) {
  const { colors, isDark } = useAppTheme();
  const styles = createStyles(colors);
  const { t } = useTranslation();
  const { isRTL } = useLocalization();
  const insets = useSafeAreaInsets();
  const { clearProfile } = useProfile();

  const hasRecoveryAuthorization = route?.params?.recoveryVerified === true;
  const isRecoveryError = !hasRecoveryAuthorization;

  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [focusedField, setFocusedField] = useState(null);
  const [loading, setLoading] = useState(false);
  const updateInFlightRef = useRef(false);

  const handleUpdatePassword = async () => {
    if (!password || !confirmPassword) {
      haptics.error();
      Alert.alert(
        t('common.error'),
        t('passwordRecovery.resetPassword.passwordMinLength')
      );
      return;
    }

    if (password.length < 6) {
      haptics.error();
      Alert.alert(
        t('common.error'),
        t('passwordRecovery.resetPassword.passwordMinLength')
      );
      return;
    }

    if (password !== confirmPassword) {
      haptics.error();
      Alert.alert(
        t('common.error'),
        t('passwordRecovery.resetPassword.passwordsMismatch')
      );
      return;
    }

    if (updateInFlightRef.current) return;
    updateInFlightRef.current = true;
    setLoading(true);

    try {
      const { error } = await updatePassword(password);

      if (error) {
        const errorMsg = (error.message || '').toLowerCase();
        haptics.error();
        if (errorMsg.includes('weak') || errorMsg.includes('should be') || errorMsg.includes('characters')) {
          Alert.alert(t('common.error'), t('passwordRecovery.errors.weakPassword'));
        } else {
          Alert.alert(t('common.error'), t('passwordRecovery.errors.updateFailed'));
        }
        return;
      }

      // Password update succeeded
      haptics.success();
      try {
        clearProfile();
      } catch {
        // Safe fallback
      }

      Alert.alert(
        t('passwordRecovery.resetPassword.successTitle'),
        t('passwordRecovery.resetPassword.successMessage'),
        [
          {
            text: t('passwordRecovery.resetPassword.successAction'),
            onPress: () => {
              navigation.reset({
                index: 0,
                routes: [{ name: 'Splash' }],
              });
            },
          },
        ],
        { cancelable: false }
      );
    } catch {
      haptics.error();
      Alert.alert(t('common.error'), t('passwordRecovery.errors.updateFailed'));
    } finally {
      updateInFlightRef.current = false;
      setLoading(false);
    }
  };

  const handleRequestNewLink = () => {
    navigation.navigate('ForgotPassword');
  };

  const handleBackToSignIn = () => {
    navigation.reset({
      index: 0,
      routes: [{ name: 'SignIn' }],
    });
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
            <Text style={[styles.title, isRTL && styles.textRTL]}>
              {isRecoveryError
                ? t('passwordRecovery.resetPassword.expiredTitle')
                : t('passwordRecovery.resetPassword.title')}
            </Text>
            <Text style={[styles.subtitle, isRTL && styles.textRTL]}>
              {isRecoveryError
                ? t('passwordRecovery.resetPassword.expiredMessage')
                : t('passwordRecovery.resetPassword.subtitle')}
            </Text>
          </View>

          {/* Glass Authentication Panel */}
          <AuthGlassPanel style={styles.authPanel}>
            {isRecoveryError ? (
              <View style={styles.errorContainer}>
                <View style={styles.errorIconCircle}>
                  <Ionicons
                    name="alert-circle-outline"
                    size={42}
                    color={colors.danger || colors.red}
                  />
                </View>

                <GradientButton
                  title={t('passwordRecovery.resetPassword.requestNewLink')}
                  color={colors.accent || colors.teal}
                  onPress={handleRequestNewLink}
                  style={styles.primaryCta}
                  accessibilityLabel={t('passwordRecovery.accessibility.requestNewLink')}
                />

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
                      {t('passwordRecovery.resetPassword.backToSignIn')}
                    </Text>
                  </PressableScale>
                </View>
              </View>
            ) : (
              <>
                {/* New Password Field */}
                <View style={styles.fieldGroup}>
                  <Text style={[styles.fieldLabel, isRTL && styles.textRTL]}>
                    {t('passwordRecovery.resetPassword.newPasswordLabel')}
                  </Text>
                  <View style={styles.passwordInputWrapper}>
                    <TextInput
                      style={[
                        styles.input,
                        styles.passwordInput,
                        focusedField === 'password' && styles.inputFocused,
                        isRTL && styles.inputRTL,
                      ]}
                      value={password}
                      onChangeText={setPassword}
                      onFocus={() => setFocusedField('password')}
                      onBlur={() => setFocusedField(null)}
                      secureTextEntry={!showPassword}
                      placeholder={t('passwordRecovery.resetPassword.newPasswordPlaceholder')}
                      placeholderTextColor={colors.textTertiary}
                      accessibilityLabel={t('passwordRecovery.accessibility.newPassword')}
                    />
                    <TouchableOpacity
                      style={[styles.eyeButton, isRTL && styles.eyeButtonRTL]}
                      onPress={() => setShowPassword((prev) => !prev)}
                      hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
                      accessibilityRole="button"
                      accessibilityLabel={showPassword ? t('passwordRecovery.accessibility.hidePassword') : t('passwordRecovery.accessibility.showPassword')}
                    >
                      <Ionicons
                        name={showPassword ? 'eye-off-outline' : 'eye-outline'}
                        size={20}
                        color={colors.textSecondary || colors.textMuted}
                      />
                    </TouchableOpacity>
                  </View>
                </View>

                {/* Confirm Password Field */}
                <View style={styles.fieldGroup}>
                  <Text style={[styles.fieldLabel, isRTL && styles.textRTL]}>
                    {t('passwordRecovery.resetPassword.confirmPasswordLabel')}
                  </Text>
                  <View style={styles.passwordInputWrapper}>
                    <TextInput
                      style={[
                        styles.input,
                        styles.passwordInput,
                        focusedField === 'confirmPassword' && styles.inputFocused,
                        isRTL && styles.inputRTL,
                      ]}
                      value={confirmPassword}
                      onChangeText={setConfirmPassword}
                      onFocus={() => setFocusedField('confirmPassword')}
                      onBlur={() => setFocusedField(null)}
                      secureTextEntry={!showConfirmPassword}
                      placeholder={t('passwordRecovery.resetPassword.confirmPasswordPlaceholder')}
                      placeholderTextColor={colors.textTertiary}
                      accessibilityLabel={t('passwordRecovery.accessibility.confirmPassword')}
                    />
                    <TouchableOpacity
                      style={[styles.eyeButton, isRTL && styles.eyeButtonRTL]}
                      onPress={() => setShowConfirmPassword((prev) => !prev)}
                      hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
                      accessibilityRole="button"
                      accessibilityLabel={showConfirmPassword ? t('passwordRecovery.accessibility.hidePassword') : t('passwordRecovery.accessibility.showPassword')}
                    >
                      <Ionicons
                        name={showConfirmPassword ? 'eye-off-outline' : 'eye-outline'}
                        size={20}
                        color={colors.textSecondary || colors.textMuted}
                      />
                    </TouchableOpacity>
                  </View>
                </View>

                {/* Update Password CTA */}
                <GradientButton
                  title={
                    loading
                      ? t('passwordRecovery.resetPassword.submittingButton')
                      : t('passwordRecovery.resetPassword.submitButton')
                  }
                  color={colors.accent || colors.teal}
                  onPress={handleUpdatePassword}
                  disabled={loading}
                  style={styles.primaryCta}
                  accessibilityLabel={t('passwordRecovery.accessibility.updatePassword')}
                />

                {/* Return to Sign In Link */}
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
                      {t('passwordRecovery.resetPassword.backToSignIn')}
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
  passwordInputWrapper: {
    position: 'relative',
    justifyContent: 'center',
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
  passwordInput: {
    paddingRight: 44,
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
    paddingRight: spacing.md,
    paddingLeft: 44,
  },
  eyeButton: {
    position: 'absolute',
    right: 12,
    height: 48,
    justifyContent: 'center',
    alignItems: 'center',
    width: 32,
  },
  eyeButtonRTL: {
    right: undefined,
    left: 12,
  },
  primaryCta: {
    marginTop: spacing.sm,
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
  errorContainer: {
    alignItems: 'center',
    paddingVertical: spacing.sm,
  },
  errorIconCircle: {
    width: 72,
    height: 72,
    borderRadius: 36,
    backgroundColor: 'rgba(239, 68, 68, 0.10)',
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: spacing.lg,
  },
  textRTL: {
    textAlign: 'right',
    writingDirection: 'rtl',
  },
});
