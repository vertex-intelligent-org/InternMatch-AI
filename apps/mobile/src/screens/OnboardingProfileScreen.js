import React, { useState } from 'react';
import {
  View,
  Text,
  TextInput,
  StyleSheet,
  TouchableOpacity,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  Alert,
} from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { Ionicons } from '@expo/vector-icons';
import { useTranslation } from 'react-i18next';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import colors from '../theme/colors';
import { spacing } from '../theme/spacing';
import { typography } from '../theme/typography';
import InternMatchLogo from '../components/InternMatchLogo';
import AuthGlassPanel from '../components/AuthGlassPanel';
import GradientButton from '../components/GradientButton';
import { useLocalization } from '../localization/LocalizationContext';
import { upsertProfile } from '../services/api';
import { useProfile } from '../context/ProfileContext';
import haptics from '../services/haptics';

export default function OnboardingProfileScreen({ navigation, route }) {
  const { t } = useTranslation();
  const { isRTL } = useLocalization();
  const insets = useSafeAreaInsets();

  const initialName =
    typeof route?.params?.initialName === 'string'
      ? route.params.initialName
      : '';

  const initialDepartment =
    typeof route?.params?.initialDepartment === 'string'
      ? route.params.initialDepartment
      : '';

  const initialAccountType =
    route?.params?.initialAccountType === 'employer'
      ? 'employer'
      : 'intern';

  const [accountType, setAccountType] = useState(initialAccountType);
  const [fullName, setFullName] = useState(initialName);
  const [department, setDepartment] = useState(initialDepartment);
  const [headline, setHeadline] = useState('');
  const [focusedField, setFocusedField] = useState(null);
  const [saving, setSaving] = useState(false);

  const { setProfile } = useProfile();

  const handleComplete = async () => {
    const trimmedName = fullName.trim();
    const trimmedDepartment = department.trim();
    const trimmedHeadline = headline.trim() || null;

    if (!trimmedName) {
      haptics.error();
      Alert.alert(
        t('common.error'),
        t('onboarding.enterFullName')
      );
      return;
    }

    if (saving) return;

    setSaving(true);

    try {
      const payload = {
        full_name: trimmedName,
        headline: trimmedHeadline,
        preferences: {
          account_type: accountType,
          department: trimmedDepartment || null,
        },
      };

      const created = await upsertProfile(payload);

      setProfile(created);
      navigation.replace('MainTabs');
    } catch (error) {
      console.warn(
        'Profile save failed during onboarding:',
        error
      );

      haptics.error();

      Alert.alert(
        t('common.error'),
        t('errors.profileSaveFailed')
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <LinearGradient
      colors={['#DBF1F5', '#EAF6F8', '#E3F4F6']}
      style={styles.container}
    >
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={styles.flex}
      >
        <ScrollView
          contentContainerStyle={[
            styles.content,
            {
              paddingTop:
                Math.max(insets.top, 16) + spacing.md,
              paddingBottom:
                Math.max(insets.bottom, 20) + spacing.xl,
            },
          ]}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          <View style={styles.brandZone}>
            <InternMatchLogo />
          </View>

          <View style={styles.headingZone}>
            <Text
              style={[
                styles.title,
                isRTL && styles.textRTL,
              ]}
            >
              {t('onboarding.title')}
            </Text>

            <Text
              style={[
                styles.subtitle,
                isRTL && styles.textRTL,
              ]}
            >
              {t('onboarding.subtitle')}
            </Text>
          </View>

          <AuthGlassPanel style={styles.panel}>
            <View style={styles.fieldGroup}>
              <Text
                style={[
                  styles.fieldLabel,
                  isRTL && styles.textRTL,
                ]}
              >
                {t('onboarding.accountType')}
              </Text>

              <View
                style={[
                  styles.typeRow,
                  isRTL && styles.typeRowRTL,
                ]}
                accessibilityRole="radiogroup"
              >
                <TouchableOpacity
                  style={[
                    styles.typeCard,
                    accountType === 'intern'
                      ? styles.typeCardActive
                      : styles.typeCardInactive,
                  ]}
                  onPress={() => {
                    haptics.selection();
                    setAccountType('intern');
                  }}
                  accessibilityRole="radio"
                  accessibilityState={{
                    selected: accountType === 'intern',
                  }}
                  accessibilityLabel={t(
                    'onboarding.internA11y'
                  )}
                >
                  <Ionicons
                    name="school-outline"
                    size={19}
                    color={
                      accountType === 'intern'
                        ? colors.accentStrong ||
                          colors.tealDark
                        : colors.textSecondary ||
                          colors.textMuted
                    }
                  />

                  <Text
                    style={[
                      styles.typeText,
                      accountType === 'intern'
                        ? styles.typeTextActive
                        : styles.typeTextInactive,
                    ]}
                  >
                    {t('onboarding.intern')}
                  </Text>
                </TouchableOpacity>

                <TouchableOpacity
                  style={[
                    styles.typeCard,
                    accountType === 'employer'
                      ? styles.typeCardActive
                      : styles.typeCardInactive,
                  ]}
                  onPress={() => {
                    haptics.selection();
                    setAccountType('employer');
                  }}
                  accessibilityRole="radio"
                  accessibilityState={{
                    selected: accountType === 'employer',
                  }}
                  accessibilityLabel={t(
                    'onboarding.employerA11y'
                  )}
                >
                  <Ionicons
                    name="briefcase-outline"
                    size={19}
                    color={
                      accountType === 'employer'
                        ? colors.accentStrong ||
                          colors.tealDark
                        : colors.textSecondary ||
                          colors.textMuted
                    }
                  />

                  <Text
                    style={[
                      styles.typeText,
                      accountType === 'employer'
                        ? styles.typeTextActive
                        : styles.typeTextInactive,
                    ]}
                  >
                    {t('onboarding.employer')}
                  </Text>
                </TouchableOpacity>
              </View>
            </View>

            <View style={styles.fieldGroup}>
              <Text
                style={[
                  styles.fieldLabel,
                  isRTL && styles.textRTL,
                ]}
              >
                {t('onboarding.fullName')}
              </Text>

              <TextInput
                style={[
                  styles.input,
                  focusedField === 'fullName' &&
                    styles.inputFocused,
                  isRTL && styles.inputRTL,
                ]}
                placeholder={t(
                  'onboarding.fullNamePlaceholder'
                )}
                placeholderTextColor="rgba(22, 35, 46, 0.40)"
                value={fullName}
                onChangeText={setFullName}
                onFocus={() =>
                  setFocusedField('fullName')
                }
                onBlur={() => setFocusedField(null)}
                autoCapitalize="words"
                accessibilityLabel={t(
                  'onboarding.fullName'
                )}
              />
            </View>

            <View style={styles.fieldGroup}>
              <Text
                style={[
                  styles.fieldLabel,
                  isRTL && styles.textRTL,
                ]}
              >
                {t('onboarding.department')}
              </Text>

              <TextInput
                style={[
                  styles.input,
                  focusedField === 'department' &&
                    styles.inputFocused,
                  isRTL && styles.inputRTL,
                ]}
                placeholder={t(
                  'onboarding.departmentPlaceholder'
                )}
                placeholderTextColor="rgba(22, 35, 46, 0.40)"
                value={department}
                onChangeText={setDepartment}
                onFocus={() =>
                  setFocusedField('department')
                }
                onBlur={() => setFocusedField(null)}
                accessibilityLabel={t(
                  'onboarding.department'
                )}
              />
            </View>

            <View style={styles.fieldGroup}>
              <Text
                style={[
                  styles.fieldLabel,
                  isRTL && styles.textRTL,
                ]}
              >
                {t('onboarding.headline')}
              </Text>

              <TextInput
                style={[
                  styles.input,
                  styles.headlineInput,
                  focusedField === 'headline' &&
                    styles.inputFocused,
                  isRTL && styles.inputRTL,
                ]}
                placeholder={t(
                  'onboarding.headlinePlaceholder'
                )}
                placeholderTextColor="rgba(22, 35, 46, 0.40)"
                value={headline}
                onChangeText={setHeadline}
                onFocus={() =>
                  setFocusedField('headline')
                }
                onBlur={() => setFocusedField(null)}
                multiline
                maxLength={160}
                accessibilityLabel={t(
                  'onboarding.headline'
                )}
              />
            </View>

            <GradientButton
              title={
                saving
                  ? t('onboarding.saving')
                  : t('onboarding.saveAndContinue')
              }
              color={colors.accent || colors.teal}
              onPress={handleComplete}
              disabled={saving}
              style={styles.primaryCta}
            />
          </AuthGlassPanel>
        </ScrollView>
      </KeyboardAvoidingView>
    </LinearGradient>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },

  flex: {
    flex: 1,
  },

  content: {
    flexGrow: 1,
    paddingHorizontal: spacing.screenHorizontalPadding,
    alignItems: 'center',
  },

  brandZone: {
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: spacing.lg,
  },

  headingZone: {
    width: '100%',
    alignItems: 'center',
    marginBottom: spacing.lg,
    paddingHorizontal: spacing.sm,
  },

  title: {
    ...typography.display,
    fontSize: 24,
    lineHeight: 30,
    fontWeight: '800',
    color: colors.textPrimary || colors.textDark,
    textAlign: 'center',
  },

  subtitle: {
    ...typography.body,
    fontSize: 14,
    lineHeight: 20,
    color: colors.textSecondary || colors.textMuted,
    textAlign: 'center',
    marginTop: spacing.xxs,
    maxWidth: 360,
  },

  panel: {
    width: '100%',
  },

  fieldGroup: {
    marginBottom: spacing.md,
  },

  fieldLabel: {
    ...typography.caption,
    fontWeight: '600',
    color: colors.textPrimary || colors.textDark,
    marginBottom: spacing.xs,
  },

  typeRow: {
    flexDirection: 'row',
    gap: spacing.sm,
  },

  typeRowRTL: {
    flexDirection: 'row-reverse',
  },

  typeCard: {
    flex: 1,
    minHeight: 48,
    borderRadius: spacing.radii.md,
    borderWidth: 1.5,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: spacing.sm,
  },

  typeCardActive: {
    backgroundColor: 'rgba(14, 116, 144, 0.12)',
    borderColor: colors.accent || colors.teal,
  },

  typeCardInactive: {
    backgroundColor: 'rgba(255, 255, 255, 0.70)',
    borderColor: 'rgba(14, 116, 144, 0.14)',
  },

  typeText: {
    ...typography.button,
    marginStart: spacing.xs + 2,
    fontSize: 13,
  },

  typeTextActive: {
    color: colors.accentStrong || colors.tealDark,
    fontWeight: '700',
  },

  typeTextInactive: {
    color: colors.textSecondary || colors.textMuted,
    fontWeight: '500',
  },

  input: {
    backgroundColor: '#FFFFFF',
    borderRadius: spacing.radii.md,
    minHeight: 48,
    paddingHorizontal: spacing.md,
    borderWidth: 1.5,
    borderColor: 'rgba(14, 116, 144, 0.16)',
    color: colors.textDark,
    ...typography.body,
  },

  headlineInput: {
    minHeight: 88,
    paddingTop: spacing.md,
    textAlignVertical: 'top',
  },

  inputFocused: {
    borderColor: colors.accent || colors.teal,
    backgroundColor: '#FFFFFF',
    shadowColor: colors.accent || colors.teal,
    shadowOffset: {
      width: 0,
      height: 1,
    },
    shadowOpacity: 0.12,
    shadowRadius: 4,
    elevation: 2,
  },

  inputRTL: {
    textAlign: 'right',
    writingDirection: 'rtl',
  },

  textRTL: {
    textAlign: 'right',
    writingDirection: 'rtl',
  },

  primaryCta: {
    marginTop: spacing.sm,
  },
});
