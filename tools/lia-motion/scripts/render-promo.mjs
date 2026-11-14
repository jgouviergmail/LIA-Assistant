/**
 * Render the LIA promotional film (`src/promo`, composition `LIA-Promo`).
 *
 *   node scripts/render-promo.mjs stills 120 480 900     # review stills
 *   node scripts/render-promo.mjs sheet 0 4919 60         # contact sheet every 60 frames
 *   node scripts/render-promo.mjs render                  # silent video, all frames
 *   node scripts/render-promo.mjs render 2880 4319        # one range only
 *   node scripts/render-promo.mjs audio                   # music + effects mix, -14 LUFS / -1.5 dBTP
 *   node scripts/render-promo.mjs mux                     # final MP4 + measurements
 *   node scripts/render-promo.mjs web                     # lighter review/web encode (CRF 20)
 *
 * Exports go to exports/lia-motion/promo/ (ignored by Git). No render contacts
 * a LIA account or a provider: every screen and datum is fictitious.
 */
import { bundle } from '@remotion/bundler';
import { getCompositions, openBrowser, renderMedia, renderStill } from '@remotion/renderer';
import { mkdir, readFile, writeFile, readdir } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { spawnSync } from 'node:child_process';

const project = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const root = path.resolve(project, '../..');
const output = path.join(root, 'exports/lia-motion/promo');
const mode = process.argv[2] ?? 'stills';
const args = process.argv.slice(3).map(Number);
const SECONDS = 114;
const FRAMES = SECONDS * 60;
await mkdir(path.join(output, 'stills'), { recursive: true });
await mkdir(path.join(output, 'chunks'), { recursive: true });

function run(executable, argv) {
  const result = spawnSync(executable, argv, { encoding: 'utf8', windowsHide: true, maxBuffer: 64 * 1024 * 1024 });
  if (result.status !== 0) throw new Error(`${executable} ${argv.join(' ')}\n${result.stderr}`);
  return `${result.stdout}${result.stderr}`;
}

async function serve() {
  return bundle({
    entryPoint: path.join(project, 'src/promo/index.tsx'),
    publicDir: path.join(project, 'public'),
    outDir: path.join(project, process.env.PROMO_BUILD_DIR ?? 'build/promo'),
    webpackOverride: (config) => {
      function visit(rules) {
        for (const rule of rules ?? []) {
          if (!rule || typeof rule !== 'object') continue;
          visit(rule.oneOf);
          visit(rule.rules);
          for (const use of Array.isArray(rule.use) ? rule.use : rule.use ? [rule.use] : []) {
            if (use && typeof use === 'object' && /[\\/]css-loader[\\/]/.test(use.loader ?? '')) {
              use.options = { ...use.options, url: { filter: (url) => !url.startsWith('/') }, sourceMap: false };
            }
          }
        }
      }
      visit(config.module?.rules);
      return { ...config, cache: false, resolve: { ...config.resolve, alias: { ...config.resolve?.alias, '@': path.join(root, 'apps/web/src') } } };
    },
  });
}

async function withBrowser(fn) {
  const browserExecutable =
    process.env.REMOTION_BROWSER_EXECUTABLE ??
    path.join(project, 'node_modules/.remotion/chrome-headless-shell/win64/chrome-headless-shell-win64/chrome-headless-shell.exe');
  const serveUrl = await serve();
  const browser = await openBrowser('chrome', { browserExecutable, logLevel: 'error' });
  try {
    const inputProps = { withAudio: false };
    const [composition] = await getCompositions(serveUrl, { puppeteerInstance: browser, inputProps });
    if (composition.durationInFrames !== FRAMES || composition.fps !== 60) throw new Error(`LIA-Promo must be ${FRAMES} frames at 60 fps`);
    await fn({ serveUrl, browser, composition, inputProps });
  } finally {
    await browser.close({ silent: true });
  }
}

async function stills(frames) {
  await withBrowser(async ({ serveUrl, browser, composition, inputProps }) => {
    for (const frame of frames) {
      const destination = path.join(output, 'stills', `f${String(frame).padStart(4, '0')}.png`);
      await renderStill({ composition, serveUrl, inputProps, frame, output: destination, imageFormat: 'png', puppeteerInstance: browser, logLevel: 'error', timeoutInMilliseconds: 120000 });
      console.log(`still ${frame} -> ${destination}`);
    }
  });
}

async function inspect(from = 0, to = FRAMES - 1, step = 15) {
  // Layout audit: every `step` frames, list texts that overflow, touch an edge or overlap.
  const report = [];
  await withBrowser(async ({ serveUrl, browser, composition }) => {
    const inputProps = { withAudio: false, inspect: true };
    const scratch = path.join(output, 'stills', '_inspect.png');
    for (let frame = from; frame <= to; frame += step) {
      await renderStill({
        composition: { ...composition, props: inputProps }, serveUrl, inputProps, frame, output: scratch, imageFormat: 'png',
        puppeteerInstance: browser, logLevel: 'error', timeoutInMilliseconds: 120000,
        onBrowserLog: (log) => {
          if (log.text.startsWith('INSPECT ')) report.push(JSON.parse(log.text.slice(8)));
        },
      });
    }
  });
  await writeFile(path.join(output, 'inspect.json'), `${JSON.stringify(report, null, 1)}\n`);
  const summary = new Map();
  for (const { frame, issues } of report) {
    for (const issue of issues) {
      const key = `${issue.kind} | ${issue.text}${issue.with ? ` <> ${issue.with}` : ''} | ${issue.in ?? ''}`;
      const entry = summary.get(key) ?? { frames: [], worst: 0 };
      entry.frames.push(frame);
      entry.worst = Math.max(entry.worst, issue.by ?? issue.share ?? (issue.distance !== undefined ? 24 - issue.distance : 0) ?? 0);
      summary.set(key, entry);
    }
  }
  const lines = [...summary.entries()].sort((a, b) => a[1].frames[0] - b[1].frames[0])
    .map(([key, { frames, worst }]) => `${String(frames[0]).padStart(4)}-${String(frames.at(-1)).padStart(4)} (${frames.length}x, worst ${worst}) ${key}`);
  await writeFile(path.join(output, 'inspect-summary.txt'), `${lines.join('\n')}\n`);
  console.log(lines.join('\n'));
}

async function render(from = 0, to = FRAMES - 1) {
  await withBrowser(async ({ serveUrl, browser, composition, inputProps }) => {
    const destination = path.join(output, 'chunks', `promo-${String(from).padStart(4, '0')}-${String(to).padStart(4, '0')}.mp4`);
    let last = -1;
    const started = Date.now();
    await renderMedia({
      composition, serveUrl, inputProps, outputLocation: destination, frameRange: [from, to],
      codec: 'h264', imageFormat: 'jpeg', jpegQuality: 96, pixelFormat: 'yuv420p', colorSpace: 'bt709', crf: 14, muted: true,
      concurrency: Number(process.env.PROMO_CONCURRENCY ?? 12), puppeteerInstance: browser, timeoutInMilliseconds: 180000,
      logLevel: 'warn', overwrite: true,
      onProgress: ({ progress }) => {
        const step = Math.floor(progress * 20);
        if (step > last) { last = step; console.log(`${(progress * 100).toFixed(0)}% (${((Date.now() - started) / 1000).toFixed(0)} s)`); }
      },
    });
    console.log(`rendered ${destination}`);
  });
}

async function audio() {
  // Mix the music with every effect cue, then normalise to -14 LUFS / -1 dBTP (two passes).
  const { SFX_CUES: SFX, DUCKS } = await import(pathToFileURL(path.join(project, 'src/promo/sound.ts')).href);
  const { MUSIC_EDIT } = await import(pathToFileURL(path.join(project, 'src/promo/timing.ts')).href);
  // The bed follows MUSIC_EDIT: one decoded input per span (inputs 0..n-1), joined on bar lines with
  // 10 ms equal-power crossfades, each span padded by 5 ms so the timeline stays exact.
  const pad = 0.005;
  const spans = MUSIC_EDIT.map((span, i) => {
    const start = i === 0 ? span.from : span.from - pad;
    const end = span.to === null ? '' : `:end=${(span.to + pad).toFixed(3)}`;
    return `[${i}:a]atrim=start=${start.toFixed(3)}${end},asetpts=PTS-STARTPTS[bed${i}]`;
  });
  let bed = spans.join(';');
  let last = 'bed0';
  for (let i = 1; i < MUSIC_EDIT.length; i++) {
    bed += `;[${last}][bed${i}]acrossfade=d=${(2 * pad).toFixed(3)}:c1=qsin:c2=qsin[bedj${i}]`;
    last = `bedj${i}`;
  }
  // Music gain: product of smooth dips (20 ms in, 250 ms hold, 120 ms out) around each gesture.
  const dip = DUCKS.map(({ frame, gain }) => {
    const t = frame / 60;
    const a = (t - 0.05).toFixed(3);
    const b = (t + 0.25).toFixed(3);
    const depth = (1 - gain).toFixed(3);
    return `(1-${depth}*min(1,max(0,(t-${a})/0.02))*min(1,max(0,(${b}+0.12-t)/0.12)))`;
  }).join('*');
  const music = path.join(project, 'public/audio/promo/lia-promo-music.mp3');
  const inputs = MUSIC_EDIT.flatMap(() => ['-i', music]);
  const filters = [];
  SFX.forEach((cue, i) => {
    inputs.push('-i', path.join(project, `public/audio/promo/sfx/${cue.sound}.mp3`));
    const ms = Math.round((cue.frame / 60) * 1000);
    filters.push(`[${i + MUSIC_EDIT.length}:a]aresample=48000,volume=${cue.volume},adelay=${ms}|${ms}[fx${i}]`);
  });
  // The bed sits 1.4 dB under unity so stacked effects never exceed full scale before normalisation.
  const mixInputs = [`${bed};[${last}]aresample=48000,volume=0.85,volume='${dip}':eval=frame[m]`, ...filters];
  const labels = ['[m]', ...SFX.map((_, i) => `[fx${i}]`)].join('');
  const graph = `${mixInputs.join(';')};${labels}amix=inputs=${SFX.length + 1}:duration=first:normalize=0,atrim=0:${SECONDS}[mix]`;
  const premix = path.join(output, 'premix.wav');
  // Float premix: an intermediate above full scale is kept, never clipped; loudnorm then limits true peaks.
  run('ffmpeg', ['-hide_banner', '-loglevel', 'error', '-y', ...inputs, '-filter_complex', graph, '-map', '[mix]', '-ar', '48000', '-ac', '2', '-c:a', 'pcm_f32le', premix]);
  const probe = run('ffmpeg', ['-hide_banner', '-i', premix, '-af', 'loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json', '-f', 'null', '-']);
  const json = JSON.parse(probe.slice(probe.lastIndexOf('{'), probe.lastIndexOf('}') + 1));
  const final = path.join(output, 'mix.wav');
  run('ffmpeg', ['-hide_banner', '-loglevel', 'error', '-y', '-i', premix, '-af',
    `loudnorm=I=-14:TP=-1.5:LRA=11:measured_I=${json.input_i}:measured_TP=${json.input_tp}:measured_LRA=${json.input_lra}:measured_thresh=${json.input_thresh}:offset=${json.target_offset}:linear=true`,
    '-ar', '48000', '-c:a', 'pcm_s24le', final]);
  console.log(`mix ${final} (input ${json.input_i} LUFS, ${json.input_tp} dBTP)`);
}

async function mux() {
  const chunks = (await readdir(path.join(output, 'chunks'))).filter((n) => n.endsWith('.mp4')).sort();
  const list = path.join(output, 'chunks.txt');
  await writeFile(list, chunks.map((n) => `file '${path.join(output, 'chunks', n).replaceAll('\\', '/')}'`).join('\n') + '\n');
  const master = path.join(output, 'lia-promo-fr-1080p60.mp4');
  run('ffmpeg', ['-hide_banner', '-loglevel', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', list, '-i', path.join(output, 'mix.wav'),
    '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '256k', '-ar', '48000', '-t', String(SECONDS), '-movflags', '+faststart', master]);
  const meta = JSON.parse(run('ffprobe', ['-v', 'error', '-show_streams', '-show_format', '-count_frames', '-of', 'json', master]));
  const video = meta.streams.find((s) => s.codec_type === 'video');
  const bytes = await readFile(master);
  const report = {
    file: path.basename(master),
    sha256: createHash('sha256').update(bytes).digest('hex'),
    bytes: bytes.length,
    width: video.width, height: video.height, fps: video.r_frame_rate, frames: Number(video.nb_read_frames),
    duration: Number(meta.format.duration),
  };
  await writeFile(path.join(output, 'verification.json'), JSON.stringify(report, null, 2) + '\n');
  console.log(report);
}

async function web() {
  // Review/web encode: H.264 CRF 20, 2-second closed GOPs, Rec.709 tags; audio straight from the clean mix.
  const master = path.join(output, 'lia-promo-fr-1080p60.mp4');
  const destination = path.join(output, 'lia-promo-fr-1080p60-web.mp4');
  run('ffmpeg', ['-hide_banner', '-loglevel', 'error', '-y', '-i', master, '-i', path.join(output, 'mix.wav'),
    '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'libx264', '-preset', 'slow', '-crf', '20', '-profile:v', 'high', '-level', '4.2',
    '-pix_fmt', 'yuv420p', '-g', '120', '-keyint_min', '120', '-sc_threshold', '0', '-x264-params', 'open-gop=0',
    '-color_primaries', 'bt709', '-color_trc', 'bt709', '-colorspace', 'bt709',
    '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-t', String(SECONDS), '-movflags', '+faststart', destination]);
  const bytes = await readFile(destination);
  console.log({ file: path.basename(destination), bytes: bytes.length, sha256: createHash('sha256').update(bytes).digest('hex') });
}

if (mode === 'stills') await stills(args.length ? args : [30, 200, 400, 470, 500, 560, 650]);
else if (mode === 'sheet') {
  const [from = 0, to = FRAMES - 1, step = 60] = args;
  const frames = [];
  for (let f = from; f <= to; f += step) frames.push(f);
  await stills(frames);
} else if (mode === 'render') await render(args[0] ?? 0, args[1] ?? FRAMES - 1);
else if (mode === 'inspect') await inspect(args[0] ?? 0, args[1] ?? FRAMES - 1, args[2] ?? 15);
else if (mode === 'audio') await audio();
else if (mode === 'mux') await mux();
else if (mode === 'web') await web();
else throw new Error('Use stills, sheet, inspect, render, audio, mux or web');
