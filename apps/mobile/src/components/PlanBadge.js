import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { useTranslation } from 'react-i18next';
import { useAppTheme } from '../context/ThemeProvider';
import { spacing } from '../theme/spacing';
import { typography } from '../theme/typography';

function getPlanLabel(plan, t) {
  const normalized = (plan || 'free').toString().toLowerCase().replace(/-/g, '_');
  switch (normalized) {
    case 'free':
      return t('components.planBadgeFree', { defaultValue: 'Free Plan' });
    case 'pro_student':
      return t('components.planBadgeProStudent', { defaultValue: 'Pro Student' });
    case 'employer':
      return t('components.planBadgeEmployer', { defaultValue: 'Employer' });
    case 'employer_pro':
      return t('components.planBadgeEmployerPro', { defaultValue: 'Employer Pro' });
    default:
      return t('components.planBadgeUnknown', { defaultValue: 'Plan' });
  }
}

export default function PlanBadge({ plan = 'free', style, onPress }) {
  const { t } = useTranslation();
  const { colors } = useAppTheme();
  const styles = createStyles(colors);
  const label = getPlanLabel(plan, t);

  const content = (
    <Text
      style={styles.badgeText}
      numberOfLines={1}
      adjustsFontSizeToFit
      minimumFontScale={0.8}
    >
      {label}
    </Text>
  );

  if (typeof onPress === 'function') {
    return (
      <TouchableOpacity
        style={[styles.badge, style]}
        onPress={onPress}
        activeOpacity={0.7}
        accessibilityRole="button"
        accessibilityLabel={t('plans.accessibility.badgeHint', {
          plan: label,
          defaultValue: `${label} - View plans`,
        })}
        hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
      >
        {content}
      </TouchableOpacity>
    );
  }

  return (
    <View style={[styles.badge, style]} accessibilityRole="text">
      {content}
    </View>
  );
}

const createStyles = (colors) => StyleSheet.create({
  badge: {
    maxWidth: 130,
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xxs + 2,
    borderRadius: spacing.radii.pill,
    backgroundColor: colors.accentSoft || '#E6F4F6',
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: 'rgba(14, 116, 144, 0.20)',
    alignItems: 'center',
    justifyContent: 'center',
    alignSelf: 'center',
  },
  badgeText: {
    ...typography.badge,
    fontSize: 11,
    lineHeight: 13,
    fontWeight: '700',
    letterSpacing: 0.3,
    color: colors.accentStrong || colors.tealDark,
    textAlign: 'center',
    includeFontPadding: false,
  },
});
