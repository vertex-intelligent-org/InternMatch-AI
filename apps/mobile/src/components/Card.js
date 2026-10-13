import React from 'react';
import { View, StyleSheet } from 'react-native';
import colors from '../theme/colors';
import { useAppTheme } from '../context/ThemeProvider';
import { spacing } from '../theme/spacing';

export default function Card({
  children,
  style,
  padding = 'md',
  variant = 'default',
}) {
  const { colors } = useAppTheme();
  const paddingValue = {
    none: 0,
    sm: spacing.sm,
    md: spacing.lg,
    lg: spacing.xl,
  }[padding] ?? spacing.lg;

  const variantStyle = {
    default: styles.default,
    subtle: styles.subtle,
    elevated: styles.elevated,
    highlight: styles.highlight,
  }[variant] ?? styles.default;

  return (
    <View
      style={[
        styles.base,
        variantStyle,
        {
          padding: paddingValue,
          backgroundColor:
            variant === 'subtle'
              ? colors.surfaceSubtle
              : colors.surface,
          borderColor:
            variant === 'highlight'
              ? colors.accent
              : colors.borderSubtle,
        },
        style,
      ]}
    >
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  base: {
    backgroundColor: colors.surface || colors.cardBg,
    borderRadius: spacing.radii.lg,
    borderWidth: 1,
    borderColor: colors.borderSubtle || colors.border,
  },
  default: {
    shadowColor: '#000000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.04,
    shadowRadius: 4,
    elevation: 1,
  },
  subtle: {
    backgroundColor: colors.surfaceSubtle || '#F8FAFC',
    borderColor: colors.borderSubtle || colors.border,
    shadowOpacity: 0,
    elevation: 0,
  },
  elevated: {
    shadowColor: '#000000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.08,
    shadowRadius: 8,
    elevation: 2,
  },
  highlight: {
    borderColor: 'rgba(14, 116, 144, 0.3)',
    shadowColor: colors.teal,
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.06,
    shadowRadius: 6,
    elevation: 1,
  },
});
