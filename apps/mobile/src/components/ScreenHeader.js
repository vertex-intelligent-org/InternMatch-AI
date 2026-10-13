import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import BackButton from './BackButton';
import colors from '../theme/colors';
import { useAppTheme } from '../context/ThemeProvider';
import { spacing } from '../theme/spacing';
import { typography } from '../theme/typography';
import { useLocalization } from '../localization/LocalizationContext';

export default function ScreenHeader({
  title,
  subtitle,
  showBack = false,
  navigation,
  onBackPress,
  rightAction,
  alignment = 'center', // 'center' | 'start'
  style,
  titleStyle,
  bordered = false,
}) {
  const isStart = alignment === 'start';
  const { isRTL } = useLocalization();
  const { colors } = useAppTheme();

  return (
    <View
      style={[
        styles.header,
        isRTL && styles.headerRTL,
        bordered && styles.bordered,
        style,
      ]}
    >
      {/* Left Slot: Back button or empty spacer */}
      {showBack ? (
        <View style={[styles.leftSlot, isRTL && styles.leftSlotRTL]}>
          <BackButton navigation={navigation} onPress={onBackPress} />
        </View>
      ) : isStart ? null : (
        <View style={styles.leftSlot} />
      )}

      {/* Center/Title Slot */}
      <View
        style={[
          styles.titleContainer,
          isStart && styles.titleContainerStart,
          isStart && isRTL && styles.titleContainerStartRTL,
          !showBack && isStart && styles.titleContainerStartNoBack,
        ]}
      >
        {title ? (
          <Text
            style={[
              styles.title,
              { color: colors.textPrimary || colors.textDark },
              isStart && styles.titleStart,
              isRTL && styles.titleRTL,
              isStart && isRTL && styles.titleStartRTL,
              titleStyle,
            ]}
            numberOfLines={1}
            accessibilityRole="header"
          >
            {title}
          </Text>
        ) : null}
        {subtitle ? (
          <Text
            style={[
              styles.subtitle,
              { color: colors.textSecondary || colors.textMuted },
              isStart && styles.subtitleStart,
              isRTL && styles.subtitleRTL,
              isStart && isRTL && styles.subtitleStartRTL,
            ]}
            numberOfLines={1}
          >
            {subtitle}
          </Text>
        ) : null}
      </View>

      {/* Right Slot: Custom action or balancing spacer */}
      {rightAction ? (
        <View style={[styles.rightSlot, isRTL && styles.rightSlotRTL]}>{rightAction}</View>
      ) : isStart ? null : (
        <View style={[styles.rightSlotSpacer, isRTL && styles.rightSlotSpacerRTL]} />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    minHeight: spacing.headerContentHeight,
    paddingHorizontal: spacing.screenHorizontalPadding,
    backgroundColor: colors.background || colors.screenBg,
  },
  headerRTL: {
    flexDirection: 'row-reverse',
  },
  bordered: {
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.glass?.borderHairline || colors.borderSubtle || colors.border,
  },
  leftSlot: {
    minWidth: spacing.minimumTouchTarget,
    minHeight: spacing.minimumTouchTarget,
    alignItems: 'flex-start',
    justifyContent: 'center',
    marginEnd: spacing.xs,
  },
  leftSlotRTL: {
    alignItems: 'flex-end',
    marginEnd: 0,
    marginStart: spacing.xs,
  },
  titleContainer: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: spacing.xs,
  },
  titleContainerStart: {
    alignItems: 'flex-start',
    paddingHorizontal: 0,
  },
  titleContainerStartNoBack: {
    paddingStart: 0,
  },
  titleContainerStartRTL: {
    alignItems: 'flex-end',
  },
  rightSlot: {
    minWidth: spacing.minimumTouchTarget,
    minHeight: spacing.minimumTouchTarget,
    alignItems: 'flex-end',
    justifyContent: 'center',
    marginStart: spacing.xs,
  },
  rightSlotRTL: {
    alignItems: 'flex-start',
    marginStart: 0,
    marginEnd: spacing.xs,
  },
  rightSlotSpacer: {
    width: spacing.minimumTouchTarget,
    height: spacing.minimumTouchTarget,
    marginStart: spacing.xs,
  },
  rightSlotSpacerRTL: {
    marginStart: 0,
    marginEnd: spacing.xs,
  },
  title: {
    ...typography.screenTitle,
    color: colors.textPrimary || colors.textDark,
    textAlign: 'center',
  },
  titleRTL: {
    writingDirection: 'rtl',
  },
  titleStart: {
    textAlign: 'left',
  },
  titleStartRTL: {
    textAlign: 'right',
  },
  subtitle: {
    ...typography.caption,
    color: colors.textSecondary || colors.textMuted,
    textAlign: 'center',
    marginTop: spacing.xxs,
  },
  subtitleRTL: {
    writingDirection: 'rtl',
  },
  subtitleStart: {
    textAlign: 'left',
  },
  subtitleStartRTL: {
    textAlign: 'right',
  },
});
