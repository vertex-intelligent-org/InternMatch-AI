import React, { useCallback, useRef } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  RefreshControl,
  ActivityIndicator,
  Image,
  Linking,
  Alert,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTranslation } from 'react-i18next';
import { useScrollToTop } from '@react-navigation/native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import colors from '../theme/colors';
import { spacing } from '../theme/spacing';
import { typography } from '../theme/typography';
import ScreenContainer from '../components/ScreenContainer';
import ScreenHeader from '../components/ScreenHeader';
import AuthenticatedAppChromeHeader from '../components/AuthenticatedAppChromeHeader';
import GlassSurface from '../components/GlassSurface';
import Card from '../components/Card';
import Chip from '../components/Chip';
import GradientButton from '../components/GradientButton';
import { useProfile } from '../context/ProfileContext';
import { useSavedInternships } from '../context/SavedInternshipsContext';
import { useTabScroll, useTabScrollReporter } from '../context/TabScrollContext';
import { useLocalization } from '../localization/LocalizationContext';
import { normalizeAccountType } from '../services/subscriptionService';
import { getTabScreenBottomPadding } from '../theme/tabBarLayout';
import { calculateProfileCompleteness } from '../utils/profileCompleteness';

const appVersion = require('../../app.json').expo.version || '1.0.0';

function getInitials(name) {
  if (!name || typeof name !== 'string') return '';
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return '';
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

export default function ProfileScreen({ navigation }) {
  const { t } = useTranslation();
  const { isRTL } = useLocalization();
  const insets = useSafeAreaInsets();
  const scrollViewRef = useRef(null);
  useTabScroll('Profile', scrollViewRef);
  useScrollToTop(scrollViewRef);
  const onScroll = useTabScrollReporter(20);

  const { profile, loading, refreshProfile } = useProfile();
  const { savedIds } = useSavedInternships();

  const accountType = profile?.preferences?.account_type
    ? normalizeAccountType(profile.preferences.account_type)
    : null;
  const isEmployer = accountType === 'employer';

  const bottomPadding = getTabScreenBottomPadding(insets.bottom);

  // Cache-first profile UX:
  // show the shared ProfileContext snapshot immediately on tab entry.
  // Fresh data remains available through explicit pull-to-refresh and
  // through profile mutations that refresh the shared context.

  const skills = profile?.skills || [];
  const initials = getInitials(profile?.full_name);
  const completeness = calculateProfileCompleteness(profile);

  const linkedinUrl =
    typeof profile?.preferences?.linkedin_url === 'string'
      ? profile.preferences.linkedin_url
      : null;
  const githubUrl =
    typeof profile?.preferences?.github_url === 'string'
      ? profile.preferences.github_url
      : null;
  const portfolioUrl =
    typeof profile?.preferences?.portfolio_url === 'string'
      ? profile.preferences.portfolio_url
      : null;
  const hasAnyLinks = Boolean(linkedinUrl || githubUrl || portfolioUrl);

  const handleOpenLink = async (url, title) => {
    if (!url) return;
    try {
      const supported = await Linking.canOpenURL(url);
      if (supported) {
        await Linking.openURL(url);
      } else {
        Alert.alert(t('profile.linkError'), t('profile.unableOpenLink', { title }));
      }
    } catch {
      Alert.alert(t('profile.linkError'), t('profile.linkError'));
    }
  };

  // Derive primary education summary if available
  const primaryEducation =
    !isEmployer && profile?.education && profile.education.length > 0
      ? `${profile.education[0].degree} - ${profile.education[0].institution}`
      : null;

  const renderSettingsAction = () => (
    <TouchableOpacity
      style={styles.settingsBtn}
      onPress={() => navigation.navigate('Settings')}
      accessibilityRole="button"
      accessibilityLabel={t('navigation.settings')}
      hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
    >
      <Ionicons
        name="settings-outline"
        size={22}
        color={colors.textPrimary || colors.textDark}
      />
    </TouchableOpacity>
  );

  return (
    <ScreenContainer edges={['top']}>
      {/* Authenticated App Chrome Header with canonical plan badge & settings action */}
      <AuthenticatedAppChromeHeader
        rightAction={renderSettingsAction()}
      />

      <ScrollView
        ref={scrollViewRef}
        style={styles.screen}
        contentContainerStyle={[styles.content, { paddingBottom: bottomPadding }]}
        showsVerticalScrollIndicator={false}
        onScroll={onScroll}
        scrollEventThrottle={16}
        refreshControl={
          <RefreshControl
            refreshing={loading}
            onRefresh={refreshProfile}
            tintColor={colors.accent || colors.teal}
          />
        }
      >
        <View style={styles.avatarWrap}>
          <View style={styles.avatarPlaceholder}>
            {profile?.avatar_url ? (
              <Image source={{ uri: profile.avatar_url }} style={styles.avatarImage} />
            ) : initials ? (
              <Text style={styles.avatarInitials}>{initials}</Text>
            ) : (
              <Ionicons
                name="person-outline"
                size={36}
                color={colors.textSecondary || colors.textMuted}
              />
            )}
          </View>
        </View>

        {!profile ? (
          <View style={styles.loadingWrap}>
            <ActivityIndicator size="large" color={colors.accent || colors.teal} />
            <Text style={styles.loadingText}>{t('profile.loading')}</Text>
          </View>
        ) : (
          <>
            <Text style={styles.name} numberOfLines={2}>
              {profile.full_name}
            </Text>
            {profile.headline ? (
              <Text style={styles.subtitle}>{profile.headline}</Text>
            ) : null}
            {!isEmployer && primaryEducation ? (
              <Text style={styles.subtitle}>{primaryEducation}</Text>
            ) : null}

            {isEmployer ? (
              /* Employer Preview Disclosure Card */
              <GlassSurface variant="card" style={styles.employerNoticeCard}>
                <View style={[styles.employerNoticeHeader, isRTL && styles.rowRTL]}>
                  <Ionicons
                    name="briefcase-outline"
                    size={20}
                    color={colors.accentStrong || colors.tealDark}
                    style={isRTL ? styles.iconRTL : styles.iconLTR}
                  />
                  <Text style={[styles.employerNoticeBadge, isRTL && styles.textRTL]}>
                    {t('profile.employer.workspaceBadge')}
                  </Text>
                </View>
                <Text style={[styles.employerNoticeText, isRTL && styles.textRTL]}>
                  {t('profile.employer.workspaceNotice')}
                </Text>
                <GradientButton
                  title={t('profile.employer.viewPlans')}
                  color={colors.accent || colors.teal}
                  onPress={() => navigation.navigate('Plans')}
                  style={{ marginTop: spacing.md, width: '100%' }}
                />
              </GlassSurface>
            ) : (
              <>
                {/* Profile Completeness Card */}
                <GlassSurface variant="card" style={styles.completenessCard}>
                  <View style={styles.completenessHeader}>
                    <View style={styles.completenessTitleRow}>
                      <Ionicons
                        name={completeness.isComplete ? 'shield-checkmark' : 'sparkles'}
                        size={16}
                        color={completeness.isComplete ? colors.green || '#10B981' : colors.accent || colors.teal}
                        style={{ marginEnd: spacing.xs }}
                      />
                      <Text style={styles.completenessTitle}>
                        {completeness.isComplete
                          ? t('profile.completenessComplete')
                          : t('profile.completenessPercent', { percentage: completeness.percentage })}
                      </Text>
                    </View>
                    <Text style={styles.completenessCount}>
                      {completeness.completedCount}/{completeness.totalCount}
                    </Text>
                  </View>

                  <View style={styles.progressBarBg}>
                    <View
                      style={[
                        styles.progressBarFill,
                        {
                          width: `${completeness.percentage}%`,
                          backgroundColor: completeness.isComplete
                            ? colors.green || '#10B981'
                            : colors.accentStrong || colors.tealDark,
                        },
                      ]}
                    />
                  </View>

                  {!completeness.isComplete && completeness.firstMissingItem ? (
                    <TouchableOpacity
                      style={styles.completenessCtaRow}
                      onPress={() => navigation.navigate(completeness.firstMissingItem.route)}
                      accessibilityRole="button"
                      accessibilityLabel={t('profile.completenessImproveMatching', { label: completeness.firstMissingItem.label })}
                      activeOpacity={0.7}
                    >
                      <Text style={styles.completenessCtaText} numberOfLines={1}>
                        {t('profile.completenessImproveMatching', { label: completeness.firstMissingItem.label })}
                      </Text>
                      <Ionicons
                        name={isRTL ? "chevron-back" : "chevron-forward"}
                        size={14}
                        color={colors.accentStrong || colors.tealDark}
                      />
                    </TouchableOpacity>
                  ) : (
                    <View style={styles.completenessCompleteRow}>
                      <Text style={styles.completenessCompleteText}>
                        {t('profile.completenessReady')}
                      </Text>
                    </View>
                  )}
                </GlassSurface>

                {/* Skills Section */}
                <Text style={styles.sectionTitle}>{t('profile.skillsTitle')}</Text>
                {skills.length > 0 ? (
                  <View style={styles.chipRow}>
                    {skills.map((s) => (
                      <Chip key={s} label={s} variant="skill" />
                    ))}
                  </View>
                ) : (
                  <Card style={styles.linkCard} padding="sm">
                    <TouchableOpacity
                      style={styles.linkRow}
                      onPress={() => navigation.navigate('EditProfile')}
                      accessibilityRole="button"
                      accessibilityLabel={t('profile.addSkills')}
                    >
                      <View style={styles.linkRowLeft}>
                        <Ionicons
                          name="add-circle-outline"
                          size={18}
                          color={colors.accent || colors.teal}
                          style={styles.linkIcon}
                        />
                        <Text style={styles.addLinksText}>{t('profile.addSkills')}</Text>
                      </View>
                      <Ionicons
                        name={isRTL ? "chevron-back" : "chevron-forward"}
                        size={16}
                        color={colors.textTertiary || colors.textMuted}
                      />
                    </TouchableOpacity>
                  </Card>
                )}
              </>
            )}

            {/* Functional Social & Portfolio Links */}
            {(isEmployer ? hasAnyLinks : true) && (
              <>
                <Text style={styles.sectionTitle}>{t('profile.linksTitle')}</Text>
                <Card style={styles.linkCard} padding="sm">
                  {hasAnyLinks ? (
                    <>
                      {linkedinUrl ? (
                        <TouchableOpacity
                          style={styles.linkRow}
                          onPress={() => handleOpenLink(linkedinUrl, 'LinkedIn')}
                          accessibilityRole="link"
                          accessibilityLabel="LinkedIn"
                        >
                          <View style={styles.linkRowLeft}>
                            <Ionicons
                              name="logo-linkedin"
                              size={18}
                              color={colors.accent || colors.teal}
                              style={styles.linkIcon}
                            />
                            <Text style={styles.linkText}>LinkedIn</Text>
                          </View>
                          <Ionicons
                            name="open-outline"
                            size={16}
                            color={colors.textTertiary || colors.textMuted}
                          />
                        </TouchableOpacity>
                      ) : null}

                      {githubUrl ? (
                        <TouchableOpacity
                          style={[styles.linkRow, linkedinUrl ? styles.linkRowBorder : null]}
                          onPress={() => handleOpenLink(githubUrl, 'GitHub')}
                          accessibilityRole="link"
                          accessibilityLabel="GitHub"
                        >
                          <View style={styles.linkRowLeft}>
                            <Ionicons
                              name="logo-github"
                              size={18}
                              color={colors.accent || colors.teal}
                              style={styles.linkIcon}
                            />
                            <Text style={styles.linkText}>GitHub</Text>
                          </View>
                          <Ionicons
                            name="open-outline"
                            size={16}
                            color={colors.textTertiary || colors.textMuted}
                          />
                        </TouchableOpacity>
                      ) : null}

                      {portfolioUrl ? (
                        <TouchableOpacity
                          style={[
                            styles.linkRow,
                            linkedinUrl || githubUrl ? styles.linkRowBorder : null,
                          ]}
                          onPress={() => handleOpenLink(portfolioUrl, 'Portfolio')}
                          accessibilityRole="link"
                          accessibilityLabel="Portfolio"
                        >
                          <View style={styles.linkRowLeft}>
                            <Ionicons
                              name="globe-outline"
                              size={18}
                              color={colors.accent || colors.teal}
                              style={styles.linkIcon}
                            />
                            <Text style={styles.linkText}>Portfolio</Text>
                          </View>
                          <Ionicons
                            name="open-outline"
                            size={16}
                            color={colors.textTertiary || colors.textMuted}
                          />
                        </TouchableOpacity>
                      ) : null}
                    </>
                  ) : !isEmployer ? (
                    <TouchableOpacity
                      style={styles.linkRow}
                      onPress={() => navigation.navigate('EditProfile')}
                      accessibilityRole="button"
                      accessibilityLabel={t('profile.addLinks')}
                    >
                      <View style={styles.linkRowLeft}>
                        <Ionicons
                          name="add-circle-outline"
                          size={18}
                          color={colors.accent || colors.teal}
                          style={styles.linkIcon}
                        />
                        <Text style={styles.addLinksText}>{t('profile.addLinks')}</Text>
                      </View>
                      <Ionicons
                        name={isRTL ? "chevron-back" : "chevron-forward"}
                        size={16}
                        color={colors.textTertiary || colors.textMuted}
                      />
                    </TouchableOpacity>
                  ) : null}
                </Card>
              </>
            )}

            {!isEmployer && (
              <>
                <View style={styles.buttonRow}>
                  <GradientButton
                    title={t('profile.editProfile')}
                    color={colors.accent || colors.teal}
                    onPress={() => navigation.navigate('EditProfile')}
                    style={styles.actionBtn}
                  />
                  <GradientButton
                    title={t('profile.uploadCV')}
                    color={colors.primary || colors.blue}
                    onPress={() => navigation.navigate('CVUpload')}
                    style={styles.actionBtn}
                  />
                </View>

                {/* Bookmarks Section */}
                <Text style={styles.sectionTitle}>{t('profile.bookmarksTitle')}</Text>
                <Card style={styles.linkCard} padding="sm">
                  <TouchableOpacity
                    style={styles.legalRow}
                    onPress={() => navigation.navigate('SavedInternships')}
                    accessibilityRole="button"
                    accessibilityLabel={`${t('profile.savedInternships')}, ${savedIds.size}`}
                  >
                    <View style={styles.legalRowLeft}>
                      <Ionicons
                        name="bookmark-outline"
                        size={18}
                        color={colors.accent || colors.teal}
                        style={styles.linkIcon}
                      />
                      <Text style={styles.linkText}>{t('profile.savedInternships')}</Text>
                    </View>
                    <View style={styles.badgeRowRight}>
                      {savedIds.size > 0 ? (
                        <View style={styles.savedBadgePill}>
                          <Text style={styles.savedBadgeText}>{savedIds.size}</Text>
                        </View>
                      ) : null}
                      <Ionicons
                        name={isRTL ? "chevron-back" : "chevron-forward"}
                        size={16}
                        color={colors.textTertiary || colors.textMuted}
                      />
                    </View>
                  </TouchableOpacity>
                </Card>
              </>
            )}

            {/* Legal & About Section */}
            <Text style={styles.sectionTitle}>{t('profile.legalTitle')}</Text>
            <Card style={styles.linkCard} padding="sm">
              <TouchableOpacity
                style={styles.legalRow}
                onPress={() => navigation.navigate('PrivacyPolicy')}
                accessibilityRole="button"
                accessibilityLabel={t('profile.privacyPolicy')}
              >
                <View style={styles.legalRowLeft}>
                  <Ionicons
                    name="shield-checkmark-outline"
                    size={18}
                    color={colors.accent || colors.teal}
                    style={styles.linkIcon}
                  />
                  <Text style={styles.linkText}>{t('profile.privacyPolicy')}</Text>
                </View>
                <Ionicons
                  name={isRTL ? "chevron-back" : "chevron-forward"}
                  size={16}
                  color={colors.textTertiary || colors.textMuted}
                />
              </TouchableOpacity>

              <TouchableOpacity
                style={[styles.legalRow, styles.linkRowBorder]}
                onPress={() => navigation.navigate('TermsOfUse')}
                accessibilityRole="button"
                accessibilityLabel={t('profile.termsOfUse')}
              >
                <View style={styles.legalRowLeft}>
                  <Ionicons
                    name="document-text-outline"
                    size={18}
                    color={colors.accent || colors.teal}
                    style={styles.linkIcon}
                  />
                  <Text style={styles.linkText}>{t('profile.termsOfUse')}</Text>
                </View>
                <Ionicons
                  name={isRTL ? "chevron-back" : "chevron-forward"}
                  size={16}
                  color={colors.textTertiary || colors.textMuted}
                />
              </TouchableOpacity>

              <View style={[styles.legalRow, styles.linkRowBorder]}>
                <View style={styles.legalRowLeft}>
                  <Ionicons
                    name="information-circle-outline"
                    size={18}
                    color={colors.textSecondary || colors.textMuted}
                    style={styles.linkIcon}
                  />
                  <Text style={styles.linkText}>{t('profile.appVersion')}</Text>
                </View>
                <Text style={styles.versionText}>{appVersion}</Text>
              </View>
            </Card>
          </>
        )}
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
    paddingHorizontal: spacing.screenHorizontalPadding,
    paddingTop: spacing.xs,
    paddingBottom: 128,
  },
  settingsBtn: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: 'rgba(14, 116, 144, 0.08)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  avatarWrap: {
    alignItems: 'center',
    marginTop: spacing.md,
  },
  avatarPlaceholder: {
    width: 84,
    height: 84,
    borderRadius: 42,
    borderWidth: 2,
    borderColor: colors.accent || colors.teal,
    backgroundColor: colors.surface || colors.cardBg,
    alignItems: 'center',
    justifyContent: 'center',
    overflow: 'hidden',
    shadowColor: 'rgba(14, 116, 144, 0.15)',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 1,
    shadowRadius: 4,
    elevation: 2,
  },
  avatarImage: {
    width: 80,
    height: 80,
    borderRadius: 40,
  },
  avatarInitials: {
    ...typography.display,
    fontSize: 26,
    fontWeight: '700',
    color: colors.accentStrong || colors.tealDark,
  },
  name: {
    ...typography.cardTitle,
    fontSize: 18,
    textAlign: 'center',
    marginTop: spacing.md,
    color: colors.textPrimary || colors.textDark,
  },
  subtitle: {
    ...typography.caption,
    color: colors.textSecondary || colors.textMuted,
    textAlign: 'center',
    marginTop: spacing.xxs,
    lineHeight: 18,
  },
  completenessCard: {
    marginTop: spacing.lg,
    padding: spacing.md,
    borderRadius: spacing.radii.lg,
  },
  completenessHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: spacing.xs,
  },
  completenessTitleRow: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  completenessTitle: {
    ...typography.body,
    fontWeight: '600',
    color: colors.textPrimary || colors.textDark,
  },
  completenessCount: {
    ...typography.caption,
    fontWeight: '600',
    color: colors.textSecondary || colors.textMuted,
  },
  progressBarBg: {
    height: 6,
    borderRadius: 3,
    backgroundColor: 'rgba(14, 116, 144, 0.12)',
    overflow: 'hidden',
    marginVertical: spacing.xs,
  },
  progressBarFill: {
    height: '100%',
    borderRadius: 3,
  },
  completenessCtaRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginTop: spacing.xs,
    paddingVertical: spacing.xxs,
  },
  completenessCtaText: {
    ...typography.caption,
    fontWeight: '600',
    color: colors.accentStrong || colors.tealDark,
    flex: 1,
    marginEnd: spacing.xs,
  },
  completenessCompleteRow: {
    marginTop: spacing.xxs,
  },
  completenessCompleteText: {
    ...typography.caption,
    color: colors.textSecondary || colors.textMuted,
    fontWeight: '500',
  },
  sectionTitle: {
    ...typography.sectionTitle,
    color: colors.textPrimary || colors.textDark,
    marginTop: spacing.xl,
    marginBottom: spacing.sm,
  },
  chipRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
  },
  linkCard: {
    marginTop: spacing.xs,
  },
  linkRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: spacing.sm,
    minHeight: 44,
  },
  linkRowBorder: {
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.borderSubtle || colors.border,
  },
  linkRowLeft: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  linkIcon: {
    marginEnd: spacing.sm,
  },
  linkText: {
    ...typography.body,
    color: colors.textPrimary || colors.textDark,
  },
  addLinksText: {
    ...typography.body,
    color: colors.accentStrong || colors.tealDark,
    fontWeight: '500',
  },
  legalRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: spacing.sm,
    minHeight: 44,
  },
  legalRowLeft: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  badgeRowRight: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  savedBadgePill: {
    backgroundColor: colors.accentSoft || '#E6F4F6',
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xxs,
    borderRadius: spacing.radiusSm || 8,
    marginEnd: spacing.xs,
  },
  savedBadgeText: {
    ...typography.caption,
    color: colors.accentStrong || colors.tealDark,
    fontWeight: '700',
    fontSize: 11,
  },
  versionText: {
    ...typography.caption,
    color: colors.textTertiary || colors.textMuted,
    fontWeight: '500',
  },
  buttonRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: spacing.xl,
    marginBottom: spacing.md,
  },
  actionBtn: {
    flex: 1,
    marginHorizontal: spacing.xxs,
  },
  loadingWrap: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: spacing.xxxl,
  },
  loadingText: {
    ...typography.body,
    color: colors.textSecondary || colors.textMuted,
    marginTop: spacing.sm,
  },
  emptyWrap: {
    marginTop: spacing.xxl,
    alignItems: 'center',
    textAlign: 'center',
  },
  employerNoticeCard: {
    marginTop: spacing.lg,
    padding: spacing.md,
    borderRadius: spacing.radii.card || spacing.radii.lg,
  },
  employerNoticeHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: spacing.xs,
  },
  employerNoticeBadge: {
    ...typography.badge,
    color: colors.accentStrong || colors.tealDark,
    fontSize: 12,
    fontWeight: '700',
    letterSpacing: 0.5,
    marginStart: spacing.xs,
  },
  employerNoticeText: {
    ...typography.caption,
    color: colors.textSecondary || colors.textMuted,
    fontSize: 13,
    lineHeight: 18,
  },
  iconLTR: {
    marginEnd: spacing.xs,
  },
  iconRTL: {
    marginStart: spacing.xs,
  },
  textRTL: {
    textAlign: 'right',
  },
});
