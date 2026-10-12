import { Config } from '@remotion/cli/config';
import path from 'node:path';

Config.setVideoImageFormat('png');
Config.setOverwriteOutput(true);
Config.overrideWebpackConfig(config => ({
  ...config,
  resolve: {
    ...config.resolve,
    alias: { ...config.resolve?.alias, '@': path.resolve('../../apps/web/src') },
  },
}));
