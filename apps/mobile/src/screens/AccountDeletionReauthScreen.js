import React, { useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import * as AppleAuthentication from 'expo-apple-authentication';
import { useTranslation } from 'react-i18next';
import { Ionicons } from '@expo/vector-icons';

import { useProfile } from '../context/ProfileContext';
import { signInWithApple } from '../services/appleAuth';
import {
  clearLocalSessionAfterAccountDeletion,
  getCurrentUser,
  signInWithEmail,
  signOut,
} from '../services/auth';
import { deleteAccount } from '../services/api';
import { signInWithGoogle } from '../services/googleAuth';
import haptics from '../services/haptics';
import colors from '../theme/colors';
import { spacing } from '../theme/spacing';
import { typography } from '../theme/typography';
import ScreenContainer from '../components/ScreenContainer';
import ScreenHeader from '../components/ScreenHeader';
import Card from '../components/Card';
import GradientButton from '../components/GradientButton';
import { useLocalization } from '../localization/LocalizationContext';


export default function AccountDeletionReauthScreen({ navigation }) {
  const { t } = useTranslation();
  const { isRTL } = useLocalization();
  const { clearProfile } = useProfile();

  const [originalUserId, setOriginalUserId] = useState(null);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loadingSource, setLoadingSource] = useState(null);
  const reauthInFlightRef = useRef(false);

  const busy = Boolean(loadingSource);

  useEffect(() => {
    let active = true;

    getCurrentUser()
      .then(({ data, error }) => {
        if (!active) return;

        if (error || !data?.user?.id) {
          navigation.reset({
            index: 0,
            routes: [{ name: 'SignIn' }],
          });
          return;
        }

        setOriginalUserId(data.user.id);
        setEmail(data.user.email || '');
      })
      .catch(() => {
        if (!active) return;

        navigation.reset({
          index: 0,
          routes: [{ name: 'SignIn' }],
        });
      });

    return () => {
      active = false;
    };
  }, [navigation]);

  const handleIdentityMismatch = async () => {
    try {
      await signOut();
    } catch (_) {}

    clearProfile();
    haptics.error();

    Alert.alert(
      t('settings.accountDeletionReauth.mismatchTitle'),
      t('settings.accountDeletionReauth.mismatchMessage'),
      [
        {
          text: t('common.ok'),
          onPress: () => {
            navigation.reset({
              index: 0,
              routes: [{ name: 'SignIn' }],
            });
          },
        },
      ]
    );
  };

  const completeDeletion = async (
    session,
    appleAuthorizationCode = null
  ) => {
    const verifiedUserId = session?.user?.id || null;

    if (
      !originalUserId ||
      !verifiedUserId ||
      verifiedUserId !== originalUserId
    ) {
      await handleIdentityMismatch();
      return;
    }

    await deleteAccount(
      appleAuthorizationCode
    );
    await clearLocalSessionAfterAccountDeletion();

    clearProfile();
    haptics.success();

    navigation.reset({
      index: 0,
      routes: [{ name: 'SignIn' }],
    });
  };

  const handlePasswordReauth = async () => {
    if (reauthInFlightRef.current || busy || !originalUserId) return;

    if (!email || !password) {
      Alert.alert(
        t('settings.accountDeletionReauth.failedTitle'),
        t('settings.accountDeletionReauth.passwordRequired')
      );
      return;
    }

    reauthInFlightRef.current = true;
    setLoadingSource('password');

    try {
      const { data, error } = await signInWithEmail(
        email,
        password
      );

      if (error || !data?.session) {
        throw error || new Error('Missing reauthenticated session.');
      }

      await completeDeletion(data.session);
    } catch (_) {
      haptics.error();

      Alert.alert(
        t('settings.accountDeletionReauth.failedTitle'),
        t('settings.accountDeletionReauth.failedMessage')
      );
    } finally {
      reauthInFlightRef.current = false;
      setLoadingSource(null);
    }
  };

  const handleGoogleReauth = async () => {
    if (reauthInFlightRef.current || busy || !originalUserId) return;

    reauthInFlightRef.current = true;
    setLoadingSource('google');

    try {
      const result = await signInWithGoogle();

      if (result?.cancelled) {
        return;
      }

      if (!result?.session) {
        throw new Error('Missing Google reauthentication session.');
      }

      await completeDeletion(result.session);
    } catch (_) {
      haptics.error();

      Alert.alert(
        t('settings.accountDeletionReauth.failedTitle'),
        t('settings.accountDeletionReauth.failedMessage')
      );
    } finally {
      reauthInFlightRef.current = false;
      setLoadingSource(null);
    }
  };

  const handleAppleReauth = async () => {
    if (reauthInFlightRef.current || busy || !originalUserId) return;

    reauthInFlightRef.current = true;
    setLoadingSource('apple');

    try {
      const result = await signInWithApple();

      if (result?.cancelled) {
        return;
      }

      if (
        result?.unavailable ||
        !result?.session ||
        !result?.authorizationCode
      ) {
        throw new Error(
          'Apple reauthentication did not return '
          + 'an authorization code.'
        );
      }

      await completeDeletion(
        result.session,
        result.authorizationCode
      );
    } catch (_) {
      haptics.error();

      Alert.alert(
        t('settings.accountDeletionReauth.failedTitle'),
        t('settings.accountDeletionReauth.failedMessage')
      );
    } finally {
      reauthInFlightRef.current = false;
      setLoadingSource(null);
    }
  };

  return (
    <ScreenContainer edges={['top', 'bottom']}>
      <ScreenHeader
        title={t('settings.accountDeletionReauth.title')}
        showBack
        navigation={navigation}
      />

      <ScrollView
        style={styles.screen}
        contentContainerStyle={styles.content}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        <Card style={styles.identityCard} padding="lg">
          <View style={styles.warningIcon}>
            <Ionicons
              name="shield-checkmark-outline"
              size={26}
              color={colors.danger || colors.red}
            />
          </View>

          <Text style={[styles.message, isRTL && styles.textRTL]}>
            {t('settings.accountDeletionReauth.message')}
          </Text>

          <View style={styles.emailPill}>
            <Ionicons
              name="mail-outline"
              size={16}
              color={colors.textSecondary || colors.textMuted}
            />

            <Text
              style={styles.email}
              numberOfLines={1}
              ellipsizeMode="middle"
            >
              {email}
            </Text>
          </View>

          <TextInput
            style={styles.input}
            value={password}
            onChangeText={setPassword}
            secureTextEntry
            autoCapitalize="none"
            autoCorrect={false}
            editable={!busy}
            placeholder={t(
              'settings.accountDeletionReauth.passwordPlaceholder'
            )}
            placeholderTextColor={
              colors.textTertiary || colors.textMuted
            }
          />

          <GradientButton
            title={t(
              'settings.accountDeletionReauth.passwordButton'
            )}
            color={colors.danger || colors.red}
            onPress={handlePasswordReauth}
            disabled={busy || !originalUserId}
            loading={loadingSource === 'password'}
          />

          <View style={styles.dividerRow}>
            <View style={styles.divider} />

            <Text style={styles.dividerText}>
              {t('auth.or')}
            </Text>

            <View style={styles.divider} />
          </View>

          <GradientButton
            title={t(
              'settings.accountDeletionReauth.googleButton'
            )}
            color={colors.accent || colors.teal}
            outline
            onPress={handleGoogleReauth}
            disabled={busy || !originalUserId}
            loading={loadingSource === 'google'}
          />

          {Platform.OS === 'ios' && (
            <View style={styles.appleWrapper}>
              {loadingSource === 'apple' ? (
                <ActivityIndicator
                  color={colors.accent || colors.teal}
                />
              ) : (
                <AppleAuthentication.AppleAuthenticationButton
                  buttonType={
                    AppleAuthentication
                      .AppleAuthenticationButtonType
                      .SIGN_IN
                  }
                  buttonStyle={
                    AppleAuthentication
                      .AppleAuthenticationButtonStyle
                      .BLACK
                  }
                  cornerRadius={24}
                  style={styles.appleButton}
                  onPress={handleAppleReauth}
                />
              )}
            </View>
          )}

          {busy && (
            <Text
              style={[
                styles.loadingText,
                isRTL && styles.textRTL,
              ]}
            >
              {t('settings.accountDeletionReauth.loading')}
            </Text>
          )}
        </Card>
      </ScrollView>
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: colors.background || colors.screenBg,
  },

  content: {
    flexGrow: 1,
    paddingHorizontal: spacing.screenHorizontalPadding,
    paddingTop: spacing.md,
    paddingBottom: spacing.xxxl,
    justifyContent: 'center',
  },

  identityCard: {
    width: '100%',
    maxWidth: 560,
    alignSelf: 'center',
  },

  warningIcon: {
    width: 52,
    height: 52,
    borderRadius: 26,
    alignSelf: 'center',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.dangerSoft || colors.redBg,
    marginBottom: spacing.lg,
  },

  message: {
    ...typography.body,
    color: colors.textSecondary || colors.textMuted,
    textAlign: 'center',
    marginBottom: spacing.lg,
  },

  emailPill: {
    minHeight: spacing.minimumTouchTarget,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingHorizontal: spacing.md,
    borderRadius: spacing.radii.md,
    borderWidth: 1,
    borderColor: colors.borderSubtle || colors.border,
    backgroundColor: colors.surfaceSubtle,
    marginBottom: spacing.sm,
  },

  email: {
    ...typography.bodyEmphasis,
    color: colors.textPrimary || colors.textDark,
    flex: 1,
    writingDirection: 'ltr',
    textAlign: 'left',
  },

  input: {
    minHeight: 48,
    borderWidth: 1,
    borderColor: colors.borderSubtle || colors.border,
    borderRadius: spacing.radii.md,
    paddingHorizontal: spacing.md,
    color: colors.textPrimary || colors.textDark,
    backgroundColor: colors.surface || colors.cardBg,
    ...typography.body,
    marginBottom: spacing.md,
  },

  dividerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginVertical: spacing.lg,
  },

  divider: {
    flex: 1,
    height: StyleSheet.hairlineWidth,
    backgroundColor: colors.borderSubtle || colors.border,
  },

  dividerText: {
    ...typography.caption,
    marginHorizontal: spacing.md,
    color: colors.textSecondary || colors.textMuted,
  },

  appleWrapper: {
    minHeight: 48,
    marginTop: spacing.md,
    justifyContent: 'center',
  },

  appleButton: {
    width: '100%',
    height: 48,
  },

  loadingText: {
    ...typography.caption,
    marginTop: spacing.md,
    textAlign: 'center',
    color: colors.textSecondary || colors.textMuted,
  },

  textRTL: {
    textAlign: 'right',
    writingDirection: 'rtl',
  },
});
