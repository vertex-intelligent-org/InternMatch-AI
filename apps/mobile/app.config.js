module.exports = ({ config }) => {
  const isProduction =
    process.env.APP_VARIANT === "production";

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
    plugins,
  };
};