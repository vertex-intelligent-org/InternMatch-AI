module.exports = ({ config }) => {
  const variant = process.env.APP_VARIANT;
  const isProduction = variant === "production";
  const isDevelopment = variant === "development";

  const plugins = config.plugins.map((plugin) => {
    if (
      Array.isArray(plugin) &&
      plugin[0] === "expo-build-properties"
    ) {
      return [
        plugin[0],
        {
          ...plugin[1],
          android: {
            ...plugin[1].android,
            usesCleartextTraffic: !isProduction,
          },
        },
      ];
    }

    return plugin;
  });

  return {
    ...config,
    name: isDevelopment ? "InternMatch AI Dev" : config.name,
    android: {
      ...config.android,
      package: isDevelopment
        ? "com.aissclub.internmatchai.dev"
        : config.android.package,
      ...(isProduction
        ? { googleServicesFile: "./google-services.json" }
        : {}),
    },
    ios: {
      ...config.ios,
      bundleIdentifier: isDevelopment
        ? "com.aissclub.internmatchai.dev"
        : config.ios.bundleIdentifier,
    },
    plugins,
  };
};

// INTERNMATCH_ENVIRONMENT_CLEARTEXT_POLICY_BEGIN
const internMatchConfigBeforeCleartextPolicy = module.exports;

module.exports = (context) => {
  const resolvedConfig =
    typeof internMatchConfigBeforeCleartextPolicy === 'function'
      ? internMatchConfigBeforeCleartextPolicy(context)
      : internMatchConfigBeforeCleartextPolicy;

  if (!resolvedConfig || typeof resolvedConfig !== 'object') {
    throw new Error('Unable to resolve Expo configuration');
  }

  const allowCleartext =
    process.env.APP_VARIANT === 'development';
  let buildPropertiesMatches = 0;

  const plugins = (resolvedConfig.plugins || []).map((plugin) => {
    const pluginName = Array.isArray(plugin) ? plugin[0] : plugin;

    if (pluginName !== 'expo-build-properties') {
      return plugin;
    }

    buildPropertiesMatches += 1;

    const nextPlugin = Array.isArray(plugin)
      ? plugin.slice()
      : [pluginName, {}];
    const options =
      nextPlugin[1] &&
      typeof nextPlugin[1] === 'object' &&
      !Array.isArray(nextPlugin[1])
        ? { ...nextPlugin[1] }
        : {};

    nextPlugin[1] = {
      ...options,
      android: {
        ...(options.android || {}),
        usesCleartextTraffic: allowCleartext,
      },
    };

    return nextPlugin;
  });

  if (buildPropertiesMatches !== 1) {
    throw new Error(
      'Expected exactly one expo-build-properties plugin'
    );
  }

  return {
    ...resolvedConfig,
    plugins,
  };
};
// INTERNMATCH_ENVIRONMENT_CLEARTEXT_POLICY_END
