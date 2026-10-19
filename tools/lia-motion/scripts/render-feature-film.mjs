import { bundle } from '@remotion/bundler';
import { getCompositions, openBrowser, renderMedia, renderStill } from '@remotion/renderer';
import { mkdir, readFile, writeFile, copyFile, access } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';

const project = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const root = path.resolve(project, '../..');
const output = path.join(root, 'exports/lia-motion/feature-film-80s');
const score = JSON.parse(await readFile(path.join(project, 'public/audio/feature-film/score.json'), 'utf8'));
const cuts = score.cues.map(cue => cue.frame);
const names = ['opening', 'day', 'context', 'approval', 'voice', 'memory', 'meetings', 'routines', 'skills', 'radio', 'closing'];
const mode = process.argv[2] ?? 'stills';
if (!['stills', 'render', 'assemble', 'all'].includes(mode)) throw new Error('Use stills, render [chapter...], assemble or all');
await mkdir(path.join(output, 'shots'), { recursive: true });

function command(executable, args) {
  const result = spawnSync(executable, args, { encoding: 'utf8', windowsHide: true });
  if (result.status !== 0) throw new Error(`${executable}: ${result.stderr}`);
  return result.stdout;
}

async function assemble() {
  const files = names.map((name, index) => path.join(output, 'shots', `${String(index).padStart(2, '0')}-${name}.mp4`));
  await Promise.all(files.map(file => access(file)));
  const list = path.join(output, 'shots.txt');
  await writeFile(list, files.map(file => `file '${file.replaceAll('\\', '/').replaceAll("'", "'\\''")}'`).join('\n') + '\n');
  const destination = path.join(output, 'lia-feature-film-1080p60.mp4');
  command('ffmpeg', ['-hide_banner', '-loglevel', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', list,
    '-i', path.join(project, 'public/audio/feature-film/lia-feature-film-80s.wav'),
    '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '320k', '-ar', '48000', '-t', '80', '-movflags', '+faststart', destination]);
  const metadata = JSON.parse(command('ffprobe', ['-v', 'error', '-show_streams', '-show_format', '-of', 'json', destination]));
  const video = metadata.streams.find(stream => stream.codec_type === 'video');
  const audio = metadata.streams.find(stream => stream.codec_type === 'audio');
  if (video?.r_frame_rate !== '60/1' || Number(video?.nb_frames) !== 4800 || video.width !== 1920 || video.height !== 1080 || audio?.sample_rate !== '48000') {
    throw new Error('Export must be 1920x1080, 4800 frames, 60 fps, stereo AAC 48k');
  }
  const bytes = await readFile(destination);
  metadata.sha256 = createHash('sha256').update(bytes).digest('hex');
  metadata.fileBytes = bytes.length;
  metadata.cuts = cuts;
  metadata.chapters = names;
  metadata.audioProvenance = score;
  await writeFile(path.join(output, 'verification.json'), JSON.stringify(metadata, null, 2) + '\n');
  console.log(`Verified ${destination} (${bytes.length} bytes, 80s, 60fps, 4800 frames)`);
}

if (mode === 'assemble') { await assemble(); process.exit(0); }
await mkdir(path.join(project, 'public/film'), { recursive: true });
await copyFile(path.join(root, 'apps/web/public/icon.svg'), path.join(project, 'public/film/icon.svg'));
await copyFile(path.join(root, 'apps/web/public/avatars/bip/v1/male/body.webp'), path.join(project, 'public/film/bip-body.webp'));
await copyFile(path.join(root, 'apps/web/e2e/fixtures/fonts/MaterialSymbolsOutlined.woff2'), path.join(project, 'public/film/MaterialSymbolsOutlined.woff2'));
for (const asset of ['eye.webp', 'eye-right.webp', 'iris.webp', 'sclera-mask.webp', 'sclera-mask-right.webp']) {
  await copyFile(path.join(root, 'apps/web/public/avatars/spirit/v1/male', asset), path.join(project, 'public/film', asset));
}
const browserExecutable = process.env.REMOTION_BROWSER_EXECUTABLE ?? path.join(project, 'node_modules/.remotion/chrome-headless-shell/win64/chrome-headless-shell-win64/chrome-headless-shell.exe');
const serveUrl = await bundle({
  entryPoint: path.join(project, 'src/film/index.tsx'), publicDir: path.join(project, 'public'), outDir: path.join(project, 'build/feature-film'),
  webpackOverride: config => {
    function visit(rules) {
      for (const rule of rules ?? []) {
        if (!rule || typeof rule !== 'object') continue;
        visit(rule.oneOf); visit(rule.rules);
        for (const use of Array.isArray(rule.use) ? rule.use : rule.use ? [rule.use] : []) {
          if (use && typeof use === 'object' && /[\\/]css-loader[\\/]/.test(use.loader ?? '')) use.options = { ...use.options, url: { filter: url => !url.startsWith('/') }, sourceMap: false };
        }
      }
    }
    visit(config.module?.rules);
    return { ...config, cache: false, resolve: { ...config.resolve, alias: { ...config.resolve?.alias, '@': path.join(root, 'apps/web/src') } } };
  },
});
const browser = await openBrowser('chrome', { browserExecutable, logLevel: 'error' });
try {
  const inputProps = { withAudio: false };
  const [composition] = await getCompositions(serveUrl, { puppeteerInstance: browser, inputProps });
  if (composition.fps !== 60 || composition.durationInFrames !== 4800) throw new Error('Film must contain 4800 frames at 60fps');
  await writeFile(path.join(output, 'composition.json'), JSON.stringify({ id: composition.id, width: composition.width, height: composition.height, fps: 60, frames: 4800, durationSeconds: 80, chapters: names, cuts, fictionalData: true, oldCreativeAssetsUsed: false }, null, 2) + '\n');
  if (mode === 'stills') {
    const frames = process.argv.slice(3).length ? process.argv.slice(3).map(Number) : [110, 385, 546, 839, 1071, 1367, 1629, 1840, 2081, 2335, 2578, 2742, 3053, 3286, 3511, 3732, 3999, 4210, 4411, 4680];
    for (const frame of frames) {
      if (!Number.isInteger(frame) || frame < 0 || frame >= 4800) throw new Error(`Invalid frame ${frame}`);
      const destination = path.join(output, `frame-${String(frame).padStart(4, '0')}.png`);
      await renderStill({ composition, serveUrl, inputProps, frame, output: destination, imageFormat: 'png', puppeteerInstance: browser, logLevel: 'error', timeoutInMilliseconds: 60000 });
      console.log(`Still ${frame}: ${destination}`);
    }
  } else {
    const selected = process.argv.slice(3);
    for (const name of selected) if (!names.includes(name)) throw new Error(`Unknown chapter ${name}`);
    for (const [index, name] of names.entries()) {
      if (selected.length && !selected.includes(name)) continue;
      const destination = path.join(output, 'shots', `${String(index).padStart(2, '0')}-${name}.mp4`);
      let lastProgress = -1;
      await renderMedia({ composition, serveUrl, inputProps, outputLocation: destination, frameRange: [cuts[index], cuts[index + 1] - 1],
        codec: 'h264', imageFormat: 'png', pixelFormat: 'yuv420p', colorSpace: 'bt709', crf: 16, muted: true,
        concurrency: 4, puppeteerInstance: browser, timeoutInMilliseconds: 90000, logLevel: 'warn', overwrite: true,
        onProgress: ({ progress }) => { const value = Math.floor(progress * 4); if (value > lastProgress) { lastProgress = value; console.log(`${name}: ${value * 25}%`); } },
      });
      console.log(`Rendered ${name}: ${cuts[index + 1] - cuts[index]} frames`);
    }
  }
} finally { await browser.close({ silent: true }); }
if (mode === 'all') await assemble();
