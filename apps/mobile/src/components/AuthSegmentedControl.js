import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { useTranslation } from 'react-i18next';
import { useAppTheme } from '../context/ThemeProvider';
import { spacing } from '../theme/spacing';
import { typography } from '../theme/typography';
import motionTokens from '../motion/motionTokens';
import PressableScale from './PressableScale';

/**
 * Premium Segmented Control for Sign In / Sign Up switching.
 * @param {'signIn' | 'signUp'} activeTab
 * @param {(tab: 'signIn' | 'signUp') => void} onTabChange
 */
export default function AuthSegmentedControl({
  activeTab = 'signIn',
  onTabChange,
  style,
}) {
  const { colors } = useAppTheme();
  const styles = createStyles(colors);
  const { t } = useTranslation();
  const isSignIn = activeTab === 'signIn';

  const handleSignInPress = () => {
    if (!isSignIn && onTabChange) {
      onTabChange('signIn');
    }
  };

  const handleSignUpPress = () => {
    if (isSignIn && onTabChange) {
      onTabChange('signUp');
    }
  };

  return (
    <View
      style={[styles.container, style]}
      accessibilityRole="tablist"
    >
      {/* Sign In Tab */}
      <PressableScale
        style={[styles.tab, isSignIn ? styles.activeTab : styles.inactiveTab]}
        onPress={handleSignInPress}
        scaleTo={isSignIn ? 1 : motionTokens.scales.chipPressed}
        activeOpacity={isSignIn ? 1 : motionTokens.opacities.pressed}
        haptic={isSignIn ? 'none' : 'selection'}
        accessibilityRole="tab"
        accessibilityState={{ selected: isSignIn }}
        accessibilityLabel={t('auth.segmentedSignInA11y')}
        hitSlop={{ top: 6, bottom: 6, left: 6, right: 6 }}
      >
        <Text
          style={[styles.tabText, isSignIn ? styles.activeTabText : styles.inactiveTabText]}
          numberOfLines={1}
          adjustsFontSizeToFit
          minimumFontScale={0.8}
        >
          {t('auth.segmentedSignIn')}
        </Text>
      </PressableScale>

      {/* Sign Up Tab */}
      <PressableScale
        style={[styles.tab, !isSignIn ? styles.activeTab : styles.inactiveTab]}
        onPress={handleSignUpPress}
        scaleTo={!isSignIn ? 1 : motionTokens.scales.chipPressed}
        activeOpacity={!isSignIn ? 1 : motionTokens.opacities.pressed}
        haptic={!isSignIn ? 'none' : 'selection'}
        accessibilityRole="tab"
        accessibilityState={{ selected: !isSignIn }}
        accessibilityLabel={t('auth.segmentedSignUpA11y')}
        hitSlop={{ top: 6, bottom: 6, left: 6, right: 6 }}
      >
        <Text
          style={[styles.tabText, !isSignIn ? styles.activeTabText : styles.inactiveTabText]}
          numberOfLines={1}
          adjustsFontSizeToFit
          minimumFontScale={0.8}
        >
          {t('auth.segmentedSignUp')}
        </Text>
      </PressableScale>
    </View>
  );
}

const createStyles = (colors) => StyleSheet.create({
  container: {
    flexDirection: 'row',
    backgroundColor: colors.glass.activePill,
    borderRadius: spacing.radii.pill,
    padding: 3,
    borderWidth: 1,
    borderColor: colors.glass.borderHairline,
    marginBottom: spacing.lg,
  },
  tab: {
    flex: 1,
    minWidth: 0,
    paddingHorizontal: spacing.xs,
    minHeight: 38,
    borderRadius: spacing.radii.pill,
    alignItems: 'center',
    justifyContent: 'center',
  },
  activeTab: {
    backgroundColor: colors.accentStrong || colors.tealDark,
    shadowColor: colors.accentStrong || colors.tealDark,
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.18,
    shadowRadius: 4,
    elevation: 2,
  },
  inactiveTab: {
    backgroundColor: 'transparent',
  },
  tabText: {
    ...typography.caption,
    fontWeight: '600',
    fontSize: 13,
    textAlign: 'center',
  },
  activeTabText: {
    color: colors.textInverse || colors.white,
    fontWeight: '700',
  },
  inactiveTabText: {
    color: colors.textSecondary || colors.textMuted,
  },
});
