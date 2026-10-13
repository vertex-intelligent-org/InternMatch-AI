import React from 'react';
import { View, StyleSheet } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useAppTheme } from '../context/ThemeProvider';

export default function ScreenContainer({
  children,
  style,
  edges = ['top', 'bottom'],
  backgroundColor = colors.background || colors.screenBg,
  paddingHorizontal = 0,
}) {
  const insets = useSafeAreaInsets();
  const { colors } = useAppTheme();

  const safeStyle = {
    flex: 1,
    backgroundColor: backgroundColor ?? colors.background,
    paddingTop: edges.includes('top') ? insets.top : 0,
    paddingBottom: edges.includes('bottom') ? insets.bottom : 0,
    paddingStart: edges.includes('left') || edges.includes('start') ? insets.left : paddingHorizontal,
    paddingEnd: edges.includes('right') || edges.includes('end') ? insets.right : paddingHorizontal,
  };

  return <View style={[safeStyle, style]}>{children}</View>;
}
