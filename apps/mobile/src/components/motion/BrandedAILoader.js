import React, { useEffect } from 'react';
import { View, StyleSheet } from 'react-native';
import { useTranslation } from 'react-i18next';
import Svg, { Circle, Line } from 'react-native-svg';
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withRepeat,
  withTiming,
  cancelAnimation,
  Easing,
} from 'react-native-reanimated';
import { useAppTheme } from '../../context/ThemeProvider';
import motionTokens from '../../motion/motionTokens';
import useReducedMotion from '../../hooks/useReducedMotion';

export default function BrandedAILoader({
  size = 28,
  color,
  active = true,
  duration = motionTokens.durations.loaderRotation,
  style,
}) {
  const { colors } = useAppTheme();
  const effectiveColor = color ?? colors.accent;
  const { t } = useTranslation();
  const isReducedMotion = useReducedMotion();
  const rotation = useSharedValue(0);

  useEffect(() => {
    if (!active || isReducedMotion) {
      cancelAnimation(rotation);
      rotation.value = 0;
      return;
    }

    rotation.value = 0;
    rotation.value = withRepeat(
      withTiming(360, {
        duration,
        easing: Easing.linear,
      }),
      -1,
      false
    );

    return () => {
      cancelAnimation(rotation);
    };
  }, [active, duration, isReducedMotion, rotation]);

  const animatedStyle = useAnimatedStyle(() => {
    if (!active || isReducedMotion) {
      return {
        transform: [{ rotate: '0deg' }],
      };
    }
    return {
      transform: [{ rotate: `${rotation.value}deg` }],
    };
  });

  return (
    <View
      style={[styles.container, { width: size, height: size }, style]}
      accessibilityRole="progressbar"
      accessibilityLabel={t('components.aiLoaderA11y', { defaultValue: 'AI processing indicator' })}
    >
      <Animated.View style={animatedStyle}>
        <Svg width={size} height={size} viewBox="0 0 32 32">
          {/* Central Target Circle */}
          <Circle
            cx="16"
            cy="16"
            r="8.5"
            stroke={effectiveColor}
            strokeWidth="2.2"
            fill="none"
          />
          {/* Top Prong */}
          <Line
            x1="16"
            y1="2"
            x2="16"
            y2="5.5"
            stroke={effectiveColor}
            strokeWidth="2.2"
            strokeLinecap="round"
          />
          {/* Bottom Prong */}
          <Line
            x1="16"
            y1="26.5"
            x2="16"
            y2="30"
            stroke={effectiveColor}
            strokeWidth="2.2"
            strokeLinecap="round"
          />
          {/* Left Prong */}
          <Line
            x1="2"
            y1="16"
            x2="5.5"
            y2="16"
            stroke={effectiveColor}
            strokeWidth="2.2"
            strokeLinecap="round"
          />
          {/* Right Prong */}
          <Line
            x1="26.5"
            y1="16"
            x2="30"
            y2="16"
            stroke={effectiveColor}
            strokeWidth="2.2"
            strokeLinecap="round"
          />
        </Svg>
      </Animated.View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    alignItems: 'center',
    justifyContent: 'center',
  },
});
