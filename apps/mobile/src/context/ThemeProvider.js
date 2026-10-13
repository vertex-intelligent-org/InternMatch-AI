import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';
import { Appearance, useColorScheme } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import * as SystemUI from 'expo-system-ui';
import { getThemeColors } from '../theme/colors';

const APPEARANCE_STORAGE_KEY = '@internmatch_ai/appearance';

const VALID_APPEARANCE_MODES = Object.freeze([
  'system',
  'light',
  'dark',
]);

const ThemeContext = createContext(null);

function normalizeAppearance(value) {
  return VALID_APPEARANCE_MODES.includes(value)
    ? value
    : 'system';
}

export function ThemeProvider({ children }) {
  const systemScheme = useColorScheme();

  const [appearance, setAppearanceState] = useState('system');
  const [isInitialized, setIsInitialized] = useState(false);

  useEffect(() => {
    let mounted = true;

    AsyncStorage.getItem(APPEARANCE_STORAGE_KEY)
      .then((storedValue) => {
        if (!mounted) return;

        setAppearanceState(
          normalizeAppearance(storedValue)
        );
      })
      .catch((error) => {
        console.warn(
          'Failed to restore appearance preference:',
          error
        );

        if (mounted) {
          setAppearanceState('system');
        }
      })
      .finally(() => {
        if (mounted) {
          setIsInitialized(true);
        }
      });

    return () => {
      mounted = false;
    };
  }, []);

  const resolvedMode =
    appearance === 'system'
      ? systemScheme === 'dark'
        ? 'dark'
        : 'light'
      : appearance;

  const isDark = resolvedMode === 'dark';

  const colors = useMemo(
    () => getThemeColors(resolvedMode),
    [resolvedMode]
  );

  useEffect(() => {
    SystemUI.setBackgroundColorAsync(colors.background).catch((error) => {
      console.warn(
        'Failed to update system UI background color:',
        error
      );
    });
  }, [colors.background]);

  const navigationTheme = useMemo(
    () => ({
      dark: isDark,
      colors: {
        primary: colors.accent,
        background: colors.background,
        card: colors.surface,
        text: colors.textPrimary,
        border: colors.borderSubtle,
        notification: colors.danger,
      },
    }),
    [colors, isDark]
  );

  const setAppearance = useCallback(async (nextAppearance) => {
    const normalized = normalizeAppearance(nextAppearance);

    setAppearanceState(normalized);

    try {
      await AsyncStorage.setItem(
        APPEARANCE_STORAGE_KEY,
        normalized
      );
    } catch (error) {
      console.warn(
        'Failed to persist appearance preference:',
        error
      );
    }
  }, []);

  useEffect(() => {
    // React Native 0.81 accepts null here to restore
    // inheritance from the operating system.
    Appearance.setColorScheme(
      appearance === 'system'
        ? null
        : appearance
    );
  }, [appearance]);

  const value = useMemo(
    () => ({
      appearance,
      resolvedMode,
      isDark,
      colors,
      navigationTheme,
      isInitialized,
      setAppearance,
    }),
    [
      appearance,
      resolvedMode,
      isDark,
      colors,
      navigationTheme,
      isInitialized,
      setAppearance,
    ]
  );

  return (
    <ThemeContext.Provider value={value}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useAppTheme() {
  const context = useContext(ThemeContext);

  if (!context) {
    throw new Error(
      'useAppTheme must be used within a ThemeProvider'
    );
  }

  return context;
}

export { APPEARANCE_STORAGE_KEY, VALID_APPEARANCE_MODES };