import React, { useEffect } from 'react';
import { StyleSheet, View } from 'react-native';
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withRepeat,
  withSequence,
  withTiming,
  cancelAnimation,
} from 'react-native-reanimated';
import { useAppTheme } from '../../context/ThemeProvider';
import { spacing } from '../../theme/spacing';
import motionTokens from '../../motion/motionTokens';
import useReducedMotion from '../../hooks/useReducedMotion';

export default function AIPulse({
  active = true,
  children,
  style,
  haloColor,
  borderColor,
}) {
  const { colors } = useAppTheme();
  const effectiveHaloColor = haloColor ?? colors.accentSoft;
  const effectiveBorderColor = borderColor ?? colors.accent;
  const isReducedMotion = useReducedMotion();
  const opacity = useSharedValue(1);
  const scale = useSharedValue(1);

  useEffect(() => {
    if (!active || isReducedMotion) {
      cancelAnimation(opacity);
      cancelAnimation(scale);
      opacity.value = 1;
      scale.value = 1;
      return;
    }

    const halfDuration = motionTokens.durations.pulse / 2;

    opacity.value = withRepeat(
      withSequence(
        withTiming(motionTokens.opacities.pulseLow, { duration: halfDuration }),
        withTiming(motionTokens.opacities.pulseHigh, { duration: halfDuration })
      ),
      -1,
      true
    );

    scale.value = withRepeat(
      withSequence(
        withTiming(1.008, { duration: halfDuration }),
        withTiming(0.995, { duration: halfDuration })
      ),
      -1,
      true
    );

    return () => {
      cancelAnimation(opacity);
      cancelAnimation(scale);
    };
  }, [active, isReducedMotion, opacity, scale]);

  const animatedHaloStyle = useAnimatedStyle(() => {
    if (!active || isReducedMotion) {
      return { opacity: 0, transform: [{ scale: 1 }] };
    }
    return {
      opacity: opacity.value,
      transform: [{ scale: scale.value }],
    };
  });

  return (
    <View style={[styles.wrapper, style]}>
      {active && !isReducedMotion && (
        <Animated.View
          accessible={false}
          style={[
            styles.halo,
            { backgroundColor: effectiveHaloColor, borderColor: effectiveBorderColor },
            animatedHaloStyle,
          ]}
        />
      )}
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  wrapper: {
    position: 'relative',
    width: '100%',
  },
  halo: {
    ...StyleSheet.absoluteFillObject,
    borderRadius: spacing.radii.lg,
    borderWidth: 1.5,
    margin: -3,
  },
});
