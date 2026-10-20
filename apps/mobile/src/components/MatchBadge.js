import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { useAppTheme } from '../context/ThemeProvider';

// score: 0-100. >=85 green, 65-84 orange/peach, <65 red-ish
function getPalette(score, colors) {
  if (score >= 85) return { bg: colors.greenBg, fg: colors.green };
  if (score >= 65) return { bg: colors.orangeBg, fg: colors.orange };
  return { bg: colors.redBg, fg: colors.red };
}

export default function MatchBadge({ score, style }) {
  const { colors } = useAppTheme();
  const { bg, fg } = getPalette(score, colors);
  return (
    <View style={[styles.badge, { backgroundColor: bg }, style]}>
      <Text style={[styles.text, { color: fg, writingDirection: 'ltr' }]}>
        {score}%
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  badge: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 12,
  },
  text: {
    fontSize: 13,
    fontWeight: '700',
  },
});
