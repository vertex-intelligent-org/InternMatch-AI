import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useLocalization } from '../localization/LocalizationContext';
import { View, StyleSheet, Platform, useWindowDimensions, Image } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { BlurView } from 'expo-blur';
import {
  GlassView,
  isLiquidGlassAvailable,
  isGlassEffectAPIAvailable,
} from 'expo-glass-effect';
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withSpring,
} from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import colors from '../theme/colors';
import { useAppTheme } from '../context/ThemeProvider';
import { spacing } from '../theme/spacing';
import motionTokens from '../motion/motionTokens';
import useReducedMotion from '../hooks/useReducedMotion';
import haptics from '../services/haptics';
import PressableScale from '../components/PressableScale';
import {
  useTabScrollResetTrigger,
  useTabScrolledState,
} from '../context/TabScrollContext';
import { useProfile } from '../context/ProfileContext';

import {
  FLOATING_TAB_BAR_HEIGHT,
  FLOATING_TAB_BAR_MIN_BOTTOM_INSET,
  FLOATING_TAB_BAR_HORIZONTAL_MARGIN,
  FLOATING_TAB_BAR_RADIUS,
  FLOATING_TAB_BAR_LENS_HEIGHT,
  FLOATING_TAB_BAR_LENS_TOP,
} from '../theme/tabBarLayout';

const ICONS = {
  Home: 'home',
  Internships: 'business',
  Opportunities: 'briefcase',
  Matchups: 'radio-button-on',
  Applications: 'document-text',
  Profile: 'person-circle',
};

const TAB_TRANSLATION_KEYS = Object.freeze({
  Home: 'navigation.tabs.home',
  Internships: 'navigation.tabs.internships',
  Opportunities: 'navigation.tabs.opportunities',
  Matchups: 'navigation.tabs.matchups',
  Applications: 'navigation.tabs.applications',
  Profile: 'navigation.tabs.profile',
});


export default function CustomTabBar({ state, descriptors, navigation }) {
  const insets = useSafeAreaInsets();
  const resetTabScroll = useTabScrollResetTrigger();
  const { isScrolled } = useTabScrolledState();
  const isReducedMotion = useReducedMotion();
  const { width: windowWidth } = useWindowDimensions();
  const { profile } = useProfile();
  const { t } = useTranslation();
  const { isRTL } = useLocalization();
  const { isDark } = useAppTheme();

  const [avatarLoadError, setAvatarLoadError] = useState(false);

  useEffect(() => {
    setAvatarLoadError(false);
  }, [profile?.avatar_url]);

  const isLiquidSupported =
    Platform.OS === 'ios' &&
    ((typeof isLiquidGlassAvailable === 'function' && isLiquidGlassAvailable()) &&
      (typeof isGlassEffectAPIAvailable === 'function' && isGlassEffectAPIAvailable()));

  const bottomOffset = Math.max(insets.bottom, FLOATING_TAB_BAR_MIN_BOTTOM_INSET);
  const routeCount = state.routes.length || 5;
  const activeVisualIndex = isRTL ? routeCount - 1 - state.index : state.index;
  const visualRoutes = isRTL ? [...state.routes].reverse() : state.routes;

  // Exact geometry derived directly from windowWidth
  const totalBarWidth = windowWidth - (FLOATING_TAB_BAR_HORIZONTAL_MARGIN * 2);
  const tabWidth = totalBarWidth / routeCount;
  const lensWidth = Math.max(48, tabWidth - 8);
  const lensInset = (tabWidth - lensWidth) / 2; // Symmetric 4px inset

  // Exact initial target position for the current visual order
  const initialTargetX = tabWidth * activeVisualIndex + lensInset;
  const translateX = useSharedValue(initialTargetX);

  useEffect(() => {
    const targetX = tabWidth * activeVisualIndex + lensInset;

    if (isReducedMotion) {
      translateX.value = targetX;
      return;
    }

    translateX.value = withSpring(targetX, {
      damping: 26,
      stiffness: 300,
      mass: 0.7,
    });
  }, [activeVisualIndex, tabWidth, lensInset, isReducedMotion, translateX]);

  const animatedLensStyle = useAnimatedStyle(() => {
    return {
      transform: [{ translateX: translateX.value }],
    };
  });

  return (
    <View style={[styles.floatingBar, { bottom: bottomOffset }]}>
      {/* Dynamic Base Layer: Darker Teal Glass near Top -> Lighter Glass when Scrolled */}
      {isLiquidSupported ? (
        <>
          <GlassView
            style={StyleSheet.absoluteFillObject}
            glassEffectStyle="regular"
            colorScheme={isDark ? "dark" : "light"}
            tintColor={
              isScrolled
                ? 'rgba(14, 116, 144, 0.40)'
                : 'rgba(7, 43, 56, 0.75)'
            }
          />
          <View
            style={[
              StyleSheet.absoluteFillObject,
              {
                backgroundColor: isScrolled
                  ? 'rgba(15, 76, 92, 0.25)'
                  : 'rgba(7, 43, 56, 0.50)',
              },
            ]}
          />
        </>
      ) : Platform.OS === 'ios' ? (
        <>
          <BlurView
            style={StyleSheet.absoluteFillObject}
            tint="systemUltraThinMaterialLight"
            intensity={85}
          />
          <View
            style={[
              StyleSheet.absoluteFillObject,
              {
                backgroundColor: isScrolled
                  ? 'rgba(15, 76, 92, 0.32)'
                  : 'rgba(7, 43, 56, 0.60)',
              },
            ]}
          />
        </>
      ) : (
        <View
          style={[
            StyleSheet.absoluteFillObject,
            {
              backgroundColor: isScrolled
                ? 'rgba(15, 76, 92, 0.88)'
                : 'rgba(7, 43, 56, 0.94)',
            },
          ]}
        />
      )}

      {/* Tabs Container */}
      <View style={styles.tabsRow}>
        {/* ONE Moving Clear Liquid Glass Lens */}
        <Animated.View
          style={[
            styles.lensContainer,
            { width: lensWidth, height: FLOATING_TAB_BAR_LENS_HEIGHT, top: FLOATING_TAB_BAR_LENS_TOP },
            animatedLensStyle,
          ]}
          pointerEvents="none"
        >
          {isLiquidSupported ? (
            <>
              <GlassView
                style={StyleSheet.absoluteFillObject}
                glassEffectStyle="regular"
                colorScheme={isDark ? "dark" : "light"}
                tintColor="rgba(255, 255, 255, 0.75)"
              />
              <View style={[StyleSheet.absoluteFillObject, styles.liquidLensOverlay]} />
            </>
          ) : (
            <View style={[StyleSheet.absoluteFillObject, styles.fallbackLens]} />
          )}
        </Animated.View>

        {/* Interactive Tab Items */}
        {visualRoutes.map((route) => {
          const routeIndex = state.routes.findIndex((candidate) => candidate.key === route.key);
          const focused = state.index === routeIndex;
          const iconName = ICONS[route.name] ?? 'ellipse';
          const isProfileRoute = route.name === 'Profile';
          const hasAvatar = isProfileRoute && Boolean(profile?.avatar_url) && !avatarLoadError;
          const tabTranslationKey = TAB_TRANSLATION_KEYS[route.name];

          const onPress = () => {
            const event = navigation.emit({
              type: 'tabPress',
              target: route.key,
              canPreventDefault: true,
            });

            if (!event.defaultPrevented) {
              if (!focused) {
                haptics.selection();
                navigation.navigate(route.name);
              }
              // Explicit bottom tab press resets that tab's root scroll to top
              resetTabScroll(route.name);
            }
          };

          return (
            <PressableScale
              key={route.key}
              style={[styles.tabItem, { width: tabWidth }]}
              onPress={onPress}
              scaleTo={motionTokens.scales.iconPressed}
              activeOpacity={0.8}
              haptic="none"
              accessibilityRole="tab"
              accessibilityState={{ selected: focused }}
              accessibilityLabel={tabTranslationKey ? t(tabTranslationKey) : route.name}
              hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
            >
              <View style={styles.tabContent}>
                {hasAvatar ? (
                  <View
                    style={[
                      styles.avatarRing,
                      focused ? styles.avatarRingActive : styles.avatarRingInactive,
                    ]}
                  >
                    <Image
                      source={{ uri: profile.avatar_url }}
                      style={styles.tabAvatar}
                      onError={() => setAvatarLoadError(true)}
                    />
                  </View>
                ) : (
                  <Ionicons
                    name={iconName}
                    size={22}
                    color={focused ? '#FFFFFF' : 'rgba(255, 255, 255, 0.65)'}
                  />
                )}
                {focused && <View style={styles.dot} />}
              </View>
            </PressableScale>
          );
        })}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  floatingBar: {
    position: 'absolute',
    left: FLOATING_TAB_BAR_HORIZONTAL_MARGIN,
    right: FLOATING_TAB_BAR_HORIZONTAL_MARGIN,
    height: FLOATING_TAB_BAR_HEIGHT,
    borderRadius: FLOATING_TAB_BAR_RADIUS,
    overflow: 'hidden',
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: 'rgba(255, 255, 255, 0.35)',
    shadowColor: 'rgba(7, 43, 56, 0.35)',
    shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 1,
    shadowRadius: 16,
    elevation: 10,
  },
  tabsRow: {
    flex: 1,
    position: 'relative',
    flexDirection: 'row',
    alignItems: 'center',
    height: FLOATING_TAB_BAR_HEIGHT,
  },
  lensContainer: {
    position: 'absolute',
    borderRadius: 24,
    overflow: 'hidden',
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.90)',
    shadowColor: 'rgba(255, 255, 255, 0.35)',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 1,
    shadowRadius: 4,
    elevation: 4,
  },
  liquidLensOverlay: {
    backgroundColor: 'rgba(255, 255, 255, 0.22)',
  },
  fallbackLens: {
    backgroundColor: 'rgba(255, 255, 255, 0.22)',
  },
  tabItem: {
    height: FLOATING_TAB_BAR_HEIGHT,
    minWidth: spacing.minimumTouchTarget,
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 1,
  },
  tabContent: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xxs + 1,
  },
  avatarRing: {
    width: 24,
    height: 24,
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
    overflow: 'hidden',
  },
  avatarRingActive: {
    borderWidth: 1.5,
    borderColor: '#FFFFFF',
  },
  avatarRingInactive: {
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.45)',
  },
  tabAvatar: {
    width: 22,
    height: 22,
    borderRadius: 11,
  },
  dot: {
    width: 4,
    height: 4,
    borderRadius: 2,
    backgroundColor: '#FFFFFF',
    marginTop: spacing.xxs,
  },
});
