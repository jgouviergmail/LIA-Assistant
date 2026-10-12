import { bundle } from '@remotion/bundler';
import { getCompositions, renderStill } from '@remotion/renderer';
import { mkdir, mkdtemp } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const project = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const root = path.resolve(project, '../..');
const output = path.resolve(root, 'exports/lia-motion');
await mkdir(path.resolve(project, 'build'), { recursive: true });
await mkdir(output, { recursive: true });
const serveUrl = await bundle({
  entryPoint: path.resolve(project, 'src/index.ts'),
  publicDir: path.resolve(project, 'public'),
  outDir: await mkdtemp(path.resolve(project, 'build/story-review-')),
  webpackOverride: config => ({
    ...config,
    cache: false,
    resolve: {
      ...config.resolve,
      alias: { ...config.resolve?.alias, '@': path.resolve(root, 'apps/web/src') },
    },
  }),
});
const browserExecutable = process.env.REMOTION_BROWSER_EXECUTABLE;
const compositions = await getCompositions(serveUrl, { browserExecutable });
const composition = compositions.find(item => item.id === 'LIA-Story24');
if (!composition) throw new Error('Story composition missing');
for (const seconds of [4, 9, 14, 16, 19, 23]) {
  await renderStill({
    serveUrl, composition, browserExecutable,
    frame: seconds * composition.fps,
    output: path.resolve(output, `story24-${seconds}.png`),
    imageFormat: 'png', logLevel: 'error',
  });
  console.log(`Story frame reviewed: ${seconds} s`);
}
for (const comparison of ['research', 'approval', 'result']) {
  await renderStill({
    serveUrl, composition, browserExecutable,
    inputProps: { withAudio: false, comparison },
    frame: 0,
    output: path.resolve(output, `story24-ui-${comparison}.png`),
    imageFormat: 'png', logLevel: 'error',
  });
  console.log(`Native UI comparison: ${comparison}`);
}
