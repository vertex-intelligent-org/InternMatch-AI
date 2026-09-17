import React, { useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Animated,
  Easing,
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

const CIRCLE_SIZE = 36;
const COLLAPSED_WIDTH = 40;
const EXPANDED_WIDTH = 124;
const ANIMATION_DURATION_MS = 180;

export default function PreAuthLanguageSwitcher({
  disabled = false,
  style,
}) {
  const { t } = useTranslation();
  const { locale, setLocale } = useLocalization();

  const [expanded, setExpanded] = useState(false);
  const [changingLocale, setChangingLocale] = useState(null);
  const localeChangeInFlightRef = useRef(false);

  const expansion = useRef(
    new Animated.Value(0)
  ).current;

  useEffect(() => {
    Animated.timing(expansion, {
      toValue: expanded ? 1 : 0,
      duration: ANIMATION_DURATION_MS,
      easing: Easing.out(Easing.cubic),
      useNativeDriver: false,
    }).start();
  }, [expanded, expansion]);

  useEffect(() => {
    if (disabled && expanded) {
      setExpanded(false);
    }
  }, [disabled, expanded]);

  const toggleExpanded = () => {
    if (disabled || changingLocale) {
      return;
    }

    haptics.selection();
    setExpanded((current) => !current);
  };

  const handleChange = async (nextLocale) => {
    if (
      localeChangeInFlightRef.current ||
      disabled ||
      changingLocale
    ) {
      return;
    }

    if (nextLocale === locale) {
      haptics.selection();
      setExpanded(false);
      return;
    }

    localeChangeInFlightRef.current = true;
    setChangingLocale(nextLocale);

    try {
      const changed = await setLocale(nextLocale);

      if (!changed) {
        throw new Error('LANGUAGE_CHANGE_REJECTED');
      }

      haptics.selection();
      setExpanded(false);
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
      localeChangeInFlightRef.current = false;
      setChangingLocale(null);
    }
  };

  const animatedWidth = expansion.interpolate({
    inputRange: [0, 1],
    outputRange: [
      COLLAPSED_WIDTH,
      EXPANDED_WIDTH,
    ],
  });

  const optionsOpacity = expansion.interpolate({
    inputRange: [0, 0.35, 1],
    outputRange: [0, 0, 1],
  });

  const collapsedOpacity = expansion.interpolate({
    inputRange: [0, 0.65, 1],
    outputRange: [1, 0, 0],
  });

  const currentOption =
    LANGUAGE_OPTIONS.find(
      (option) => option.code === locale
    ) || LANGUAGE_OPTIONS[0];

  return (
    <Animated.View
      style={[
        styles.wrapper,
        {
          width: animatedWidth,
        },
        style,
      ]}
    >
      <Animated.View
        pointerEvents={expanded ? 'none' : 'auto'}
        style={[
          styles.collapsedLayer,
          {
            opacity: collapsedOpacity,
          },
        ]}
      >
        <TouchableOpacity
          style={[
            styles.option,
            styles.optionSelected,
            disabled && styles.optionDisabled,
          ]}
          onPress={toggleExpanded}
          disabled={disabled || Boolean(changingLocale)}
          activeOpacity={0.72}
          accessibilityRole="button"
          accessibilityState={{
            expanded,
            disabled:
              disabled || Boolean(changingLocale),
          }}
          accessibilityLabel={`${t(
            `languages.${currentOption.code}`
          )}. ${t('settings.languagePicker.title', {
            defaultValue: 'Change language',
          })}`}
        >
          <Text
            style={[
              styles.optionText,
              styles.optionTextSelected,
            ]}
          >
            {currentOption.label}
          </Text>
        </TouchableOpacity>
      </Animated.View>

      <Animated.View
        pointerEvents={expanded ? 'auto' : 'none'}
        style={[
          styles.optionsLayer,
          {
            opacity: optionsOpacity,
          },
        ]}
        accessibilityRole="radiogroup"
      >
        {LANGUAGE_OPTIONS.map((option) => {
          const selected =
            locale === option.code;

          const changing =
            changingLocale === option.code;

          const optionDisabled =
            disabled ||
            Boolean(changingLocale);

          return (
            <TouchableOpacity
              key={option.code}
              style={[
                styles.option,
                selected && styles.optionSelected,
                optionDisabled &&
                  styles.optionDisabled,
              ]}
              onPress={() =>
                handleChange(option.code)
              }
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
      </Animated.View>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  wrapper: {
    alignSelf: 'flex-end',
    height: COLLAPSED_WIDTH,
    borderRadius: COLLAPSED_WIDTH / 2,
    backgroundColor:
      'rgba(255, 255, 255, 0.62)',
    borderWidth: 1,
    borderColor:
      'rgba(14, 116, 144, 0.12)',
    overflow: 'hidden',
    direction: 'ltr',
  },

  collapsedLayer: {
    ...StyleSheet.absoluteFillObject,
    alignItems: 'center',
    justifyContent: 'center',
  },

  optionsLayer: {
    flex: 1,
    flexDirection: 'row',
    direction: 'ltr',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 2,
  },

  option: {
    width: CIRCLE_SIZE,
    height: CIRCLE_SIZE,
    borderRadius: CIRCLE_SIZE / 2,
    alignItems: 'center',
    justifyContent: 'center',
  },

  optionSelected: {
    backgroundColor:
      'rgba(14, 116, 144, 0.14)',
  },

  optionDisabled: {
    opacity: 0.62,
  },

  optionText: {
    ...typography.caption,
    fontSize: 12,
    fontWeight: '600',
    color:
      colors.textSecondary ||
      colors.textMuted,
  },

  optionTextSelected: {
    color:
      colors.accentStrong ||
      colors.tealDark,
    fontWeight: '800',
  },
});
