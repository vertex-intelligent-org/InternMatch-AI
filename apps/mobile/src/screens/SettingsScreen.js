import React, { useEffect, useRef, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  Alert,
  Modal,
  ActivityIndicator,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import colors from '../theme/colors';
import { spacing } from '../theme/spacing';
import { typography } from '../theme/typography';
import ScreenContainer from '../components/ScreenContainer';
import ScreenHeader from '../components/ScreenHeader';
import GlassSurface from '../components/GlassSurface';
import { signOut, getCurrentUser, sendPasswordResetEmail } from '../services/auth';
import { PASSWORD_RESET_REDIRECT_URL } from '../services/passwordRecovery';
import { useProfile } from '../context/ProfileContext';
import { useRevenueCat } from '../context/RevenueCatProvider';
import { useSubscription } from '../context/SubscriptionProvider';
import { getSubscriptionSnapshot, normalizeAccountType } from '../services/subscriptionService';
import haptics from '../services/haptics';
import { useTranslation } from 'react-i18next';
import { useLocalization } from '../localization/LocalizationContext';
import { getLocalizedErrorMessage } from '../localization/errorMessages';
import LocaleFlag from '../components/LocaleFlag';

const appVersion = require('../../app.json').expo.version || '1.0.0';

const LANGUAGE_OPTIONS = [
  { code: 'en', label: 'English' },
  { code: 'tr', label: 'T\u00fcrk\u00e7e' },
  { code: 'ar', label: '\u0627\u0644\u0639\u0631\u0628\u064a\u0629' },
];

function SettingsRow({
  icon,
  iconColor,
  flagLocale,
  label,
  value,
  onPress,
  showChevron = true,
  isLast = false,
  accessibilityLabel,
}) {
  const isPressable = typeof onPress === 'function';
  const Wrapper = isPressable ? TouchableOpacity : View;
  const { isRTL } = useLocalization();

  return (
    <Wrapper
      style={[styles.row, isRTL && styles.rowRTL, isLast && styles.rowLast]}
      onPress={
        isPressable
          ? () => {
              haptics.selection();
              onPress();
            }
          : undefined
      }
      activeOpacity={0.7}
      accessibilityRole={isPressable ? 'button' : undefined}
      accessibilityLabel={accessibilityLabel || (typeof label === 'string' ? label : undefined)}
    >
      <View style={[styles.rowLeft, isRTL && styles.rowLeftRTL]}>
        {flagLocale ? (
          <View style={[styles.iconContainer, styles.flagIconContainer, isRTL && styles.iconContainerRTL]}>
            <LocaleFlag locale={flagLocale} width={24} height={16} />
          </View>
        ) : icon ? (
          <View style={[styles.iconContainer, isRTL && styles.iconContainerRTL]}>
            <Ionicons
              name={icon}
              size={18}
              color={iconColor || colors.accent || colors.teal}
            />
          </View>
        ) : null}
        <Text style={[styles.rowLabel, isRTL && styles.textRTL]}>{label}</Text>
      </View>
      <View style={[styles.rowRight, isRTL && styles.rowRightRTL]}>
        {value ? <Text style={[styles.valueText, isRTL && styles.alignRTL]}>{value}</Text> : null}
        {showChevron && isPressable ? (
          <Ionicons
            name={isRTL ? 'chevron-back' : 'chevron-forward'}
            size={16}
            color={colors.textTertiary || colors.textMuted}
            style={styles.chevron}
          />
        ) : null}
      </View>
    </Wrapper>
  );
}

export default function SettingsScreen({ navigation }) {
  const [userEmail, setUserEmail] = useState('');
  const [signingOut, setSigningOut] = useState(false);
  const { profile, clearProfile } = useProfile();
  const { candidateState } = useRevenueCat();
  const { backendSubscription } = useSubscription();
  const { t } = useTranslation();
  const { locale, isRTL, setLocale } = useLocalization();
  const [languagePickerVisible, setLanguagePickerVisible] = useState(false);
  const [changingLanguage, setChangingLanguage] = useState(false);
  const [resettingPassword, setResettingPassword] = useState(false);
  const passwordResetInFlightRef = useRef(false);

  const accountType = profile?.preferences?.account_type
    ? normalizeAccountType(profile.preferences.account_type)
    : null;
  const isEmployer = accountType === 'employer';
  const subscriptionSnapshot = getSubscriptionSnapshot(
    profile?.preferences?.account_type,
    candidateState,
    backendSubscription
  );
  const currentPlanLabel = t(subscriptionSnapshot.currentPlan.badgeKey);

  useEffect(() => {
    let isMounted = true;
    getCurrentUser()
      .then(({ data }) => {
        if (isMounted && data?.user?.email) {
          setUserEmail(data.user.email);
        }
      })
      .catch((err) => {
        console.warn('Failed to fetch user email:', err);
      });
    return () => {
      isMounted = false;
    };
  }, []);

  const handleLanguageChange = async (nextLocale) => {
    if (changingLanguage || nextLocale === locale) {
      setLanguagePickerVisible(false);
      return;
    }

    setLanguagePickerVisible(false);
    setChangingLanguage(true);

    try {
      const changed = await setLocale(nextLocale);
      if (!changed) throw new Error('LANGUAGE_CHANGE_REJECTED');
      haptics.success();
    } catch (error) {
      console.warn('Language change failed:', error);
      Alert.alert(
        t('settings.languagePicker.changeFailedTitle'),
        t('settings.languagePicker.changeFailedMessage')
      );
    } finally {
      setChangingLanguage(false);
    }
  };

  const handlePasswordReset = async () => {
    if (resettingPassword) return;

    try {
      const email = userEmail.trim();
      if (!email) {
        Alert.alert(t('settings.password.noEmailTitle'), t('settings.password.noEmailMessage'));
        return;
      }

      Alert.alert(
        t('settings.password.confirmTitle'),
        t('settings.password.confirmMessage', { email }),
        [
          { text: t('common.cancel'), style: 'cancel' },
          {
            text: t('settings.password.sendLink'),
            onPress: async () => {
              if (passwordResetInFlightRef.current) return;
              passwordResetInFlightRef.current = true;
              setResettingPassword(true);
              try {
                const { error } = await sendPasswordResetEmail(email, PASSWORD_RESET_REDIRECT_URL);
                if (error) {
                  Alert.alert(t('settings.password.resetFailedTitle'), getLocalizedErrorMessage(error, t));
                } else {
                  haptics.success();
                  Alert.alert(
                    t('settings.password.resetSentTitle'),
                    t('settings.password.resetSentMessage', { email })
                  );
                }
              } catch (err) {
                const msg = getLocalizedErrorMessage(err, t);
                Alert.alert(t('common.error'), msg);
              } finally {
                passwordResetInFlightRef.current = false;
                setResettingPassword(false);
              }
            },
          },
        ]
      );
    } catch (err) {
      const msg = getLocalizedErrorMessage(err, t);
      Alert.alert(t('common.error'), msg);
    }
  };

  const handleSignOut = () => {
    Alert.alert(t('settings.signOutDialog.title'), t('settings.signOutDialog.message'), [
      { text: t('common.cancel'), style: 'cancel' },
      {
        text: t('settings.signOut'),
        style: 'destructive',
        onPress: async () => {
          if (signingOut) return;
          setSigningOut(true);
          try {
            const { error } = await signOut();
            if (error) {
              throw error;
            }
            clearProfile();
            haptics.success();
            navigation.reset({
              index: 0,
              routes: [{ name: 'SignIn' }],
            });
          } catch (error) {
            const message = getLocalizedErrorMessage(error, t);
            Alert.alert(t('settings.signOutDialog.failedTitle'), message);
          } finally {
            setSigningOut(false);
          }
        },
      },
    ]);
  };

  if (!profile) {
    return (
      <ScreenContainer edges={['top', 'bottom']}>
        <ScreenHeader
          title={t('settings.title')}
          showBack={true}
          navigation={navigation}
        />
        <View style={styles.profileLoadingContainer}>
          <ActivityIndicator
            size="large"
            color={colors.accent || colors.teal}
          />
        </View>
      </ScreenContainer>
    );
  }

  return (
    <ScreenContainer edges={['top', 'bottom']}>
      <ScreenHeader
        title={t('settings.title')}
        showBack={true}
        navigation={navigation}
      />

      <ScrollView
        style={styles.screen}
        contentContainerStyle={styles.content}
        showsVerticalScrollIndicator={false}
      >
        {/* Account Section */}
        <Text style={[styles.sectionHeader, isRTL && styles.textRTL]}>{t('settings.sections.account')}</Text>
        <GlassSurface variant="card" style={styles.glassCard}>
          <SettingsRow
            icon="school-outline"
            label={t('settings.accountType')}
            value={subscriptionSnapshot.accountType === 'employer' ? t('plans.badges.employer') : t('settings.accountTypeIntern')}
            showChevron={false}
          />
          <SettingsRow
            icon="sparkles-outline"
            label={t('settings.plansAndUpgrade')}
            value={currentPlanLabel}
            onPress={() => navigation.navigate('Plans')}
            accessibilityLabel={t('settings.accessibility.plansAndUpgrade')}
          />
          <SettingsRow
            icon="mail-outline"
            label={t('settings.emailAddress')}
            value={userEmail || t('settings.authenticated')}
            showChevron={false}
          />
          <SettingsRow
            flagLocale={locale}
            label={t('settings.language')}
            value={LANGUAGE_OPTIONS.find((option) => option.code === locale)?.label || LANGUAGE_OPTIONS[0].label}
            onPress={() => setLanguagePickerVisible(true)}
            accessibilityLabel={t('settings.accessibility.language')}
          />
          <SettingsRow
            icon="key-outline"
            label={t('settings.changePassword')}
            onPress={handlePasswordReset}
            isLast={true}
            accessibilityLabel={t('settings.accessibility.passwordReset')}
          />
        </GlassSurface>

        {/* Profile Section */}
        <Text style={[styles.sectionHeader, isRTL && styles.textRTL]}>
          {isEmployer ? t('settings.sections.profile') : t('settings.sections.profileCareer')}
        </Text>
        <GlassSurface variant="card" style={styles.glassCard}>
          <SettingsRow
            icon="person-outline"
            label={t('settings.editProfile')}
            onPress={() => navigation.navigate('EditProfile')}
            isLast={isEmployer}
            accessibilityLabel={t('settings.accessibility.editProfile')}
          />
          {!isEmployer && (
            <SettingsRow
              icon="document-text-outline"
              label={t('settings.manageCv')}
              onPress={() => navigation.navigate('CVUpload')}
              isLast={true}
              accessibilityLabel={t('settings.accessibility.manageCv')}
            />
          )}
        </GlassSurface>

        {/* Privacy & Legal Section */}
        <Text style={[styles.sectionHeader, isRTL && styles.textRTL]}>{t('settings.sections.privacyLegal')}</Text>
        <GlassSurface variant="card" style={styles.glassCard}>
          <SettingsRow
            icon="shield-checkmark-outline"
            label={t('settings.privacyPolicy')}
            onPress={() => navigation.navigate('PrivacyPolicy')}
            accessibilityLabel={t('settings.accessibility.privacyPolicy')}
          />
          <SettingsRow
            icon="document-outline"
            label={t('settings.termsOfUse')}
            onPress={() => navigation.navigate('TermsOfUse')}
            isLast={true}
            accessibilityLabel={t('settings.accessibility.termsOfUse')}
          />
        </GlassSurface>

        {/* About Section */}
        <Text style={[styles.sectionHeader, isRTL && styles.textRTL]}>{t('settings.sections.about')}</Text>
        <GlassSurface variant="card" style={styles.glassCard}>
          <SettingsRow
            icon="information-circle-outline"
            label="InternMatch AI"
            value={t('settings.productTagline')}
            showChevron={false}
          />
          <SettingsRow
            icon="code-slash-outline"
            label={t('settings.appVersion')}
            value={`v${appVersion}`}
            showChevron={false}
            isLast={true}
          />
        </GlassSurface>

        {/* Sign Out CTA */}
        <TouchableOpacity
          style={styles.signOutButton}
          onPress={handleSignOut}
          disabled={signingOut}
          accessibilityRole="button"
          accessibilityLabel={t('settings.accessibility.signOut')}
          activeOpacity={0.75}
        >
          <Ionicons
            name="log-out-outline"
            size={18}
            color={colors.danger || colors.red}
            style={styles.signOutIcon}
          />
          <Text style={[styles.signOutText, isRTL && styles.textRTL]}>
            {signingOut ? t('settings.signingOut') : t('settings.signOut')}
          </Text>
        </TouchableOpacity>
      </ScrollView>

      <Modal
        visible={languagePickerVisible}
        transparent={true}
        animationType="fade"
        onRequestClose={() => setLanguagePickerVisible(false)}
      >
        <View style={styles.languageModalBackdrop}>
          <GlassSurface variant="card" style={styles.languageSheet}>
            <Text style={[styles.languageTitle, isRTL && styles.textRTL]}>{t('settings.languagePicker.title')}</Text>
            <Text style={[styles.languageMessage, isRTL && styles.textRTL]}>{t('settings.languagePicker.message')}</Text>

            {LANGUAGE_OPTIONS.map((option) => {
              const selected = option.code === locale;
              const optionIsRTL = option.code === 'ar';

              return (
                <TouchableOpacity
                  key={option.code}
                  style={[styles.languageOption, selected && styles.languageOptionSelected]}
                  onPress={() => handleLanguageChange(option.code)}
                  disabled={changingLanguage}
                  accessibilityRole="radio"
                  accessibilityLabel={option.label}
                  accessibilityState={{ selected, disabled: changingLanguage }}
                  activeOpacity={0.72}
                >
                  <View style={styles.languageFlagCol}>
                    <LocaleFlag locale={option.code} width={26} height={18} />
                  </View>
                  <View style={styles.languageNameCol}>
                    <Text
                      style={[
                        styles.languageOptionText,
                        optionIsRTL ? { writingDirection: 'rtl' } : { writingDirection: 'ltr' },
                        selected && styles.languageOptionTextSelected,
                      ]}
                    >
                      {option.label}
                    </Text>
                  </View>
                  <View style={styles.languageCheckCol}>
                    {selected ? (
                      <Ionicons name="checkmark-circle" size={20} color={colors.accent || colors.teal} />
                    ) : null}
                  </View>
                </TouchableOpacity>
              );
            })}

            <TouchableOpacity
              style={styles.languageCancel}
              onPress={() => setLanguagePickerVisible(false)}
              disabled={changingLanguage}
              accessibilityRole="button"
              accessibilityLabel={t('common.cancel')}
              activeOpacity={0.72}
            >
              <Text style={[styles.languageCancelText, isRTL && styles.textRTL]}>{t('common.cancel')}</Text>
            </TouchableOpacity>
          </GlassSurface>
        </View>
      </Modal>
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: colors.background || colors.screenBg,
  },
  content: {
    paddingHorizontal: spacing.screenHorizontalPadding,
    paddingTop: spacing.xs,
    paddingBottom: spacing.xxxl,
  },
  sectionHeader: {
    ...typography.caption,
    fontWeight: '700',
    letterSpacing: 0.8,
    color: colors.textSecondary || colors.textMuted,
    marginTop: spacing.lg,
    marginBottom: spacing.xs,
    marginStart: spacing.xs,
  },
  glassCard: {
    borderRadius: spacing.radii.lg,
    overflow: 'hidden',
    marginBottom: spacing.xs,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.lg,
    minHeight: 52,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.borderSubtle || 'rgba(14, 116, 144, 0.12)',
  },
  rowLast: {
    borderBottomWidth: 0,
  },
  rowLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
    marginEnd: spacing.sm,
  },
  iconContainer: {
    width: 28,
    height: 28,
    borderRadius: 14,
    backgroundColor: 'rgba(14, 116, 144, 0.08)',
    alignItems: 'center',
    justifyContent: 'center',
    marginEnd: spacing.md,
  },
  flagIconContainer: {
    backgroundColor: 'transparent',
  },
  rowLabel: {
    ...typography.body,
    fontWeight: '500',
    color: colors.textPrimary || colors.textDark,
  },
  rowRight: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  valueText: {
    ...typography.caption,
    color: colors.textSecondary || colors.textMuted,
    fontWeight: '500',
    maxWidth: 180,
  },
  chevron: {
    marginStart: spacing.xs,
  },
  languageModalBackdrop: {
    flex: 1,
    justifyContent: 'center',
    paddingHorizontal: spacing.xl,
    backgroundColor: 'rgba(2, 8, 23, 0.46)',
  },
  languageSheet: {
    width: '100%',
    maxWidth: 420,
    alignSelf: 'center',
    padding: spacing.lg,
    borderRadius: spacing.radii.lg,
    overflow: 'hidden',
  },
  languageTitle: {
    ...typography.body,
    fontSize: 18,
    fontWeight: '700',
    color: colors.textPrimary || colors.textDark,
    marginBottom: spacing.xs,
  },
  languageMessage: {
    ...typography.caption,
    color: colors.textSecondary || colors.textMuted,
    marginBottom: spacing.md,
  },
  languageOption: {
    flexDirection: 'row',
    alignItems: 'center',
    minHeight: 50,
    paddingHorizontal: spacing.md,
    borderRadius: spacing.radii.md,
    borderWidth: 1,
    borderColor: colors.borderSubtle || 'rgba(14, 116, 144, 0.12)',
    marginBottom: spacing.sm,
    backgroundColor: 'rgba(255, 255, 255, 0.65)',
  },
  languageOptionSelected: {
    borderColor: colors.accent || colors.teal,
    backgroundColor: 'rgba(14, 116, 144, 0.10)',
  },
  languageFlagCol: {
    width: 36,
    alignItems: 'flex-start',
    justifyContent: 'center',
  },
  languageNameCol: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  languageCheckCol: {
    width: 36,
    alignItems: 'flex-end',
    justifyContent: 'center',
  },
  languageOptionText: {
    ...typography.bodyEmphasis,
    fontSize: 15,
    color: colors.textPrimary || colors.textDark,
    textAlign: 'center',
  },
  languageOptionTextSelected: {
    color: colors.accent || colors.teal,
    fontWeight: '700',
  },
  languageCancel: {
    minHeight: 44,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: spacing.xs,
  },
  languageCancelText: {
    ...typography.button,
    color: colors.textSecondary || colors.textMuted,
    fontWeight: '600',
  },
  rowRTL: {
    flexDirection: 'row-reverse',
  },
  rowLeftRTL: {
    flexDirection: 'row-reverse',
    marginEnd: 0,
    marginStart: spacing.sm,
  },
  rowRightRTL: {
    flexDirection: 'row-reverse',
  },
  iconContainerRTL: {
    marginEnd: 0,
    marginStart: spacing.md,
  },
  textRTL: {
    textAlign: 'right',
    writingDirection: 'rtl',
  },
  textLTR: {
    textAlign: 'left',
    writingDirection: 'ltr',
  },
  alignRTL: {
    textAlign: 'right',
  },
  signOutButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'rgba(239, 68, 68, 0.08)',
    borderWidth: 1,
    borderColor: 'rgba(239, 68, 68, 0.25)',
    borderRadius: spacing.radii.lg,
    paddingVertical: spacing.md,
    marginTop: spacing.xl,
    minHeight: 50,
  },
  signOutIcon: {
    marginEnd: spacing.xs,
  },
  signOutText: {
    ...typography.button,
    color: colors.danger || colors.red,
    fontWeight: '600',
  },
  profileLoadingContainer: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
