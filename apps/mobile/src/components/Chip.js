import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useAppTheme } from '../context/ThemeProvider';
import { spacing } from '../theme/spacing';
import { typography } from '../theme/typography';
import motionTokens from '../motion/motionTokens';
import PressableScale from './PressableScale';

// variant: 'skill' (mint green) | 'gap' (orange outline) | 'neutral'
export default function Chip({ label, variant = 'skill', onRemove, selected, onPress }) {
  const { colors, isDark } = useAppTheme();
  const palette = {
    skill: {
      bg: colors.greenBg,
      fg: isDark ? colors.success : '#0F8A5F',
    },
    gap: {
      bg: isDark ? colors.warningSoft : colors.white,
      fg: isDark ? colors.warning : colors.orange,
      border: isDark ? colors.warning : colors.orange,
    },
    neutral: {
      bg: isDark ? colors.surfaceMuted : '#EDEDED',
      fg: isDark ? colors.textSecondary : colors.textMuted,
    },
  }[variant] || {
    bg: isDark ? colors.surfaceMuted : '#EDEDED',
    fg: isDark ? colors.textSecondary : colors.textMuted,
  };
  const selectedTextColor = colors.white;

  const content = (
    <View
      style={[
        styles.chip,
        { backgroundColor: selected ? colors.teal : palette.bg },
        palette.border ? { borderWidth: 1, borderColor: palette.border } : null,
      ]}
    >
      <Text style={[styles.label, { color: selected ? selectedTextColor : palette.fg }]}>
        {label}
      </Text>
      {onRemove ? (
        <TouchableOpacity
          onPress={onRemove}
          hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
          accessibilityRole="button"
          accessibilityLabel={`Remove ${label}`}
        >
          <Ionicons name="close" size={14} color={selected ? selectedTextColor : palette.fg} style={styles.removeIcon} />
        </TouchableOpacity>
      ) : null}
    </View>
  );

  if (onPress) {
    return (
      <PressableScale
        onPress={onPress}
        scaleTo={motionTokens.scales.chipPressed}
        activeOpacity={motionTokens.opacities.subtlePressed}
        haptic="selection"
        accessibilityRole="button"
        accessibilityLabel={label}
      >
        {content}
      </PressableScale>
    );
  }

  return content;
}

const styles = StyleSheet.create({
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs + 2,
    borderRadius: spacing.radii.pill,
    marginEnd: spacing.sm,
    marginBottom: spacing.sm,
  },
  label: {
    ...typography.badge,
    fontSize: 13,
  },
  removeIcon: {
    marginStart: spacing.xs,
  },
});
