export const colors = {
  // Gradient (Splash / Sign In / Sign Up backgrounds)
  gradientStart: '#12C7E0',
  gradientMid: '#0F93AA',
  gradientEnd: '#075E6E',

  // Brand
  primaryBlue: '#3A3AF0',
  teal: '#0E7490',
  tealDark: '#0B5F70',

  // Backgrounds
  screenBg: '#EAF6F8',
  authGradientStart: '#DBF1F5',
  authGradientMid: '#EAF6F8',
  authGradientEnd: '#E3F4F6',
  cardBg: '#FFFFFF',
  inputBg: '#E2E2E2',

  // Text
  textDark: '#16232E',
  textMuted: '#6B7686',
  textOnGradient: '#FFFFFF',

  // Status
  green: '#22C58B',
  greenBg: '#D3F4E6',
  orange: '#F2A93B',
  orangeBg: '#FBE7C6',
  purple: '#8B87F0',
  purpleBg: '#E4E2FC',
  red: '#EF5A5A',
  redBg: '#FCE1E1',

  border: '#D8E4E8',
  white: '#FFFFFF',

  // Semantic Token Foundation (Gate 2.38B)
  background: '#EAF6F8',
  surface: '#FFFFFF',
  surfaceElevated: '#FFFFFF',
  surfaceSubtle: '#F8FAFC',
  surfaceMuted: '#F1F5F9',

  textPrimary: '#16232E',
  textSecondary: '#4B5563',
  textTertiary: '#6B7686',
  textInverse: '#FFFFFF',

  accent: '#0E7490',
  accentStrong: '#0B5F70',
  accentSoft: '#E6F4F6',

  borderSubtle: '#E2E8F0',
  borderStrong: '#CBD5E1',

  success: '#10B981',
  successSoft: '#DCFCE7',
  warning: '#D97706',
  warningSoft: '#FEF3C7',
  danger: '#EF4444',
  dangerSoft: '#FEE2E2',
  info: '#0284C7',
  infoSoft: '#E0F2FE',

  // Glass & Material Tokens (Gate 2.38F-A)
  glass: {
    bgLight: 'rgba(255, 255, 255, 0.72)',
    bgFallback: 'rgba(255, 255, 255, 0.95)',
    borderLight: 'rgba(255, 255, 255, 0.65)',
    borderHairline: 'rgba(14, 116, 144, 0.12)',
    activePill: 'rgba(14, 116, 144, 0.08)',
    shadow: 'rgba(15, 23, 42, 0.06)',
  },
};

export const gradientColors = [colors.gradientStart, colors.gradientMid, colors.gradientEnd];

export const semanticColors = {
  background: colors.background,
  surface: colors.surface,
  surfaceElevated: colors.surfaceElevated,
  surfaceSubtle: colors.surfaceSubtle,
  surfaceMuted: colors.surfaceMuted,
  textPrimary: colors.textPrimary,
  textSecondary: colors.textSecondary,
  textTertiary: colors.textTertiary,
  textInverse: colors.textInverse,
  accent: colors.accent,
  accentStrong: colors.accentStrong,
  accentSoft: colors.accentSoft,
  borderSubtle: colors.borderSubtle,
  borderStrong: colors.borderStrong,
  success: colors.success,
  successSoft: colors.successSoft,
  warning: colors.warning,
  warningSoft: colors.warningSoft,
  danger: colors.danger,
  dangerSoft: colors.dangerSoft,
  info: colors.info,
  infoSoft: colors.infoSoft,
};

export const lightThemeColors = colors;

export const darkThemeColors = {
  ...colors,

  // Semantic surfaces
  background: '#07171D',
  screenBg: '#07171D',
  authGradientStart: '#061419',
  authGradientMid: '#0A2027',
  authGradientEnd: '#0D2931',
  surface: '#0D232A',
  surfaceElevated: '#112B33',
  surfaceSubtle: '#10262D',
  surfaceMuted: '#16313A',

  // Semantic text
  textPrimary: '#F2F7F8',
  textSecondary: '#C0D0D5',
  textTertiary: '#94A9B0',
  textDark: '#F2F7F8',
  textMuted: '#A7BBC1',
  textInverse: '#07171D',

  // Accent
  accent: '#20B9D2',
  accentStrong: '#5AD4E5',
  accentSoft: '#113A43',

  // Borders
  border: '#27434B',
  borderSubtle: '#24414A',
  borderStrong: '#36545D',

  // Status
  success: '#34D399',
  successSoft: '#10382C',
  warning: '#F59E0B',
  warningSoft: '#3A2A0D',
  danger: '#F87171',
  dangerSoft: '#3C1719',
  info: '#38BDF8',
  infoSoft: '#0C3342',

  // Legacy semantic backgrounds
  greenBg: '#10382C',
  orangeBg: '#3A2A0D',
  purpleBg: '#2A2448',
  redBg: '#3C1719',

  // Inputs
  inputBg: '#112B33',

  // Glass
  glass: {
    ...colors.glass,
    bgLight: 'rgba(13, 35, 42, 0.72)',
    bgFallback: 'rgba(13, 35, 42, 0.96)',
    borderLight: 'rgba(255, 255, 255, 0.10)',
    borderHairline: 'rgba(255, 255, 255, 0.08)',
    activePill: 'rgba(32, 185, 210, 0.14)',
    shadow: 'rgba(0, 0, 0, 0.32)',
  },
};

export const getThemeColors = (mode) =>
  mode === 'dark' ? darkThemeColors : lightThemeColors;

export default colors;
