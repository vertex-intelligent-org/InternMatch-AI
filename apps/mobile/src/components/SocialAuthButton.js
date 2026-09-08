import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { useTranslation } from 'react-i18next';
import Svg, { Path } from 'react-native-svg';
import { Ionicons } from '@expo/vector-icons';
import colors from '../theme/colors';
import { spacing } from '../theme/spacing';
import { typography } from '../theme/typography';
import motionTokens from '../motion/motionTokens';
import PressableScale from './PressableScale';

function GoogleIcon() {
  return (
    <Svg width={20} height={20} viewBox="0 0 24 24">
      <Path
        fill="#4285F4"
        d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
      />
      <Path
        fill="#34A853"
        d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
      />
      <Path
        fill="#FBBC05"
        d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"
      />
      <Path
        fill="#EA4335"
        d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"
      />
    </Svg>
  );
}

function AppleIcon() {
  return <Ionicons name="logo-apple" size={20} color="#FFFFFF" />;
}

/**
 * Polished Social Authentication Button for Google & Apple.
 * @param {'google' | 'apple'} provider
 * @param {() => void} onPress
 */
export default function SocialAuthButton({
  provider = 'google',
  onPress,
  disabled = false,
  label,
  style,
}) {
  const { t } = useTranslation();
  const isGoogle = provider === 'google';
  const resolvedLabel = label || (isGoogle ? t('auth.continueWithGoogle') : t('auth.continueWithApple'));

  return (
    <PressableScale
      style={[
        styles.button,
        isGoogle ? styles.googleButton : styles.appleButton,
        disabled && styles.disabled,
        style,
      ]}
      onPress={onPress}
      disabled={disabled}
      scaleTo={motionTokens.scales.buttonPressed}
      activeOpacity={motionTokens.opacities.pressed}
      haptic={disabled ? 'none' : 'light'}
      accessibilityRole="button"
      accessibilityLabel={resolvedLabel}
      hitSlop={{ top: 6, bottom: 6, left: 6, right: 6 }}
    >
      <View style={styles.iconContainer}>
        {isGoogle ? <GoogleIcon /> : <AppleIcon />}
      </View>
      <Text
        style={[
          styles.text,
          isGoogle ? styles.googleText : styles.appleText,
        ]}
      >
        {resolvedLabel}
      </Text>
    </PressableScale>
  );
}

const styles = StyleSheet.create({
  button: {
    height: 48,
    minHeight: spacing.minimumTouchTarget,
    borderRadius: spacing.radii.pill,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: spacing.lg,
    width: '100%',
  },
  googleButton: {
    backgroundColor: '#FFFFFF',
    borderWidth: 1,
    borderColor: 'rgba(14, 116, 144, 0.18)',
    shadowColor: 'rgba(7, 43, 56, 0.08)',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 1,
    shadowRadius: 4,
    elevation: 1,
  },
  appleButton: {
    backgroundColor: '#000000',
    borderWidth: 1,
    borderColor: '#000000',
    shadowColor: '#000000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.15,
    shadowRadius: 4,
    elevation: 2,
  },
  iconContainer: {
    width: 24,
    height: 24,
    alignItems: 'center',
    justifyContent: 'center',
    marginEnd: spacing.sm + 2,
  },
  text: {
    ...typography.button,
    fontSize: 16,
    fontWeight: '600',
  },
  googleText: {
    color: colors.textDark,
  },
  appleText: {
    color: '#FFFFFF',
  },
  disabled: {
    opacity: 0.6,
  },
});
