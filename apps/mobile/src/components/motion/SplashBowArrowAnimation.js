import React, { useEffect, useRef } from 'react';
import { Platform, StyleSheet, View } from 'react-native';
import Svg, { Path, Line, Polygon } from 'react-native-svg';
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  useAnimatedProps,
  withTiming,
  withDelay,
  withSequence,
  Easing,
} from 'react-native-reanimated';

const AnimatedLine = Animated.createAnimatedComponent(Line);

/**
 * SplashBowArrowAnimation
 *
 * Precision-engineered branded one-shot bow-and-arrow sequence:
 * 1. 0.0 - 0.35s: Bow and nocked arrow resolve in.
 * 2. 0.35 - 1.30s: Smooth, elegant draw back with synchronized subtle audio.
 * 3. 1.30 - 1.55s: Brief tension hold.
 * 4. 1.55 - 2.10s: Clean string release and rapid flight along the aim centerline.
 * 5. 2.10 - 2.35s: Arrow directly pierces and passes through the spoked-circle target center.
 * 6. 2.20 - 2.70s: Bow softly and calmly fades away as arrow passes through.
 * 7. 2.35 - 2.85s: Arrow continues smoothly beyond the target, exiting along trajectory.
 * 8. 2.85 - 3.00s: Clean brand frame holds before graceful startup transition.
 */
export default function SplashBowArrowAnimation({
  targetCoords,
  isReducedMotion = false,
  onAnimationComplete,
  onTargetImpact,
}) {
  const onAnimationCompleteRef = useRef(onAnimationComplete);
  onAnimationCompleteRef.current = onAnimationComplete;

  const onTargetImpactRef = useRef(onTargetImpact);
  onTargetImpactRef.current = onTargetImpact;
  // Shared animated values
  const introOpacity = useSharedValue(0);
  // drawProgress: 0 (at rest) -> 1 (full draw)
  const drawProgress = useSharedValue(0);
  // flightProgress: 0 (at release) -> 1 (overshoot/exit beyond target)
  const flightProgress = useSharedValue(0);
  // stringTension: 0 (rest) -> 1 (full draw) -> 0 (snap release)
  const stringTension = useSharedValue(0);
  // bowFade: 1 -> 0 (soft, calm fade-out after pass-through)
  const bowFade = useSharedValue(1);
  // arrowExitOpacity: 1 -> 0 (graceful fade as arrow exits beyond target)
  const arrowExitOpacity = useSharedValue(1);

  // Trigger one-shot motion choreography
  useEffect(() => {
    if (isReducedMotion) {
      introOpacity.value = 1;
      drawProgress.value = 1;
      flightProgress.value = 1;
      bowFade.value = 0;
      arrowExitOpacity.value = 0;
      const finishTimer = setTimeout(() => {
        onAnimationCompleteRef.current?.();
      }, 350);
      return () => clearTimeout(finishTimer);
    }

    // Phase 1: Intro reveal (0 - 350ms)
    introOpacity.value = withTiming(1, {
      duration: 350,
      easing: Easing.out(Easing.quad),
    });

    // Phase 2: Draw back (350 - 1300ms, 950ms duration)
    drawProgress.value = withDelay(
      350,
      withTiming(1, {
        duration: 950,
        easing: Easing.inOut(Easing.cubic),
      })
    );

    // String tension tracks draw and snaps back on release
    stringTension.value = withDelay(
      350,
      withSequence(
        // Draw tension increases to 1
        withTiming(1, {
          duration: 950,
          easing: Easing.inOut(Easing.cubic),
        }),
        // Tension hold (1300 - 1550ms, 250ms duration)
        withDelay(
          250,
          // Release: string snaps back in 50ms (1550 - 1600ms)
          withTiming(0, {
            duration: 50,
            easing: Easing.out(Easing.quad),
          })
        )
      )
    );

    // Phase 4 & 5: Release, Flight, Target Pierce, and Overshoot Exit (1550 - 2750ms, 1200ms duration)
    flightProgress.value = withDelay(
      1550,
      withTiming(1, {
        duration: 1200,
        easing: Easing.bezier(0.22, 1, 0.36, 1),
      })
    );

    // Bow fades out softly and calmly as the arrow pierces through and exits (2200 - 2700ms, 500ms duration)
    bowFade.value = withDelay(
      2200,
      withTiming(0, {
        duration: 500,
        easing: Easing.inOut(Easing.quad),
      })
    );

    // Arrow gracefully fades out as it completes its overshoot exit (2500 - 2850ms, 350ms duration)
    arrowExitOpacity.value = withDelay(
      2500,
      withTiming(0, {
        duration: 350,
        easing: Easing.inOut(Easing.quad),
      })
    );
    // Target pierce/impact micro-pulse trigger at 2100ms (when arrow tip reaches target center)
    const impactTimer = setTimeout(() => {
      onTargetImpactRef.current?.();
    }, 2100);

    // Total sequence completion at 3000ms
    const completeTimer = setTimeout(() => {
      onAnimationCompleteRef.current?.();
    }, 3000);

    return () => {
      clearTimeout(impactTimer);
      clearTimeout(completeTimer);
    };
  }, [isReducedMotion]);

  // Measured target center coordinates relative to brandHero container
  const targetX = targetCoords?.x ?? 190;
  const targetY = targetCoords?.y ?? 14;

  // Position bow in the open visual space below-left of the logo area
  const bowX = targetX - 85;
  const bowY = targetY + 120;

  const dx = targetX - bowX;
  const dy = targetY - bowY;
  const dist = Math.hypot(dx, dy) || 147;
  const angleRad = Math.atan2(dy, dx);
  const angleDeg = angleRad * (180 / Math.PI);

  // Unit directional vectors along the flight path
  const ux = dx / dist;
  const uy = dy / dist;

  // Total flight travel distance: from drawn position (u = 18) past target center (u = dist) to overshoot exit (dist + 85px)
  const overshootDistance = dist + 85;

  // Animated style for bow container (centered at bowX, bowY with zero-size anchor)
  const animatedBowStyle = useAnimatedStyle(() => {
    return {
      opacity: introOpacity.value * bowFade.value,
      transform: [
        { translateX: bowX },
        { translateY: bowY },
        { rotate: `${angleDeg}deg` },
      ],
    };
  });

  // Animated props for upper and lower string segments (meeting at dynamic nock point)
  const animatedUpperStringProps = useAnimatedProps(() => {
    const nockX = -7 - 25 * stringTension.value;
    return {
      x1: -8,
      y1: -42,
      x2: nockX,
      y2: 0,
    };
  });

  const animatedLowerStringProps = useAnimatedProps(() => {
    const nockX = -7 - 25 * stringTension.value;
    return {
      x1: -8,
      y1: 42,
      x2: nockX,
      y2: 0,
    };
  });

  // Animated style for arrow container (anchored at arrow TIP (0, 0))
  // Arrow total length = 52px.
  // During draw: tip moves from u = 43 (rest) to u = 18 (full draw), keeping tail locked to nock point.
  // During flight: tip moves from u = 18 through u = dist (target center) to u = overshootDistance (piercing through and exiting).
  const animatedArrowStyle = useAnimatedStyle(() => {
    'worklet';
    let u = 43;
    if (flightProgress.value > 0) {
      // Flight phase: moves from release position (18) through target center (dist) to overshoot exit (overshootDistance)
      u = 18 + flightProgress.value * (overshootDistance - 18);
    } else {
      // Draw phase: moves from rest (43) to full draw (18)
      u = 43 - drawProgress.value * (43 - 18);
    }

    const currentTipX = bowX + u * ux;
    const currentTipY = bowY + u * uy;

    return {
      opacity: introOpacity.value * arrowExitOpacity.value,
      transform: [
        { translateX: currentTipX },
        { translateY: currentTipY },
        { rotate: `${angleDeg}deg` },
      ],
    };
  });

  return (
    <View style={StyleSheet.absoluteFill} pointerEvents="none">
      {/* Bow and String Layer (Zero-dimension pivot anchor at (bowX, bowY)) */}
      <Animated.View
        collapsable={false}
        style={[
          styles.zeroPivot,
          Platform.OS === 'ios' && styles.iosNativePivot,
          animatedBowStyle,
        ]}
      >
        <Svg width={60} height={100} viewBox="-38 -50 60 100" style={styles.bowSvg}>
          {/* Upper string segment */}
          <AnimatedLine
            animatedProps={animatedUpperStringProps}
            stroke="rgba(255, 255, 255, 0.85)"
            strokeWidth="1.4"
            strokeLinecap="round"
          />
          {/* Lower string segment */}
          <AnimatedLine
            animatedProps={animatedLowerStringProps}
            stroke="rgba(255, 255, 255, 0.85)"
            strokeWidth="1.4"
            strokeLinecap="round"
          />
          {/* Bow limb curve */}
          <Path
            d="M -8 -42 Q 18 0 -8 42"
            stroke="#FFFFFF"
            strokeWidth="2.6"
            fill="none"
            strokeLinecap="round"
          />
        </Svg>
      </Animated.View>

      {/* Arrow Layer (Zero-dimension pivot anchor at arrow TIP) */}
      <Animated.View
        collapsable={false}
        style={[
          styles.zeroPivot,
          Platform.OS === 'ios' && styles.iosNativePivot,
          animatedArrowStyle,
        ]}
      >
        <Svg width={60} height={20} viewBox="-54 -10 60 20" style={styles.arrowSvg}>
          {/* Arrow shaft (from tail at -50 to tip at 0) */}
          <Line
            x1="-50"
            y1="0"
            x2="0"
            y2="0"
            stroke="#FFFFFF"
            strokeWidth="2.0"
            strokeLinecap="round"
          />
          {/* Minimal arrowhead (tip at 0, 0) */}
          <Polygon
            points="0,0 -10,-3.5 -8,0 -10,3.5"
            fill="#FFFFFF"
          />
          {/* Refined forward-facing fletching pair 1 */}
          <Line
            x1="-50"
            y1="-4"
            x2="-44"
            y2="0"
            stroke="rgba(255, 255, 255, 0.9)"
            strokeWidth="1.5"
            strokeLinecap="round"
          />
          <Line
            x1="-50"
            y1="4"
            x2="-44"
            y2="0"
            stroke="rgba(255, 255, 255, 0.9)"
            strokeWidth="1.5"
            strokeLinecap="round"
          />
          {/* Refined forward-facing fletching pair 2 */}
          <Line
            x1="-44"
            y1="-4"
            x2="-38"
            y2="0"
            stroke="rgba(255, 255, 255, 0.9)"
            strokeWidth="1.5"
            strokeLinecap="round"
          />
          <Line
            x1="-44"
            y1="4"
            x2="-38"
            y2="0"
            stroke="rgba(255, 255, 255, 0.9)"
            strokeWidth="1.5"
            strokeLinecap="round"
          />
        </Svg>
      </Animated.View>
    </View>
  );
}

const styles = StyleSheet.create({
  zeroPivot: {
    position: 'absolute',
    left: 0,
    top: 0,
    width: 0,
    height: 0,
  },
  // iOS does not reliably composite animated SVG children whose native
  // parent has an exactly zero-sized layout box. Keep Android's original
  // zero-size pivot untouched, while giving iOS a 1x1 native surface whose
  // center remains exactly on the logical (0, 0) pivot.
  iosNativePivot: {
    left: -0.5,
    top: -0.5,
    width: 1,
    height: 1,
  },
  bowSvg: {
    position: 'absolute',
    left: -38,
    top: -50,
    overflow: 'visible',
  },
  arrowSvg: {
    position: 'absolute',
    left: -54,
    top: -10,
    overflow: 'visible',
  },
});
