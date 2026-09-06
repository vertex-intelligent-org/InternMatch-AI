import React, { useEffect, useRef } from 'react';
import { Animated, Text, StyleSheet, View } from 'react-native';
import colors from '../theme/colors';
import { spacing } from '../theme/spacing';
import { typography } from '../theme/typography';
import motionTokens from '../motion/motionTokens';
import PressableScale from './PressableScale';

const SPINNER_DOTS = [
  1,
  0.88,
  0.76,
  0.64,
  0.52,
  0.40,
  0.28,
  0.18,
];

function DottedSpinner({ color }) {
  const rotation = useRef(
    new Animated.Value(0)
  ).current;

  useEffect(() => {
    const animation = Animated.loop(
      Animated.timing(rotation, {
        toValue: 1,
        duration: 850,
        useNativeDriver: true,
      })
    );

    animation.start();

    return () => {
      animation.stop();
    };
  }, [rotation]);

  const rotate = rotation.interpolate({
    inputRange: [0, 1],
    outputRange: ['0deg', '360deg'],
  });

  return (
    <Animated.View
      pointerEvents="none"
      style={[
        styles.spinner,
        {
          transform: [{ rotate }],
        },
      ]}
    >
      {SPINNER_DOTS.map((opacity, index) => (
        <View
          key={index}
          style={[
            styles.spinnerDotPosition,
            {
              transform: [
                {
                  rotate: `${index * 45}deg`,
                },
              ],
            },
          ]}
        >
          <View
            style={[
              styles.spinnerDot,
              {
                backgroundColor: color,
                opacity,
              },
            ]}
          />
        </View>
      ))}
    </Animated.View>
  );
}

/**
 * Solid-color primary CTA button with tactile physics and light haptic feedback.
 */
export default function GradientButton({
  title,
  onPress,
  color = colors.primaryBlue,
  textColor = colors.white,
  style,
  outline = false,
  disabled = false,
  loading = false,
  accessibilityLabel,
}) {
  if (outline) {
    return (
      <PressableScale
        style={[
          styles.button,
          styles.outline,
          { borderColor: color },
          disabled && styles.disabled,
          style,
        ]}
        onPress={onPress}
        disabled={disabled}
        scaleTo={motionTokens.scales.buttonPressed}
        activeOpacity={motionTokens.opacities.pressed}
        haptic={disabled ? 'none' : 'light'}
        accessibilityRole="button"
        accessibilityLabel={accessibilityLabel || (typeof title === 'string' ? title : undefined)}
      >
        <View style={styles.content}>
          {loading ? (
            <DottedSpinner color={color} />
          ) : null}
          <Text style={[styles.text, { color }]}>{title}</Text>
        </View>
      </PressableScale>
    );
  }

  return (
    <PressableScale
      style={[
        styles.button,
        { backgroundColor: color },
        disabled && styles.disabled,
        style,
      ]}
      onPress={onPress}
      disabled={disabled}
      scaleTo={motionTokens.scales.buttonPressed}
      activeOpacity={motionTokens.opacities.pressed}
      haptic={disabled ? 'none' : 'light'}
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel || (typeof title === 'string' ? title : undefined)}
    >
      <View style={styles.content}>
        {loading ? (
          <DottedSpinner color={textColor} />
        ) : null}
        <Text style={[styles.text, { color: textColor }]}>{title}</Text>
      </View>
    </PressableScale>
  );
}

const styles = StyleSheet.create({
  button: {
    height: 48,
    borderRadius: spacing.radii.pill,
    alignItems: 'center',
    justifyContent: 'center',
    width: '100%',
    minHeight: spacing.minimumTouchTarget,
  },
  outline: {
    backgroundColor: 'transparent',
    borderWidth: 1.5,
  },
  disabled: {
    opacity: 0.6,
  },
  content: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.xs,
  },
  spinner: {
    width: 18,
    height: 18,
    position: 'relative',
  },
  spinnerDotPosition: {
    position: 'absolute',
    width: 18,
    height: 18,
    alignItems: 'center',
  },
  spinnerDot: {
    width: 3,
    height: 3,
    borderRadius: 1.5,
  },
  text: {
    ...typography.button,
  },
});
