import React, { useState } from 'react';
import {
  View,
  Text,
  TextInput,
  StyleSheet,
  TouchableOpacity,
  ScrollView,
  Alert,
  KeyboardAvoidingView,
  Platform,
  Image,
  ActivityIndicator,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTranslation } from 'react-i18next';
import { useLocalization } from '../localization/LocalizationContext';
import * as ImagePicker from 'expo-image-picker';
import colors from '../theme/colors';
import { spacing } from '../theme/spacing';
import { typography } from '../theme/typography';
import ScreenContainer from '../components/ScreenContainer';
import ScreenHeader from '../components/ScreenHeader';
import Chip from '../components/Chip';
import GradientButton from '../components/GradientButton';
import { useProfile } from '../context/ProfileContext';
import { upsertProfile, uploadAvatar, deleteAvatar } from '../services/api';
import { normalizeAccountType } from '../services/subscriptionService';
import haptics from '../services/haptics';

const WORK_TYPE_KEYS = [
  { id: 'remote' },
  { id: 'hybrid' },
  { id: 'onsite' },
];

function getInitials(name) {
  if (!name || typeof name !== 'string') return '';
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return '';
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

function normalizeUrl(rawUrl) {
  if (!rawUrl || typeof rawUrl !== 'string') return null;
  let trimmed = rawUrl.trim();
  if (!trimmed) return null;

  // Block dangerous schemes
  const lower = trimmed.toLowerCase();
  if (
    lower.startsWith('javascript:') ||
    lower.startsWith('data:') ||
    lower.startsWith('vbscript:') ||
    lower.startsWith('file:')
  ) {
    return null;
  }

  // Prepend https:// if no scheme provided
  if (!/^https?:\/\//i.test(trimmed)) {
    trimmed = 'https://' + trimmed;
  }

  try {
    const parsed = new URL(trimmed);
    if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
      return null;
    }
    return parsed.toString();
  } catch {
    // Regex validation fallback
    if (/^https?:\/\/[^\s$.?#].[^\s]*$/i.test(trimmed)) {
      return trimmed;
    }
    return null;
  }
}

export default function EditProfileScreen({ navigation }) {
  const { t } = useTranslation();
  const { isRTL } = useLocalization();
  const { profile, setProfile, refreshProfile } = useProfile();

  const accountType = profile?.preferences?.account_type
    ? normalizeAccountType(profile.preferences.account_type)
    : null;
  const isEmployer = accountType === 'employer';

  const [fullName, setFullName] = useState(profile?.full_name ?? '');
  const [headline, setHeadline] = useState(profile?.headline ?? '');
  const [department, setDepartment] = useState(
    typeof profile?.preferences?.department === 'string' ? profile.preferences.department : ''
  );
  const [linkedinUrl, setLinkedinUrl] = useState(
    typeof profile?.preferences?.linkedin_url === 'string' ? profile.preferences.linkedin_url : ''
  );
  const [githubUrl, setGithubUrl] = useState(
    typeof profile?.preferences?.github_url === 'string' ? profile.preferences.github_url : ''
  );
  const [portfolioUrl, setPortfolioUrl] = useState(
    typeof profile?.preferences?.portfolio_url === 'string' ? profile.preferences.portfolio_url : ''
  );

  const [skills, setSkills] = useState(
    Array.isArray(profile?.skills) ? [...profile.skills] : []
  );
  const [newSkill, setNewSkill] = useState('');

  // Career Preferences State
  const [workTypes, setWorkTypes] = useState(
    Array.isArray(profile?.preferences?.work_types)
      ? profile.preferences.work_types
          .map((wt) => (typeof wt === 'string' ? wt.trim().toLowerCase() : ''))
          .filter(Boolean)
      : []
  );

  const [desiredLocations, setDesiredLocations] = useState(
    Array.isArray(profile?.preferences?.desired_locations)
      ? [...profile.preferences.desired_locations]
      : []
  );
  const [newLocation, setNewLocation] = useState('');

  const [targetRoles, setTargetRoles] = useState(
    Array.isArray(profile?.preferences?.target_roles)
      ? [...profile.preferences.target_roles]
      : []
  );
  const [newRole, setNewRole] = useState('');

  const [avatarUri, setAvatarUri] = useState(profile?.avatar_url ?? null);
  const [uploadingAvatar, setUploadingAvatar] = useState(false);
  const [saving, setSaving] = useState(false);

  const currentAvatar = avatarUri || profile?.avatar_url || null;
  const initials = getInitials(fullName || profile?.full_name);

  const handlePickImage = async () => {
    try {
      const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (!permission.granted) {
        Alert.alert(
          t('editProfile.permissionRequiredTitle'),
          t('editProfile.permissionRequiredMsg')
        );
        return;
      }

      const result = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ['images'],
        allowsEditing: true,
        aspect: [1, 1],
        quality: 0.85,
      });

      if (result.canceled || !result.assets || result.assets.length === 0) {
        return;
      }

      const asset = result.assets[0];
      setAvatarUri(asset.uri);
      setUploadingAvatar(true);

      try {
        const uploadRes = await uploadAvatar({
          uri: asset.uri,
          name: asset.fileName || 'avatar.jpg',
          type: asset.mimeType || 'image/jpeg',
        });
        setAvatarUri(uploadRes.avatar_url);
        await refreshProfile();
        haptics.success();
      } catch (err) {
        setAvatarUri(profile?.avatar_url || null);
        console.warn('Avatar upload failed:', err);
        Alert.alert(t('common.error'), t('editProfile.uploadFailed'));
        haptics.error();
      } finally {
        setUploadingAvatar(false);
      }
    } catch (err) {
      console.warn('Image picker error:', err);
      setUploadingAvatar(false);
    }
  };

  const handleRemoveAvatar = async () => {
    setUploadingAvatar(true);
    try {
      await deleteAvatar();
      setAvatarUri(null);
      await refreshProfile();
      haptics.success();
    } catch (err) {
      console.warn('Avatar remove failed:', err);
      Alert.alert(t('common.error'), t('editProfile.removeFailed'));
      haptics.error();
    } finally {
      setUploadingAvatar(false);
    }
  };

  const handleAvatarPress = () => {
    if (uploadingAvatar) return;

    if (currentAvatar) {
      Alert.alert(t('editProfile.avatarOptionsTitle'), t('editProfile.avatarOptionsSubtitle'), [
        { text: t('editProfile.chooseFromLibrary'), onPress: handlePickImage },
        { text: t('editProfile.removePhoto'), style: 'destructive', onPress: handleRemoveAvatar },
        { text: t('common.cancel'), style: 'cancel' },
      ]);
    } else {
      handlePickImage();
    }
  };

  // Skill Add / Remove
  const handleAddSkill = () => {
    if (!newSkill) return;
    const clean = newSkill.replace(/\s+/g, ' ').trim();
    if (!clean) {
      setNewSkill('');
      return;
    }

    if (clean.length > 80) {
      haptics.error();
      Alert.alert(t('common.error'), t('editProfile.skillTooLong'));
      return;
    }

    if (skills.length >= 50) {
      haptics.error();
      Alert.alert(t('common.error'), t('editProfile.maxSkillsReached'));
      return;
    }

    const isDuplicate = skills.some(
      (s) => s.trim().toLowerCase() === clean.toLowerCase()
    );

    if (isDuplicate) {
      haptics.selection();
      setNewSkill('');
      return;
    }

    haptics.selection();
    setSkills((prev) => [...prev, clean]);
    setNewSkill('');
  };

  const handleRemoveSkill = (skillToRemove) => {
    haptics.selection();
    setSkills((prev) => prev.filter((s) => s !== skillToRemove));
  };

  // Work Type Toggle
  const toggleWorkType = (typeId) => {
    haptics.selection();
    setWorkTypes((prev) =>
      prev.includes(typeId) ? prev.filter((t) => t !== typeId) : [...prev, typeId]
    );
  };

  // Location Add / Remove
  const handleAddLocation = () => {
    if (!newLocation) return;
    const clean = newLocation.replace(/\s+/g, ' ').trim();
    if (!clean) {
      setNewLocation('');
      return;
    }

    if (clean.length > 80) {
      haptics.error();
      Alert.alert(t('common.error'), t('editProfile.locationTooLong'));
      return;
    }

    if (desiredLocations.length >= 10) {
      haptics.error();
      Alert.alert(t('common.error'), t('editProfile.limitLocations'));
      return;
    }

    const isDuplicate = desiredLocations.some(
      (l) => l.trim().toLowerCase() === clean.toLowerCase()
    );

    if (isDuplicate) {
      haptics.selection();
      setNewLocation('');
      return;
    }

    haptics.selection();
    setDesiredLocations((prev) => [...prev, clean]);
    setNewLocation('');
  };

  const handleRemoveLocation = (locToRemove) => {
    haptics.selection();
    setDesiredLocations((prev) => prev.filter((l) => l !== locToRemove));
  };

  // Role Add / Remove
  const handleAddRole = () => {
    if (!newRole) return;
    const clean = newRole.replace(/\s+/g, ' ').trim();
    if (!clean) {
      setNewRole('');
      return;
    }

    if (clean.length > 80) {
      haptics.error();
      Alert.alert(t('common.error'), t('editProfile.roleTooLong'));
      return;
    }

    if (targetRoles.length >= 10) {
      haptics.error();
      Alert.alert(t('common.error'), t('editProfile.limitRoles'));
      return;
    }

    const isDuplicate = targetRoles.some(
      (r) => r.trim().toLowerCase() === clean.toLowerCase()
    );

    if (isDuplicate) {
      haptics.selection();
      setNewRole('');
      return;
    }

    haptics.selection();
    setTargetRoles((prev) => [...prev, clean]);
    setNewRole('');
  };

  const handleRemoveRole = (roleToRemove) => {
    haptics.selection();
    setTargetRoles((prev) => prev.filter((r) => r !== roleToRemove));
  };

  const handleSave = async () => {
    const trimmedName = fullName.trim();
    if (!trimmedName) {
      haptics.error();
      Alert.alert(t('common.error'), t('editProfile.enterFullName'));
      return;
    }

    if (saving) return;

    const normalizedLinkedin = normalizeUrl(linkedinUrl);
    const normalizedGithub = normalizeUrl(githubUrl);
    const normalizedPortfolio = normalizeUrl(portfolioUrl);

    if (linkedinUrl.trim() && !normalizedLinkedin) {
      haptics.error();
      Alert.alert(t('common.error'), t('editProfile.invalidUrl'));
      return;
    }
    if (githubUrl.trim() && !normalizedGithub) {
      haptics.error();
      Alert.alert(t('common.error'), t('editProfile.invalidUrl'));
      return;
    }
    if (portfolioUrl.trim() && !normalizedPortfolio) {
      haptics.error();
      Alert.alert(t('common.error'), t('editProfile.invalidUrl'));
      return;
    }

    setSaving(true);
    try {
      const payload = isEmployer
        ? {
            full_name: trimmedName,
            headline: headline.trim() || null,
            preferences: {
              ...(profile?.preferences || {}),
              account_type: 'employer',
              linkedin_url: normalizedLinkedin,
              github_url: normalizedGithub,
              portfolio_url: normalizedPortfolio,
            },
            skills: profile?.skills || [],
          }
        : {
            full_name: trimmedName,
            headline: headline.trim() || (department.trim() ? department.trim() : null),
            preferences: {
              ...(profile?.preferences || {}),
              account_type: profile?.preferences?.account_type || 'intern',
              department: department.trim() || null,
              linkedin_url: normalizedLinkedin,
              github_url: normalizedGithub,
              portfolio_url: normalizedPortfolio,
              work_types: workTypes,
              desired_locations: desiredLocations,
              target_roles: targetRoles,
            },
            skills: skills,
          };

      const updated = await upsertProfile(payload);
      setProfile(updated);
      haptics.success();
      navigation.goBack();
    } catch (error) {
      console.warn('Profile save failed:', error);
      Alert.alert(t('common.error'), t('errors.profileSaveFailed'));
    } finally {
      setSaving(false);
    }
  };

  if (!profile) {
    return (
      <ScreenContainer edges={['top', 'bottom']}>
        <ScreenHeader
          title={t('editProfile.title')}
          showBack={true}
          navigation={navigation}
        />
        <View style={styles.centerLoading}>
          <ActivityIndicator size="large" color={colors.accent || colors.teal} />
        </View>
      </ScreenContainer>
    );
  }

  return (
    <ScreenContainer edges={['top', 'bottom']}>
      <ScreenHeader
        title={t('editProfile.title')}
        showBack={true}
        navigation={navigation}
      />

      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={styles.flex}
      >
        <ScrollView
          style={styles.screen}
          contentContainerStyle={styles.content}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          {/* Circular Interactive Avatar */}
          <View style={styles.avatarWrap}>
            <TouchableOpacity
              style={styles.avatarTouchTarget}
              onPress={handleAvatarPress}
              disabled={uploadingAvatar}
              accessibilityRole="button"
              accessibilityLabel={currentAvatar ? t('editProfile.changePhoto') : t('editProfile.addPhoto')}
              accessibilityHint={t('editProfile.avatarOptionsSubtitle')}
              hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
            >
              <View style={styles.avatarContainer}>
                {uploadingAvatar ? (
                  <ActivityIndicator size="small" color={colors.accent || colors.teal} />
                ) : currentAvatar ? (
                  <Image source={{ uri: currentAvatar }} style={styles.avatarImage} />
                ) : initials ? (
                  <Text style={styles.avatarInitials}>{initials}</Text>
                ) : (
                  <Ionicons
                    name="person-add-outline"
                    size={28}
                    color={colors.accent || colors.teal}
                  />
                )}

                {/* Camera / Edit Badge Indicator */}
                {!uploadingAvatar && (
                  <View style={styles.editBadge}>
                    <Ionicons name="camera" size={13} color="#FFFFFF" />
                  </View>
                )}
              </View>
            </TouchableOpacity>
            <Text style={styles.avatarLabel}>
              {currentAvatar ? t('editProfile.changePhoto') : t('editProfile.addPhoto')}
            </Text>
          </View>

          <Text style={[styles.sectionTitle, isRTL && styles.textRTL]}>{t('editProfile.basicInfo')}</Text>

          <Text style={[styles.label, isRTL && styles.textRTL]}>
            {isEmployer ? t('editProfile.employer.fullName') : t('editProfile.fullName')}
          </Text>
          <TextInput
            style={[styles.input, styles.compactMultilineInput, isRTL && styles.inputRTL]}
            multiline
            numberOfLines={2}
            textAlignVertical="top"
            maxLength={120}
            placeholder={isEmployer ? t('editProfile.employer.fullNamePlaceholder') : t('editProfile.fullName')}
            placeholderTextColor={colors.textTertiary || colors.textMuted}
            value={fullName}
            onChangeText={setFullName}
          />

          <Text style={[styles.label, isRTL && styles.textRTL]}>{t('editProfile.headline')}</Text>
          <TextInput
            style={[styles.input, styles.headlineInput, isRTL && styles.inputRTL]}
            multiline
            numberOfLines={2}
            textAlignVertical="top"
            placeholder={
              isEmployer
                ? t('editProfile.employer.headlinePlaceholder', { defaultValue: 'e.g. Technology company hiring interns' })
                : t('editProfile.headlinePlaceholder', { defaultValue: 'e.g. Computer Science Student' })
            }
            placeholderTextColor={colors.textTertiary || colors.textMuted}
            value={headline}
            onChangeText={setHeadline}
          />

          {!isEmployer && (
            <>
              <Text style={[styles.label, isRTL && styles.textRTL]}>{t('editProfile.department')}</Text>
              <TextInput
                style={[styles.input, styles.compactMultilineInput, isRTL && styles.inputRTL]}
                multiline
                numberOfLines={2}
                textAlignVertical="top"
                maxLength={120}
                placeholder={t('editProfile.departmentPlaceholder', { defaultValue: 'e.g. Computer Engineering' })}
                placeholderTextColor={colors.textTertiary || colors.textMuted}
                value={department}
                onChangeText={setDepartment}
              />

              {/* Editable Skills Section */}
              <Text style={[styles.sectionTitle, isRTL && styles.textRTL]}>{t('editProfile.skills')}</Text>
              <View style={[styles.chipInputRow, isRTL && styles.rowRTL]}>
                <TextInput
                  style={[styles.input, styles.chipInput, isRTL && styles.inputRTL]}
                  placeholder={t('editProfile.addSkillPlaceholder')}
                  placeholderTextColor={colors.textTertiary || colors.textMuted}
                  value={newSkill}
                  onChangeText={setNewSkill}
                  onSubmitEditing={handleAddSkill}
                  returnKeyType="done"
                  maxLength={80}
                />
                <TouchableOpacity
                  style={styles.addChipBtn}
                  onPress={handleAddSkill}
                  accessibilityRole="button"
                  accessibilityLabel={t('editProfile.addSkillPlaceholder')}
                  hitSlop={{ top: 6, bottom: 6, left: 6, right: 6 }}
                >
                  <Ionicons name="add" size={20} color="#FFFFFF" />
                </TouchableOpacity>
              </View>

              {skills.length > 0 ? (
                <View style={styles.chipRow}>
                  {skills.map((s) => (
                    <Chip
                      key={s}
                      label={s}
                      variant="skill"
                      onRemove={() => handleRemoveSkill(s)}
                    />
                  ))}
                </View>
              ) : (
                <Text style={[styles.emptyItemsText, isRTL && styles.textRTL]}>
                  {t('editProfile.noSkills')}
                </Text>
              )}

              {/* Career Preferences Section */}
              <Text style={[styles.sectionTitle, isRTL && styles.textRTL]}>{t('editProfile.careerPreferences')}</Text>

              <Text style={[styles.label, isRTL && styles.textRTL]}>{t('editProfile.workStyle')}</Text>
              <View style={styles.chipRow}>
                {WORK_TYPE_KEYS.map((opt) => {
                  const isSelected = workTypes.includes(opt.id);
                  const label = t(`editProfile.workTypes.${opt.id}`, { defaultValue: opt.id });
                  return (
                    <Chip
                      key={opt.id}
                      label={label}
                      variant={isSelected ? 'skill' : 'neutral'}
                      selected={isSelected}
                      onPress={() => toggleWorkType(opt.id)}
                    />
                  );
                })}
              </View>

              <Text style={[styles.label, isRTL && styles.textRTL]}>{t('editProfile.desiredLocations')}</Text>
              <View style={[styles.chipInputRow, isRTL && styles.rowRTL]}>
                <TextInput
                  style={[styles.input, styles.chipInput, isRTL && styles.inputRTL]}
                  placeholder={t('editProfile.addLocationPlaceholder')}
                  placeholderTextColor={colors.textTertiary || colors.textMuted}
                  value={newLocation}
                  onChangeText={setNewLocation}
                  onSubmitEditing={handleAddLocation}
                  returnKeyType="done"
                  maxLength={80}
                />
                <TouchableOpacity
                  style={styles.addChipBtn}
                  onPress={handleAddLocation}
                  accessibilityRole="button"
                  accessibilityLabel={t('editProfile.addLocationPlaceholder')}
                  hitSlop={{ top: 6, bottom: 6, left: 6, right: 6 }}
                >
                  <Ionicons name="add" size={20} color="#FFFFFF" />
                </TouchableOpacity>
              </View>

              {desiredLocations.length > 0 ? (
                <View style={styles.chipRow}>
                  {desiredLocations.map((loc) => (
                    <Chip
                      key={loc}
                      label={loc}
                      variant="skill"
                      onRemove={() => handleRemoveLocation(loc)}
                    />
                  ))}
                </View>
              ) : (
                <Text style={[styles.emptyItemsText, isRTL && styles.textRTL]}>
                  {t('editProfile.noLocations')}
                </Text>
              )}

              <Text style={[styles.label, isRTL && styles.textRTL]}>{t('editProfile.targetRoles')}</Text>
              <View style={[styles.chipInputRow, isRTL && styles.rowRTL]}>
                <TextInput
                  style={[styles.input, styles.chipInput, isRTL && styles.inputRTL]}
                  placeholder={t('editProfile.addRolePlaceholder')}
                  placeholderTextColor={colors.textTertiary || colors.textMuted}
                  value={newRole}
                  onChangeText={setNewRole}
                  onSubmitEditing={handleAddRole}
                  returnKeyType="done"
                  maxLength={80}
                />
                <TouchableOpacity
                  style={styles.addChipBtn}
                  onPress={handleAddRole}
                  accessibilityRole="button"
                  accessibilityLabel={t('editProfile.addRolePlaceholder')}
                  hitSlop={{ top: 6, bottom: 6, left: 6, right: 6 }}
                >
                  <Ionicons name="add" size={20} color="#FFFFFF" />
                </TouchableOpacity>
              </View>

              {targetRoles.length > 0 ? (
                <View style={styles.chipRow}>
                  {targetRoles.map((role) => (
                    <Chip
                      key={role}
                      label={role}
                      variant="skill"
                      onRemove={() => handleRemoveRole(role)}
                    />
                  ))}
                </View>
              ) : (
                <Text style={[styles.emptyItemsText, isRTL && styles.textRTL]}>
                  {t('editProfile.noRoles')}
                </Text>
              )}
            </>
          )}

          <Text style={[styles.sectionTitle, isRTL && styles.textRTL]}>{t('editProfile.socialLinks')}</Text>

          <Text style={[styles.label, isRTL && styles.textRTL]}>{t('editProfile.linkedin')}</Text>
          <TextInput
            style={[styles.input, styles.urlInput]}
            placeholder="https://linkedin.com/in/username"
            placeholderTextColor={colors.textTertiary || colors.textMuted}
            value={linkedinUrl}
            onChangeText={setLinkedinUrl}
            autoCapitalize="none"
            autoCorrect={false}
            keyboardType="url"
          />

          <Text style={[styles.label, isRTL && styles.textRTL]}>{t('editProfile.github')}</Text>
          <TextInput
            style={[styles.input, styles.urlInput]}
            placeholder="https://github.com/username"
            placeholderTextColor={colors.textTertiary || colors.textMuted}
            value={githubUrl}
            onChangeText={setGithubUrl}
            autoCapitalize="none"
            autoCorrect={false}
            keyboardType="url"
          />

          <Text style={[styles.label, isRTL && styles.textRTL]}>{t('editProfile.portfolio')}</Text>
          <TextInput
            style={[styles.input, styles.urlInput]}
            placeholder="https://yourportfolio.com"
            placeholderTextColor={colors.textTertiary || colors.textMuted}
            value={portfolioUrl}
            onChangeText={setPortfolioUrl}
            autoCapitalize="none"
            autoCorrect={false}
            keyboardType="url"
          />

          <GradientButton
            title={saving ? t('common.saving') : t('common.save')}
            color={colors.accent || colors.teal}
            onPress={handleSave}
            disabled={saving || uploadingAvatar}
            style={{ marginTop: spacing.lg }}
          />
        </ScrollView>
      </KeyboardAvoidingView>
    </ScreenContainer>
  );
}

const styles = StyleSheet.create({
  flex: {
    flex: 1,
  },
  screen: {
    flex: 1,
    backgroundColor: colors.background || colors.screenBg,
  },
  content: {
    paddingHorizontal: spacing.screenHorizontalPadding,
    paddingTop: spacing.xs,
    paddingBottom: spacing.xxxl,
  },
  avatarWrap: {
    alignItems: 'center',
    marginBottom: spacing.lg,
  },
  avatarTouchTarget: {
    alignItems: 'center',
    justifyContent: 'center',
  },
  avatarContainer: {
    width: 76,
    height: 76,
    borderRadius: 38,
    borderWidth: 2,
    borderColor: colors.accent || colors.teal,
    backgroundColor: colors.surface || colors.cardBg,
    alignItems: 'center',
    justifyContent: 'center',
    position: 'relative',
    shadowColor: 'rgba(14, 116, 144, 0.2)',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 1,
    shadowRadius: 4,
    elevation: 2,
  },
  avatarImage: {
    width: 72,
    height: 72,
    borderRadius: 36,
  },
  avatarInitials: {
    ...typography.display,
    fontSize: 22,
    fontWeight: '700',
    color: colors.accentStrong || colors.tealDark,
  },
  editBadge: {
    position: 'absolute',
    bottom: -2,
    right: -2,
    width: 24,
    height: 24,
    borderRadius: 12,
    backgroundColor: colors.accentStrong || colors.tealDark,
    borderWidth: 2,
    borderColor: colors.surface || '#FFFFFF',
    alignItems: 'center',
    justifyContent: 'center',
  },
  avatarLabel: {
    ...typography.caption,
    fontWeight: '600',
    color: colors.accentStrong || colors.tealDark,
    marginTop: spacing.xs + 2,
  },
  label: {
    ...typography.caption,
    fontWeight: '600',
    color: colors.textPrimary || colors.textDark,
    marginBottom: spacing.xxs + 2,
    marginStart: spacing.xxs,
  },
  input: {
    borderWidth: 1,
    borderColor: colors.borderSubtle || colors.border,
    backgroundColor: colors.surface || colors.cardBg,
    borderRadius: spacing.radii.md,
    minHeight: 46,
    paddingHorizontal: spacing.lg,
    marginBottom: spacing.md,
    justifyContent: 'center',
    color: colors.textPrimary || colors.textDark,
    ...typography.body,
  },
  inputRTL: {
    textAlign: 'right',
    writingDirection: 'rtl',
  },
  urlInput: {
    textAlign: 'left',
    writingDirection: 'ltr',
  },
  textRTL: {
    textAlign: 'right',
    writingDirection: 'rtl',
  },
  rowRTL: {
    flexDirection: 'row-reverse',
  },
  headlineInput: {
    minHeight: 72,
    paddingTop: spacing.sm,
    paddingBottom: spacing.sm,
  },
  compactMultilineInput: {
    height: 72,
    minHeight: 72,
    maxHeight: 72,
    paddingTop: spacing.sm,
    paddingBottom: spacing.sm,
  },
  chipInputRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: spacing.sm,
  },
  chipInput: {
    flex: 1,
    marginBottom: 0,
    marginEnd: spacing.sm,
  },
  addChipBtn: {
    width: 46,
    height: 46,
    borderRadius: spacing.radii.md,
    backgroundColor: colors.accentStrong || colors.tealDark,
    alignItems: 'center',
    justifyContent: 'center',
  },
  emptyItemsText: {
    ...typography.caption,
    color: colors.textSecondary || colors.textMuted,
    marginBottom: spacing.md,
    marginStart: spacing.xxs,
    fontStyle: 'italic',
  },
  sectionTitle: {
    ...typography.sectionTitle,
    color: colors.textPrimary || colors.textDark,
    marginTop: spacing.md,
    marginBottom: spacing.sm,
  },
  chipRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    marginBottom: spacing.md,
  },
  centerLoading: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: spacing.xxxl,
  },
});
