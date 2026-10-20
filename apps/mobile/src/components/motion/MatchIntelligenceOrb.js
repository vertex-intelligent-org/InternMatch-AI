import React, { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { View, Text, StyleSheet } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { Ionicons } from '@expo/vector-icons';
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withSpring,
  withTiming,
} from 'react-native-reanimated';
import { useAppTheme } from '../../context/ThemeProvider';
import { spacing } from '../../theme/spacing';
import { typography } from '../../theme/typography';
import motionTokens from '../../motion/motionTokens';
import useReducedMotion from '../../hooks/useReducedMotion';
import AIPulse from './AIPulse';

export default function MatchIntelligenceOrb({
  score,
  topMatch,
  hasAnalyzedCV = false,
  isCalculating = false,
  progressPercent = 0,
  style,
}) {
  const { colors, isDark } = useAppTheme();
  const styles = createStyles(colors, isDark);
  const { t } = useTranslation();
  const isReducedMotion = useReducedMotion();
  const scale = useSharedValue(isReducedMotion ? 1 : motionTokens.scales.orbSettleStart);
  const opacity = useSharedValue(isReducedMotion ? 1 : 0);

  useEffect(() => {
    if (isReducedMotion) {
      scale.value = 1;
      opacity.value = 1;
      return;
    }

    scale.value = withSpring(1, motionTokens.spring.hero);
    opacity.value = withTiming(1, { duration: motionTokens.durations.reveal + 100 });
  }, [isReducedMotion, opacity, scale]);

  const animatedOrbStyle = useAnimatedStyle(() => {
    if (isReducedMotion) {
      return { opacity: 1, transform: [{ scale: 1 }] };
    }
    return {
      opacity: opacity.value,
      transform: [{ scale: scale.value }],
    };
  });

  // Determine state labels and content
  let statusEyebrow = t('home.orb.eyebrow');
  let primaryContent = null;
  let subtitleText = '';
  let accessibilityLabelText = '';

  if (isCalculating) {
    statusEyebrow = t('home.orb.progressEyebrow');
    primaryContent = (
      <View style={styles.centerScoreWrap}>
        <Text style={[styles.scoreNumber, { writingDirection: 'ltr' }]}>{progressPercent}%</Text>
        <Text style={styles.scoreUnit}>{t('home.orb.analyzing')}</Text>
      </View>
    );
    subtitleText = t('home.orb.comparing');
    accessibilityLabelText = t('home.orb.a11yCalculating', { progress: progressPercent });
  } else if (hasAnalyzedCV && typeof score === 'number' && score > 0) {
    statusEyebrow = t('home.orb.eyebrow');
    primaryContent = (
      <View style={styles.centerScoreWrap}>
        <Text style={[styles.scoreNumber, { writingDirection: 'ltr' }]}>{score}%</Text>
        <Text style={styles.scoreUnit}>{t('home.orb.topMatch')}</Text>
      </View>
    );
    subtitleText = topMatch?.internship
      ? `${topMatch.internship.title} \u00b7 ${topMatch.internship.company}`
      : t('home.orb.compatibilityBackground');
    accessibilityLabelText = topMatch?.internship ? t('home.orb.a11yTopWithInternship', { score, title: topMatch.internship.title, company: topMatch.internship.company }) : t('home.orb.a11yTop', { score });
  } else if (hasAnalyzedCV) {
    statusEyebrow = t('home.orb.eyebrow');
    primaryContent = (
      <View style={styles.centerScoreWrap}>
        <Ionicons name="sparkles" size={32} color={colors.accent || colors.teal} />
        <Text style={styles.stateLabel}>{t('home.orb.ready')}</Text>
      </View>
    );
    subtitleText = t('home.orb.readySubtitle');
    accessibilityLabelText = t('home.orb.a11yReady');
  } else {
    statusEyebrow = t('home.orb.eyebrow');
    primaryContent = (
      <View style={styles.centerScoreWrap}>
        <Ionicons name="document-text-outline" size={32} color={colors.accent || colors.teal} />
        <Text style={styles.stateLabel}>{t('home.orb.cvNeeded')}</Text>
      </View>
    );
    subtitleText = t('home.orb.cvNeededSubtitle');
    accessibilityLabelText = t('home.orb.a11yCvNeeded');
  }

  return (
    <AIPulse active={isCalculating} style={[styles.container, style]}>
      <Animated.View
        style={[styles.orbCard, animatedOrbStyle]}
        accessibilityRole="summary"
        accessibilityLabel={accessibilityLabelText}
      >
        <LinearGradient
          colors={isDark ? [colors.surfaceElevated, colors.surface] : ['#FFFFFF', '#F0F9FA']}
          start={{ x: 0, y: 0 }}
          end={{ x: 0, y: 1 }}
          style={styles.cardGradient}
        >
          <View style={styles.topRow}>
            <View style={styles.badge}>
              <View style={styles.activeDot} />
              <Text style={styles.eyebrowText}>{statusEyebrow}</Text>
            </View>
          </View>

          <View style={styles.orbStructure}>
            {/* Outer Subtle Halo */}
            <View style={styles.outerRing}>
              {/* Inner Surface */}
              <LinearGradient
                colors={isDark ? [colors.accentSoft, colors.surfaceMuted] : ['#E6F4F6', '#D1EDF2']}
                style={styles.innerCircle}
              >
                {primaryContent}
              </LinearGradient>
            </View>
          </View>

          <Text style={styles.subtitle} numberOfLines={2}>
            {subtitleText}
          </Text>
        </LinearGradient>
      </Animated.View>
    </AIPulse>
  );
}

const createStyles = (colors, isDark) => StyleSheet.create({
  container: {
    width: '100%',
    marginBottom: spacing.lg,
  },
  orbCard: {
    borderRadius: spacing.radii.lg,
    borderWidth: 1,
    borderColor: isDark ? colors.border : 'rgba(14, 116, 144, 0.18)',
    shadowColor: isDark ? colors.background : colors.teal,
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.08,
    shadowRadius: 12,
    elevation: 2,
    overflow: 'hidden',
    backgroundColor: colors.surface || colors.cardBg,
  },
  cardGradient: {
    padding: spacing.lg,
    alignItems: 'center',
  },
  topRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: spacing.md,
  },
  badge: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: isDark ? colors.accentSoft : 'rgba(14, 116, 144, 0.08)',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xxs + 1,
    borderRadius: spacing.radii.pill,
  },
  activeDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: colors.accent || colors.teal,
    marginEnd: spacing.xs,
  },
  eyebrowText: {
    ...typography.eyebrow,
    color: colors.accentStrong || colors.tealDark,
    fontSize: 11,
    letterSpacing: 0.8,
  },
  orbStructure: {
    alignItems: 'center',
    justifyContent: 'center',
    marginVertical: spacing.xs,
  },
  outerRing: {
    width: 124,
    height: 124,
    borderRadius: 62,
    borderWidth: 2,
    borderColor: isDark ? colors.borderStrong : 'rgba(14, 116, 144, 0.22)',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: isDark ? colors.surfaceElevated : 'rgba(255, 255, 255, 0.6)',
  },
  innerCircle: {
    width: 104,
    height: 104,
    borderRadius: 52,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: isDark ? colors.borderStrong : 'rgba(255, 255, 255, 0.8)',
  },
  centerScoreWrap: {
    alignItems: 'center',
    justifyContent: 'center',
  },
  scoreNumber: {
    ...typography.display,
    fontSize: 28,
    lineHeight: 32,
    fontWeight: '800',
    color: colors.accentStrong || colors.tealDark,
  },
  scoreUnit: {
    ...typography.eyebrow,
    fontSize: 10,
    color: colors.textSecondary || colors.textMuted,
    marginTop: -2,
  },
  stateLabel: {
    ...typography.caption,
    fontWeight: '700',
    color: colors.accentStrong || colors.tealDark,
    marginTop: spacing.xxs,
  },
  subtitle: {
    ...typography.caption,
    color: colors.textSecondary || colors.textMuted,
    textAlign: 'center',
    marginTop: spacing.md,
    lineHeight: 18,
  },
});
