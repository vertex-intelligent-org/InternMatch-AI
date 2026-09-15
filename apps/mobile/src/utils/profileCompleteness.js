/**
 * Profile Completeness Calculation Utility
 * Evaluates the 9 canonical profile completion dimensions:
 * 1. Full name
 * 2. Headline
 * 3. CV
 * 4. Skills
 * 5. Education
 * 6. Experience
 * 7. Career preferences
 * 8. Avatar
 * 9. Social links
 */

export function calculateProfileCompleteness(profile) {
  const defaultMissing = [
    { key: 'full_name', label: 'Add your full name', route: 'EditProfile' },
    { key: 'headline', label: 'Add a headline', route: 'EditProfile' },
    { key: 'cv', label: 'Upload your CV', route: 'CVUpload' },
    { key: 'skills', label: 'Add skills', route: 'EditProfile' },
    { key: 'education', label: 'Add education', route: 'CVUpload' },
    { key: 'experience', label: 'Add experience', route: 'CVUpload' },
    { key: 'preferences', label: 'Set career preferences', route: 'EditProfile' },
    { key: 'avatar', label: 'Add a profile photo', route: 'EditProfile' },
    { key: 'social', label: 'Add a social link', route: 'EditProfile' },
  ];

  if (!profile) {
    return {
      completedCount: 0,
      totalCount: 9,
      percentage: 0,
      missingItems: defaultMissing,
      firstMissingItem: defaultMissing[0],
      isComplete: false,
    };
  }

  const dimensions = [
    {
      key: 'full_name',
      label: 'Add your full name',
      route: 'EditProfile',
      completed: Boolean(
        profile.full_name &&
          typeof profile.full_name === 'string' &&
          profile.full_name.trim().length > 0
      ),
    },
    {
      key: 'headline',
      label: 'Add a headline',
      route: 'EditProfile',
      completed: Boolean(
        profile.headline &&
          typeof profile.headline === 'string' &&
          profile.headline.trim().length > 0
      ),
    },
    {
      key: 'cv',
      label: 'Upload your CV',
      route: 'CVUpload',
      completed: Boolean(profile.has_cv),
    },
    {
      key: 'skills',
      label: 'Add skills',
      route: 'EditProfile',
      completed: Boolean(Array.isArray(profile.skills) && profile.skills.length > 0),
    },
    {
      key: 'education',
      label: 'Add education',
      route: 'CVUpload',
      completed: Boolean(Array.isArray(profile.education) && profile.education.length > 0),
    },
    {
      key: 'experience',
      label: 'Add experience',
      route: 'CVUpload',
      completed: Boolean(Array.isArray(profile.experience) && profile.experience.length > 0),
    },
    {
      key: 'preferences',
      label: 'Set career preferences',
      route: 'EditProfile',
      completed: Boolean(
        (Array.isArray(profile.preferences?.work_types) &&
          profile.preferences.work_types.length > 0) ||
          (Array.isArray(profile.preferences?.desired_locations) &&
            profile.preferences.desired_locations.length > 0) ||
          (Array.isArray(profile.preferences?.target_roles) &&
            profile.preferences.target_roles.length > 0)
      ),
    },
    {
      key: 'avatar',
      label: 'Add a profile photo',
      route: 'EditProfile',
      completed: Boolean(
        profile.avatar_url &&
          typeof profile.avatar_url === 'string' &&
          profile.avatar_url.trim().length > 0
      ),
    },
    {
      key: 'social',
      label: 'Add a social link',
      route: 'EditProfile',
      completed: Boolean(
        (profile.preferences?.linkedin_url &&
          typeof profile.preferences.linkedin_url === 'string' &&
          profile.preferences.linkedin_url.trim().length > 0) ||
          (profile.preferences?.github_url &&
            typeof profile.preferences.github_url === 'string' &&
            profile.preferences.github_url.trim().length > 0) ||
          (profile.preferences?.portfolio_url &&
            typeof profile.preferences.portfolio_url === 'string' &&
            profile.preferences.portfolio_url.trim().length > 0)
      ),
    },
  ];

  const completedCount = dimensions.filter((d) => d.completed).length;
  const totalCount = dimensions.length; // 9
  const percentage = Math.round((completedCount / totalCount) * 100);
  const missingItems = dimensions.filter((d) => !d.completed);
  const firstMissingItem = missingItems.length > 0 ? missingItems[0] : null;

  return {
    completedCount,
    totalCount,
    percentage,
    missingItems,
    firstMissingItem,
    isComplete: completedCount === totalCount,
  };
}
