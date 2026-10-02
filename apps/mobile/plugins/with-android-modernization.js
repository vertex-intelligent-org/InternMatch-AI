const { withAndroidManifest, withAndroidStyles } = require('expo/config-plugins');

const DEPRECATED_STYLE_ITEMS = new Set([
  'android:statusBarColor',
  'android:navigationBarColor',
  'android:navigationBarDividerColor',
  'android:statusBarContrastEnforced',
  'android:navigationBarContrastEnforced',
]);

function stripScreenOrientation(activity) {
  if (activity && activity.$) {
    delete activity.$['android:screenOrientation'];
    delete activity.$['android:resizeableActivity'];
  }
}

const withAndroidModernization = (config) => {
  config = withAndroidManifest(config, (manifestConfig) => {
    const application = manifestConfig.modResults.manifest.application?.[0];

    if (!application) {
      return manifestConfig;
    }

    application.$ = application.$ || {};
    application.$['android:resizeableActivity'] = 'true';

    for (const activity of application.activity || []) {
      stripScreenOrientation(activity);
    }

    for (const alias of application['activity-alias'] || []) {
      stripScreenOrientation(alias);
    }

    return manifestConfig;
  });

  config = withAndroidStyles(config, (stylesConfig) => {
    const styles = stylesConfig.modResults.resources?.style || [];

    for (const style of styles) {
      if (!Array.isArray(style.item)) {
        continue;
      }

      style.item = style.item.filter(
        (item) => !DEPRECATED_STYLE_ITEMS.has(item?.$?.name)
      );
    }

    return stylesConfig;
  });

  return config;
};

module.exports = withAndroidModernization;
