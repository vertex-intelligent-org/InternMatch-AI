import React from 'react';
import { View, StyleSheet, Platform } from 'react-native';
import { BlurView } from 'expo-blur';
import {
  GlassView,
  isLiquidGlassAvailable,
  isGlassEffectAPIAvailable,
} from 'expo-glass-effect';
import { useAppTheme } from '../context/ThemeProvider';
import { spacing } from '../theme/spacing';

/**
 * Reusable platform-adaptive Glass Surface.
 * - iOS Liquid Glass (when available): GlassView with subtle overlay
 * - iOS Standard Blur: BlurView (systemUltraThinMaterialLight) with translucent overlay
 * - Android / Web: Translucent solid surface with subtle border & shadow
 */
export default function GlassSurface({
  children,
  style,
  contentStyle,
  variant = 'panel', // 'panel' | 'control' | 'card' | 'subtle'
  glassEffectStyle = 'regular',
  intensity = 75,
  tintColor,
}) {
  const { colors, isDark } = useAppTheme();
  const isLiquidSupported =
    Platform.OS === 'ios' &&
    ((typeof isLiquidGlassAvailable === 'function' && isLiquidGlassAvailable()) &&
      (typeof isGlassEffectAPIAvailable === 'function' && isGlassEffectAPIAvailable()));

  const variantContainerStyle = {
    panel: styles.panelContainer,
    control: styles.controlContainer,
    card: styles.cardContainer,
    subtle: styles.subtleContainer,
  }[variant] ?? styles.panelContainer;

  const defaultTintColor = isDark
    ? {
        panel: 'rgba(13, 35, 42, 0.72)',
        control: 'rgba(17, 43, 51, 0.72)',
        card: 'rgba(13, 35, 42, 0.80)',
        subtle: 'rgba(16, 38, 45, 0.70)',
      }[variant]
    : {
        panel: 'rgba(255, 255, 255, 0.72)',
        control: 'rgba(255, 255, 255, 0.65)',
        card: 'rgba(255, 255, 255, 0.80)',
        subtle: 'rgba(255, 255, 255, 0.50)',
      }[variant];

  const effectiveTintColor = tintColor || defaultTintColor;
  const effectiveBorderColor = colors.glass.borderLight;
  const effectiveShadowColor = colors.glass.shadow;
  const liquidOverlayColor = isDark
    ? 'rgba(7, 23, 29, 0.18)'
    : variant === 'panel'
      ? 'rgba(255, 255, 255, 0.52)'
      : 'rgba(255, 255, 255, 0.40)';
  const blurOverlayColor = isDark
    ? 'rgba(7, 23, 29, 0.24)'
    : variant === 'panel'
      ? 'rgba(255, 255, 255, 0.52)'
      : 'rgba(255, 255, 255, 0.60)';

  return (
    <View
      style={[
        styles.baseContainer,
        variantContainerStyle,
        {
          borderColor: effectiveBorderColor,
          shadowColor: effectiveShadowColor,
        },
        style,
      ]}
    >
      {/* Background layer */}
      {isLiquidSupported ? (
        <>
          <GlassView
            style={StyleSheet.absoluteFillObject}
            glassEffectStyle={glassEffectStyle}
            colorScheme={isDark ? "dark" : "light"}
            tintColor={effectiveTintColor}
          />
          <View
            style={[
              StyleSheet.absoluteFillObject,
              styles.liquidOverlay,
              variant === 'panel' && styles.panelOverlay,
              { backgroundColor: liquidOverlayColor },
            ]}
          />
        </>
      ) : Platform.OS === 'ios' ? (
        <>
          <BlurView
            style={StyleSheet.absoluteFillObject}
            tint={isDark ? "systemUltraThinMaterialDark" : "systemUltraThinMaterialLight"}
            intensity={intensity}
          />
          <View
            style={[
              StyleSheet.absoluteFillObject,
              styles.blurOverlay,
              variant === 'panel' && styles.panelOverlay,
              { backgroundColor: blurOverlayColor },
            ]}
          />
        </>
      ) : (
        <View
          style={[
            StyleSheet.absoluteFillObject,
            styles.fallbackSurface,
            variant === 'subtle' && styles.fallbackSubtle,
            { backgroundColor: effectiveTintColor },
          ]}
        />
      )}

      {/* Surface content */}
      <View style={[styles.innerContent, contentStyle]}>{children}</View>
    </View>
  );
}

const styles = StyleSheet.create({
  baseContainer: {
    position: 'relative',
    overflow: 'hidden',
  },
  innerContent: {
    position: 'relative',
    zIndex: 1,
  },
  // Variant container geometries
  panelContainer: {
    borderRadius: 24,
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.85)',
    shadowColor: 'rgba(7, 43, 56, 0.10)',
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 1,
    shadowRadius: 20,
    elevation: 4,
  },
  controlContainer: {
    borderRadius: spacing.radii.pill,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: 'rgba(255, 255, 255, 0.70)',
  },
  cardContainer: {
    borderRadius: spacing.radii.lg,
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.80)',
    shadowColor: 'rgba(7, 43, 56, 0.06)',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 1,
    shadowRadius: 12,
    elevation: 2,
  },
  subtleContainer: {
    borderRadius: spacing.radii.md,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: 'rgba(255, 255, 255, 0.50)',
  },
  // Overlays
  liquidOverlay: {
    backgroundColor: 'rgba(255, 255, 255, 0.40)',
  },
  blurOverlay: {
    backgroundColor: 'rgba(255, 255, 255, 0.60)',
  },
  panelOverlay: {
    backgroundColor: 'rgba(255, 255, 255, 0.52)',
  },
  // Android & Web fallback surfaces
  fallbackSurface: {
    backgroundColor: 'rgba(255, 255, 255, 0.92)',
  },
  fallbackSubtle: {
    backgroundColor: 'rgba(255, 255, 255, 0.75)',
  },
});
