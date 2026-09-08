import React, { useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { useTranslation } from 'react-i18next';
import { useLocalization } from '../localization/LocalizationContext';
import colors from '../theme/colors';
import { spacing } from '../theme/spacing';
import { typography } from '../theme/typography';
import haptics from '../services/haptics';

const LANGUAGE_OPTIONS = [
  { code: 'en', label: 'EN' },
  { code: 'tr', label: 'TR' },
  { code: 'ar', label: 'AR' },
];

export default function PreAuthLanguageSwitcher({
  disabled = false,
  style,
}) {
  const { t } = useTranslation();
  const { locale, setLocale } = useLocalization();
  const [changingLocale, setChangingLocale] = useState(null);

  const handleChange = async (nextLocale) => {
    if (
      disabled ||
      changingLocale ||
      nextLocale === locale
    ) {
      return;
    }

    setChangingLocale(nextLocale);

    try {
      const changed = await setLocale(nextLocale);

      if (!changed) {
        throw new Error('LANGUAGE_CHANGE_REJECTED');
      }

      haptics.selection();
    } catch (error) {
      console.warn(
        'Pre-auth language change failed:',
        error
      );

      haptics.error();

      Alert.alert(
        t('settings.languagePicker.changeFailedTitle'),
        t('settings.languagePicker.changeFailedMessage')
      );
    } finally {
      setChangingLocale(null);
    }
  };

  return (
    <View
      style={[styles.wrapper, style]}
      accessibilityRole="radiogroup"
    >
      {LANGUAGE_OPTIONS.map((option) => {
        const selected = locale === option.code;
        const changing = changingLocale === option.code;
        const optionDisabled =
          disabled || Boolean(changingLocale);

        return (
          <TouchableOpacity
            key={option.code}
            style={[
              styles.option,
              selected && styles.optionSelected,
              optionDisabled && styles.optionDisabled,
            ]}
            onPress={() => handleChange(option.code)}
            disabled={optionDisabled}
            activeOpacity={0.72}
            accessibilityRole="radio"
            accessibilityState={{
              selected,
              disabled: optionDisabled,
            }}
            accessibilityLabel={t(
              `languages.${option.code}`
            )}
          >
            {changing ? (
              <ActivityIndicator
                size="small"
                color={
                  colors.accentStrong ||
                  colors.tealDark
                }
              />
            ) : (
              <Text
                style={[
                  styles.optionText,
                  selected &&
                    styles.optionTextSelected,
                ]}
              >
                {option.label}
              </Text>
            )}
          </TouchableOpacity>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  wrapper: {
    alignSelf: 'flex-end',
    flexDirection: 'row',
    direction: 'ltr',
    alignItems: 'center',
    padding: 3,
    borderRadius: spacing.radii.pill,
    backgroundColor: 'rgba(255, 255, 255, 0.62)',
    borderWidth: 1,
    borderColor: 'rgba(14, 116, 144, 0.12)',
  },

  option: {
    minWidth: 38,
    minHeight: 32,
    paddingHorizontal: spacing.sm,
    borderRadius: spacing.radii.pill,
    alignItems: 'center',
    justifyContent: 'center',
  },

  optionSelected: {
    backgroundColor: 'rgba(14, 116, 144, 0.14)',
  },

  optionDisabled: {
    opacity: 0.62,
  },

  optionText: {
    ...typography.caption,
    fontSize: 12,
    fontWeight: '600',
    color: colors.textSecondary || colors.textMuted,
  },

  optionTextSelected: {
    color: colors.accentStrong || colors.tealDark,
    fontWeight: '800',
  },
});
