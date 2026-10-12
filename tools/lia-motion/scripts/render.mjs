import { bundle } from '@remotion/bundler';
import { getCompositions, renderMedia } from '@remotion/renderer';
import { mkdir, mkdtemp, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { measuredLoudnessFilter, runFfmpeg } from './audio-master.mjs';
import { PRESENTATION_REVISION } from '../src/presentation-plan.ts';

const project = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const root = path.resolve(project, '../..');
const output = path.resolve(root, 'exports/lia-motion');
const mode = process.argv[2] ?? 'full';
const requestedFocusIds = process.argv
  .slice(3)
  .map(name => (name.startsWith('LIA-') ? name : `LIA-${name}`));
if (requestedFocusIds.length && mode !== 'focus')
  throw new Error('Named selections are supported only in focus mode');
const executable = process.env.REMOTION_BROWSER_EXECUTABLE;
if (mode === 'stills' || mode === 'stills-focus') {
  const reviewed = spawnSync(process.execPath,
    ['--experimental-strip-types', path.resolve(project, 'scripts/review-presentation.mjs'), mode === 'stills' ? 'all' : 'focus'],
    {stdio:'inherit'});
  process.exit(reviewed.status ?? 1);
}
await mkdir(output, { recursive: true });
const prepared = spawnSync(
  process.execPath,
  [path.resolve(project, 'scripts/prepare-assets.mjs')],
  { stdio: 'inherit' }
);
if (prepared.status !== 0) throw new Error('LIA asset preparation failed');
await mkdir(path.resolve(project, 'build'), { recursive: true });
const bundleDirectory = await mkdtemp(path.resolve(project, 'build/render-'));
const serveUrl = await bundle({
  entryPoint: path.resolve(project, 'src/index.ts'),
  publicDir: path.resolve(project, 'public'),
  outDir: bundleDirectory,
  webpackOverride: config => ({
    ...config,
    // Parallel exports have independent bundles; a shared disk cache races.
    cache: false,
    resolve: {
      ...config.resolve,
      alias: { ...config.resolve?.alias, '@': path.resolve(root, 'apps/web/src') },
    },
  }),
});
const compositions = await getCompositions(serveUrl, {
  browserExecutable: executable,
  inputProps: {},
});
const music = JSON.parse(await readFile(path.resolve(project, 'src/music.json'), 'utf8'));
const filmMusic=JSON.parse(await readFile(path.resolve(project,'src/music-film.json'),'utf8'));
const storyMusic=JSON.parse(await readFile(path.resolve(project,'src/music-v3.json'),'utf8'));
const soundtrackFor=id=>id==='LIA-Story24'?storyMusic:id==='LIA-Proof30'||id.includes('Legacy')?music:filmMusic;
for (const composition of compositions) {
  if (composition.durationInFrames / composition.fps > soundtrackFor(composition.id).durationSeconds) {
    throw new Error(`Soundtrack is shorter than ${composition.id}; rebuild its musical edit first`);
  }
}
await writeFile(
  path.resolve(output, 'compositions.json'),
  JSON.stringify(
    compositions.map(({ id, fps, width, height, durationInFrames }) => ({
      id,
      fps,
      width,
      height,
      durationInFrames,
      generation:id.includes('Legacy')||id==='LIA-Proof30'?'legacy':id==='LIA-Story24'?'story24':PRESENTATION_REVISION,
    })),
    null,
    2
  ) + '\n'
);

{
  const selectors = {
    landing: ['LIA-Landing'],
    full: ['LIA-Full'],
    master25: ['LIA-Master25'],
    all: ['LIA-Landing', 'LIA-Full'],
  };
  const selected =
    mode === 'focus'
      ? compositions.filter(
          composition =>
            composition.id.startsWith('LIA-focus-') &&
            (!requestedFocusIds.length || requestedFocusIds.includes(composition.id))
        )
      : compositions.filter(composition => (selectors[mode] ?? [mode]).includes(composition.id));
  if (selected.length === 0) throw new Error(`Unknown composition selection: ${mode}`);
  for (const id of requestedFocusIds) {
    if (!selected.some(composition => composition.id === id))
      throw new Error(`Unknown focus composition: ${id}`);
  }
  for (const composition of selected) {
    const master = composition.id === 'LIA-Master25';
    const name = composition.id.replace(/^LIA-/, '').toLowerCase();
    const target = path.resolve(output, `${name}.${master ? 'mov' : 'mp4'}`);
    const picture = master ? path.resolve(output, `${name}-picture.mov`) : target;
    let reported = -1;
    await renderMedia({
      composition,
      serveUrl,
      codec: master ? 'prores' : 'h264',
      outputLocation: picture,
      browserExecutable: executable,
      concurrency: Number(process.env.MOTION_CONCURRENCY ?? 4),
      imageFormat: 'png',
      pixelFormat: master ? 'yuv422p10le' : 'yuv420p',
      colorSpace: 'bt709',
      audioCodec: master ? 'pcm-16' : 'aac',
      muted: master,
      sampleRate: 48000,
      ...(master
        ? { proResProfile: 'hq' }
        : { crf: 16, x264Preset: 'medium', audioBitrate: '320k' }),
      logLevel: 'error',
      onProgress: ({ progress }) => {
        const percent = Math.floor(progress * 10) * 10;
        if (percent > reported) {
          console.log(`${composition.id}: ${percent}%`);
          reported = percent;
        }
      },
    });
    if (master) {
      const duration = composition.durationInFrames / composition.fps;
      const originalAudio = path.resolve(project, 'public', soundtrackFor(composition.id).audio);
      const fades = `atrim=duration=${duration},afade=t=in:d=1,afade=t=out:st=${duration - 2}:d=2,`;
      const normalized = measuredLoudnessFilter(['-i', originalAudio], fades);
      runFfmpeg([
        '-i',
        picture,
        '-i',
        originalAudio,
        '-map',
        '0:v:0',
        '-map',
        '1:a:0',
        '-c:v',
        'copy',
        '-af',
        normalized.filter,
        '-c:a',
        'pcm_s24le',
        '-ar',
        '48000',
        '-shortest',
        target,
      ]);
      await writeFile(
        path.resolve(output, `${name}-audio-measurement.json`),
        JSON.stringify(normalized.measurement, null, 2) + '\n'
      );
    }
    console.log(target);
  }
}
