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
