import React, { useEffect, useState, useRef, useCallback } from 'react';
import { View, Text, StyleSheet, TouchableOpacity } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { Ionicons } from '@expo/vector-icons';
import { useTranslation } from 'react-i18next';
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withTiming,
  withSequence,
  withRepeat,
  cancelAnimation,
  Easing,
} from 'react-native-reanimated';
import { gradientColors, colors } from '../theme/colors';
import {
  clearLocalSessionAfterAccountDeletion,
  getCurrentSession,
  signOut,
} from '../services/auth';
import { ApiError, completeSignup, deleteAccount } from '../services/api';
import { useProfile } from '../context/ProfileContext';
import useReducedMotion from '../hooks/useReducedMotion';
import SplashBowArrowAnimation from '../components/motion/SplashBowArrowAnimation';

export default function SplashScreen({ navigation }) {
  const { t } = useTranslation();
  const { refreshProfile, clearProfile } = useProfile();
  const isReducedMotion = useReducedMotion();

  const [checking, setChecking] = useState(true);
  const [retryNonce, setRetryNonce] = useState(0);
  const [connectionError, setConnectionError] = useState(false);

  // Layout-measured coordinates of the target mark relative to brandHero container
  const [targetCoords, setTargetCoords] = useState(null);
  const brandHeroRef = useRef(null);
  const targetRef = useRef(null);

  // Concurrency & navigation gate refs
  const pendingDestinationRef = useRef(null);
  const animationFinishedRef = useRef(false);
  const hasNavigatedRef = useRef(false);

  // Target micro-pulse scale and continuous loading wheel rotation
  const targetScale = useSharedValue(1);
  const targetRotation = useSharedValue(0);
  const isRotatingRef = useRef(false);

  const measureTargetPosition = useCallback(() => {
    if (targetRef.current && brandHeroRef.current) {
      targetRef.current.measureLayout(
        brandHeroRef.current,
        (x, y, width, height) => {
          if (width > 0 && height > 0) {
            setTargetCoords({
              x: Math.round((x + width / 2) * 10) / 10,
              y: Math.round((y + height / 2) * 10) / 10,
            });
          }
        },
        () => {}
      );
    }
  }, []);

  const performNavigationIfReady = useCallback(() => {
    if (hasNavigatedRef.current) return;
    const dest = pendingDestinationRef.current;

    if (dest && animationFinishedRef.current) {
      hasNavigatedRef.current = true;

      if (typeof dest === 'string') {
        navigation.replace(dest);
      } else {
        navigation.replace(dest.name, dest.params);
      }
    }
  }, [navigation]);

  const startTargetRotation = useCallback(() => {
    if (isReducedMotion) return;
    isRotatingRef.current = true;
    targetRotation.value = withRepeat(
      withTiming(targetRotation.value + 360, {
        duration: 1800,
        easing: Easing.linear,
      }),
      -1,
      false
    );
  }, [isReducedMotion, targetRotation]);

  const stopTargetRotation = useCallback(() => {
    isRotatingRef.current = false;
    cancelAnimation(targetRotation);
    targetRotation.value = withTiming(0, {
      duration: 300,
      easing: Easing.out(Easing.quad),
    });
  }, [targetRotation]);

  const handleAnimationComplete = useCallback(() => {
    animationFinishedRef.current = true;
    performNavigationIfReady();
  }, [performNavigationIfReady]);

  const handleTargetImpact = useCallback(() => {
    if (isReducedMotion) return;
    // 1. Target micro-pulse as arrow pierces center
    targetScale.value = withSequence(
      withTiming(1.10, { duration: 110, easing: Easing.out(Easing.quad) }),
      withTiming(1.0, { duration: 160, easing: Easing.inOut(Easing.quad) })
    );

    // 2. Begin continuous loading wheel rotation
    startTargetRotation();
  }, [isReducedMotion, targetScale, startTargetRotation]);

  const handleRetry = useCallback(() => {
    setConnectionError(false);
    setRetryNonce((value) => value + 1);
    if (animationFinishedRef.current) {
      startTargetRotation();
    }
  }, [startTargetRotation]);

  const animatedTargetStyle = useAnimatedStyle(() => {
    return {
      transform: [
        { scale: targetScale.value },
        { rotate: `${targetRotation.value}deg` },
      ],
    };
  });

  // Concurrent startup session and profile resolution (runs immediately on mount)
  useEffect(() => {
    let isMounted = true;

    async function checkSessionAndRoute() {
      setChecking(true);
      setConnectionError(false);
      try {
        const { data, error } = await getCurrentSession();

        if (error || !data?.session?.access_token) {
          if (isMounted) {
            pendingDestinationRef.current = 'SignIn';
            performNavigationIfReady();
          }
          return;
        }

        // Load the authoritative backend profile once.
        const existingProfile = await refreshProfile();

        if (existingProfile) {
          if (isMounted) {
            pendingDestinationRef.current = 'MainTabs';
            performNavigationIfReady();
          }
          return;
        }

        // EMAIL_CONFIRMATION_AUTO_BOOTSTRAP
        // A confirmed email sign-up can restore a valid Supabase session
        // before its canonical InternMatch profile exists. Explicit email
        // provider + sign-up metadata is sufficient evidence to finish the
        // already-started registration, but not to create a social-login
        // account implicitly from the Sign In flow.
        const sessionUser = data.session?.user;
        const appMetadata = sessionUser?.app_metadata || {};
        const signupMetadata = sessionUser?.user_metadata || {};

        const providerList = Array.isArray(appMetadata.providers)
          ? appMetadata.providers
          : [];

        const isEmailIdentity =
          appMetadata.provider === 'email'
          || providerList.includes('email');

        const signupName =
          typeof signupMetadata.full_name === 'string'
            ? signupMetadata.full_name.trim()
            : '';

        const signupDepartment =
          typeof signupMetadata.department === 'string'
            ? signupMetadata.department.trim()
            : '';

        const signupAccountType =
          signupMetadata.account_type === 'intern'
          || signupMetadata.account_type === 'employer'
            ? signupMetadata.account_type
            : null;

        if (isEmailIdentity && signupName && signupAccountType) {
          try {
            await completeSignup({
              full_name: signupName,
              department: signupDepartment || null,
              account_type: signupAccountType,
            });
          } catch (error) {
            // A concurrent callback/session restoration may have completed
            // the profile already. Only tolerate the idempotent conflict.
            if (!(error instanceof ApiError && error.status === 409)) {
              throw error;
            }
          }

          const completedProfile = await refreshProfile();

          if (!completedProfile) {
            throw new Error(
              'Canonical profile missing after confirmed email sign-up.'
            );
          }

          if (isMounted) {
            pendingDestinationRef.current = 'MainTabs';
            performNavigationIfReady();
          }

          return;
        }

        // Preserve the existing fail-closed behavior for a real orphan Auth
        // identity such as a social identity created through Sign In without
        // an existing canonical InternMatch account.
        await deleteAccount();
        await clearLocalSessionAfterAccountDeletion();
        clearProfile();

        if (isMounted) {
          pendingDestinationRef.current = 'SignIn';
          performNavigationIfReady();
        }
      } catch (err) {
        console.warn('Session restoration failed on splash:', err);
        if (err instanceof ApiError && (err.status === 401 || err.status === 403)) {
          try {
            await signOut();
          } catch (_) {}
          clearProfile();
          if (isMounted) {
            pendingDestinationRef.current = 'SignIn';
            performNavigationIfReady();
          }
        } else {
          // A valid Supabase session may still exist while the API/network is unavailable.
          // Preserve authentication, stop wheel rotation, and allow the user to retry.
          if (isMounted) {
            setConnectionError(true);
            stopTargetRotation();
          }
        }
      } finally {
        if (isMounted) setChecking(false);
      }
    }

    checkSessionAndRoute();

    return () => {
      isMounted = false;
    };
  }, [navigation, refreshProfile, clearProfile, retryNonce, performNavigationIfReady, stopTargetRotation]);

  return (
    <LinearGradient colors={gradientColors} style={styles.container}>
      <View style={styles.center}>
        <View
          ref={brandHeroRef}
          style={styles.brandHero}
          onLayout={measureTargetPosition}
        >
          <View style={styles.logoRow}>
            <Text style={styles.logo}>InternMatch</Text>
            <View
              ref={targetRef}
              style={styles.targetWrap}
              onLayout={measureTargetPosition}
            >
              <Animated.View style={animatedTargetStyle}>
                <Ionicons name="locate" size={26} color={colors.white} />
              </Animated.View>
            </View>
          </View>
          <Text style={styles.tagline}>Right internship, bright future</Text>

          {/* Branded Bow-and-Arrow Motion Sequence */}
          <SplashBowArrowAnimation
            targetCoords={targetCoords}
            isReducedMotion={isReducedMotion}
            onAnimationComplete={handleAnimationComplete}
            onTargetImpact={handleTargetImpact}
          />
        </View>

        {connectionError && (
          <View style={styles.retryBox}>
            <Text style={styles.retryText}>{t('splash.reachServices')}</Text>
            <Text style={styles.retrySubtext}>{t('splash.sessionPreserved')}</Text>
            <TouchableOpacity
              style={styles.retryButton}
              onPress={handleRetry}
              accessibilityRole="button"
              accessibilityLabel={t('common.tryAgain')}
            >
              <Text style={styles.retryButtonText}>{t('common.tryAgain')}</Text>
            </TouchableOpacity>
          </View>
        )}
      </View>
    </LinearGradient>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  brandHero: {
    alignItems: 'center',
    justifyContent: 'center',
    position: 'relative',
    paddingBottom: 72,
  },
  logoRow: {
    flexDirection: 'row',
    direction: 'ltr',
    alignItems: 'center',
  },
  logo: {
    fontSize: 28,
    fontStyle: 'italic',
    fontWeight: '700',
    color: colors.white,
  },
  targetWrap: {
    marginLeft: 6,
    width: 26,
    height: 26,
    alignItems: 'center',
    justifyContent: 'center',
  },
  tagline: {
    marginTop: 12,
    color: colors.white,
    fontSize: 13,
    fontWeight: '600',
  },
  retryBox: { alignItems: 'center', marginTop: 24, paddingHorizontal: 32 },
  retryText: { color: colors.white, fontSize: 14, fontWeight: '700', textAlign: 'center' },
  retrySubtext: { color: colors.white, opacity: 0.8, fontSize: 12, marginTop: 6, textAlign: 'center' },
  retryButton: { marginTop: 16, paddingHorizontal: 20, paddingVertical: 10, borderRadius: 18, backgroundColor: 'rgba(255,255,255,0.2)' },
  retryButtonText: { color: colors.white, fontWeight: '700' },
});
