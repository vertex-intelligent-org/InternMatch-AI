import React from 'react';
import { useTranslation } from 'react-i18next';
import { StyleSheet } from 'react-native';
import { useLocalization } from '../localization/LocalizationContext';
import { Ionicons } from '@expo/vector-icons';
import { useAppTheme } from '../context/ThemeProvider';
import { spacing } from '../theme/spacing';
import motionTokens from '../motion/motionTokens';
import PressableScale from './PressableScale';

export default function BackButton({
  navigation,
  onPress,
  color,
  style,
  accessibilityLabel,
  accessibilityHint,
}) {
  const { t } = useTranslation();
  const { isRTL } = useLocalization();
  const { colors } = useAppTheme();
  const resolvedColor = color || colors.textPrimary || colors.textDark;
  const resolvedAccessibilityLabel = accessibilityLabel ?? t('navigation.back.label');
  const resolvedAccessibilityHint = accessibilityHint ?? t('navigation.back.hint');

  const handlePress = () => {
    if (onPress) {
      onPress();
    } else if (navigation && typeof navigation.goBack === 'function') {
      navigation.goBack();
    }
  };

  return (
    <PressableScale
      style={[styles.button, style]}
      onPress={handlePress}
      scaleTo={motionTokens.scales.iconPressed}
      activeOpacity={0.7}
      haptic="none"
      accessibilityRole="button"
      accessibilityLabel={resolvedAccessibilityLabel}
      accessibilityHint={resolvedAccessibilityHint}
      hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
    >
      <Ionicons name={isRTL ? 'arrow-forward' : 'arrow-back'} size={22} color={resolvedColor} />
    </PressableScale>
  );
}

const styles = StyleSheet.create({
  button: {
    width: spacing.minimumTouchTarget,
    height: spacing.minimumTouchTarget,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
