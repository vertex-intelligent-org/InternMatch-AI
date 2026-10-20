import React from 'react';
import { StyleSheet, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTranslation } from 'react-i18next';
import { useAppTheme } from '../context/ThemeProvider';
import { spacing } from '../theme/spacing';
import PressableScale from './PressableScale';

export default function BookmarkButton({
  isSaved = false,
  onPress,
  disabled = false,
  size = 22,
  style,
  hitSlop = { top: 8, bottom: 8, left: 8, right: 8 },
}) {
  const { colors } = useAppTheme();
  const { t } = useTranslation();
  const iconColor = isSaved ? colors.accentStrong : colors.textTertiary;

  const iconName = isSaved ? 'bookmark' : 'bookmark-outline';

  return (
    <PressableScale
      style={[styles.container, style]}
      onPress={onPress}
      disabled={disabled}
      haptic="light"
      hitSlop={hitSlop}
      accessibilityRole="button"
      accessibilityLabel={
        isSaved ? t('components.bookmarkRemoveA11y') : t('components.bookmarkSaveA11y')
      }
      accessibilityState={{ selected: isSaved, disabled }}
    >
      <View style={styles.iconWrap}>
        <Ionicons name={iconName} size={size} color={iconColor} />
      </View>
    </PressableScale>
  );
}

const styles = StyleSheet.create({
  container: {
    minWidth: spacing.minimumTouchTarget || 44,
    minHeight: spacing.minimumTouchTarget || 44,
    alignItems: 'center',
    justifyContent: 'center',
  },
  iconWrap: {
    alignItems: 'center',
    justifyContent: 'center',
  },
});
