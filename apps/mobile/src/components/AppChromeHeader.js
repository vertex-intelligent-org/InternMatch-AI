import React from 'react';
import { View, StyleSheet } from 'react-native';
import colors from '../theme/colors';
import { useAppTheme } from '../context/ThemeProvider';
import { spacing } from '../theme/spacing';
import InternMatchLogo from './InternMatchLogo';
import PlanBadge from './PlanBadge';

import NotificationBell from './NotificationBell';
export default function AppChromeHeader({ style, rightAction, plan = 'free', onPlanPress }) {
  const { colors } = useAppTheme();
  return (
    <View
      style={[
        styles.headerContainer,
        {
          backgroundColor: colors.surface,
          borderBottomColor: colors.borderSubtle,
        },
        style,
      ]}
    >
      <View style={styles.contentRow}>
        <InternMatchLogo style={styles.logoItem} />
        <View style={styles.rightGroup}>
          <NotificationBell />
      <PlanBadge plan={plan} onPress={onPlanPress} style={styles.badgeItem} />
          {rightAction ? <View style={styles.actionItem}>{rightAction}</View> : null}
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  headerContainer: {
    height: 92,
    justifyContent: 'center',
    paddingHorizontal: spacing.screenHorizontalPadding,
    backgroundColor: colors.surface || '#FFFFFF',
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.borderSubtle || '#E2E8F0',
  },
  contentRow: {
    width: '100%',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  logoItem: {
    alignSelf: 'center',
  },
  rightGroup: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  badgeItem: {
    alignSelf: 'center',
  },
  actionItem: {
    marginStart: spacing.sm,
    alignSelf: 'center',
  },
});
