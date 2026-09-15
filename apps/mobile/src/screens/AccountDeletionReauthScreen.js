import React, { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import * as AppleAuthentication from 'expo-apple-authentication';
import { useTranslation } from 'react-i18next';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

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


export default function AccountDeletionReauthScreen({ navigation }) {
  const { t } = useTranslation();
  const insets = useSafeAreaInsets();
  const { clearProfile } = useProfile();

  const [originalUserId, setOriginalUserId] = useState(null);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loadingSource, setLoadingSource] = useState(null);

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
    if (busy || !originalUserId) return;

    if (!email || !password) {
      Alert.alert(
        t('settings.accountDeletionReauth.failedTitle'),
        t('settings.accountDeletionReauth.passwordRequired')
      );
      return;
    }

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
      setLoadingSource(null);
    }
  };

  const handleGoogleReauth = async () => {
    if (busy || !originalUserId) return;

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
      setLoadingSource(null);
    }
  };

  const handleAppleReauth = async () => {
    if (busy || !originalUserId) return;

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
      setLoadingSource(null);
    }
  };

  return (
    <View
      style={[
        styles.screen,
        {
          paddingTop: insets.top,
          paddingBottom: insets.bottom,
        },
      ]}
    >
      <ScrollView
        contentContainerStyle={styles.content}
        keyboardShouldPersistTaps="handled"
      >
        <TouchableOpacity
          style={styles.backButton}
          onPress={() => navigation.goBack()}
          disabled={busy}
          accessibilityRole="button"
        >
          <Text style={styles.backText}>
            {t('settings.accountDeletionReauth.back')}
          </Text>
        </TouchableOpacity>

        <Text style={styles.title}>
          {t('settings.accountDeletionReauth.title')}
        </Text>

        <Text style={styles.message}>
          {t('settings.accountDeletionReauth.message')}
        </Text>

        <Text style={styles.email}>
          {email}
        </Text>

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
          placeholderTextColor={colors.textSecondary || '#8A94A3'}
        />

        <TouchableOpacity
          style={styles.dangerButton}
          onPress={handlePasswordReauth}
          disabled={busy || !originalUserId}
          accessibilityRole="button"
        >
          {loadingSource === 'password' ? (
            <ActivityIndicator color="#FFFFFF" />
          ) : (
            <Text style={styles.dangerButtonText}>
              {t(
                'settings.accountDeletionReauth.passwordButton'
              )}
            </Text>
          )}
        </TouchableOpacity>

        <View style={styles.dividerRow}>
          <View style={styles.divider} />
          <Text style={styles.dividerText}>
            {t('auth.or')}
          </Text>
          <View style={styles.divider} />
        </View>

        <TouchableOpacity
          style={styles.providerButton}
          onPress={handleGoogleReauth}
          disabled={busy || !originalUserId}
          accessibilityRole="button"
        >
          {loadingSource === 'google' ? (
            <ActivityIndicator />
          ) : (
            <Text style={styles.providerButtonText}>
              {t(
                'settings.accountDeletionReauth.googleButton'
              )}
            </Text>
          )}
        </TouchableOpacity>

        {Platform.OS === 'ios' && (
          <View style={styles.appleWrapper}>
            {loadingSource === 'apple' ? (
              <ActivityIndicator />
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
                cornerRadius={10}
                style={styles.appleButton}
                onPress={handleAppleReauth}
              />
            )}
          </View>
        )}

        {busy && (
          <Text style={styles.loadingText}>
            {t(
              'settings.accountDeletionReauth.loading'
            )}
          </Text>
        )}
      </ScrollView>
    </View>
  );
}


const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: colors.background || '#0B1020',
  },
  content: {
    flexGrow: 1,
    padding: spacing.lg || 24,
    justifyContent: 'center',
  },
  backButton: {
    alignSelf: 'flex-start',
    marginBottom: spacing.xl || 28,
    paddingVertical: 8,
  },
  backText: {
    color: colors.textSecondary || '#A8B0C0',
    ...typography.body,
  },
  title: {
    color: colors.textPrimary || '#FFFFFF',
    ...typography.h1,
    marginBottom: spacing.md || 16,
  },
  message: {
    color: colors.textSecondary || '#A8B0C0',
    ...typography.body,
    lineHeight: 22,
    marginBottom: spacing.lg || 24,
  },
  email: {
    color: colors.textPrimary || '#FFFFFF',
    ...typography.body,
    marginBottom: spacing.sm || 12,
  },
  input: {
    minHeight: 52,
    borderWidth: 1,
    borderColor: colors.border || '#2B3448',
    borderRadius: 12,
    paddingHorizontal: 16,
    color: colors.textPrimary || '#FFFFFF',
    backgroundColor: colors.surface || '#141B2D',
    marginBottom: spacing.md || 16,
  },
  dangerButton: {
    minHeight: 52,
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.danger || '#D92D20',
    paddingHorizontal: 16,
  },
  dangerButtonText: {
    color: '#FFFFFF',
    ...typography.button,
  },
  dividerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginVertical: spacing.lg || 24,
  },
  divider: {
    flex: 1,
    height: StyleSheet.hairlineWidth,
    backgroundColor: colors.border || '#2B3448',
  },
  dividerText: {
    marginHorizontal: 12,
    color: colors.textSecondary || '#A8B0C0',
  },
  providerButton: {
    minHeight: 52,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: colors.border || '#2B3448',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.surface || '#141B2D',
  },
  providerButtonText: {
    color: colors.textPrimary || '#FFFFFF',
    ...typography.button,
  },
  appleWrapper: {
    minHeight: 52,
    marginTop: 12,
    justifyContent: 'center',
  },
  appleButton: {
    width: '100%',
    height: 52,
  },
  loadingText: {
    marginTop: 16,
    textAlign: 'center',
    color: colors.textSecondary || '#A8B0C0',
  },
});
