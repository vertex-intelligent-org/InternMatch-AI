import React, { useEffect } from 'react';
import { View, Text, StyleSheet, Pressable } from 'react-native';
import { useTranslation } from 'react-i18next';
import Svg, { Circle, Line } from 'react-native-svg';
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withTiming,
  Easing,
} from 'react-native-reanimated';
import { useAppTheme } from '../context/ThemeProvider';
import { spacing } from '../theme/spacing';
import { typography } from '../theme/typography';
import useReducedMotion from '../hooks/useReducedMotion';

export default function InternMatchLogo({ style }) {
  const { t } = useTranslation();
  const { colors } = useAppTheme();
  const styles = createStyles(colors);
  const isReducedMotion = useReducedMotion();
  const rotation = useSharedValue(0);

  useEffect(() => {
    if (isReducedMotion) {
      rotation.value = 0;
      return;
    }

    // Run practical ONE 360-degree rotation on initial mount
    rotation.value = withTiming(360, {
      duration: 800,
      easing: Easing.out(Easing.cubic),
    });
  }, [isReducedMotion, rotation]);

  const handlePress = () => {
    if (isReducedMotion) return;

    // Run ONE additional 360-degree rotation from current angle
    rotation.value = withTiming(rotation.value + 360, {
      duration: 750,
      easing: Easing.out(Easing.cubic),
    });
  };

  const animatedIconStyle = useAnimatedStyle(() => {
    if (isReducedMotion) {
      return { transform: [{ rotate: '0deg' }] };
    }
    return {
      transform: [{ rotate: `${rotation.value}deg` }],
    };
  });

  const iconColor = colors.accentStrong || colors.tealDark;

  return (
    <Pressable
      onPress={handlePress}
      style={[styles.container, style]}
      accessibilityRole="button"
      accessibilityLabel={t('components.logoA11y', { defaultValue: 'InternMatch brand logo' })}
      hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
    >
      <Text style={styles.brandText}>InternMatch</Text>
      <Animated.View style={[styles.iconWrap, animatedIconStyle]}>
        <Svg width={22} height={22} viewBox="0 0 32 32">
          {/* Target Circle */}
          <Circle
            cx="16"
            cy="16"
            r="8.5"
            stroke={iconColor}
            strokeWidth="2.4"
            fill="none"
          />
          {/* Top Prong */}
          <Line
            x1="16"
            y1="2"
            x2="16"
            y2="5.5"
            stroke={iconColor}
            strokeWidth="2.4"
            strokeLinecap="round"
          />
          {/* Bottom Prong */}
          <Line
            x1="16"
            y1="26.5"
            x2="16"
            y2="30"
            stroke={iconColor}
            strokeWidth="2.4"
            strokeLinecap="round"
          />
          {/* Left Prong */}
          <Line
            x1="2"
            y1="16"
            x2="5.5"
            y2="16"
            stroke={iconColor}
            strokeWidth="2.4"
            strokeLinecap="round"
          />
          {/* Right Prong */}
          <Line
            x1="26.5"
            y1="16"
            x2="30"
            y2="16"
            stroke={iconColor}
            strokeWidth="2.4"
            strokeLinecap="round"
          />
        </Svg>
      </Animated.View>
    </Pressable>
  );
}

const createStyles = (colors) => StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
  },
  brandText: {
    ...typography.display,
    fontSize: 22,
    lineHeight: 26,
    fontWeight: '800',
    color: colors.accentStrong || colors.tealDark,
    letterSpacing: 0.5,
  },
  iconWrap: {
    width: 22,
    height: 22,
    marginStart: spacing.xs,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
