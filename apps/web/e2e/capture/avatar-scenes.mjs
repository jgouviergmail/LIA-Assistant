/** Named performances through the real hook's rig, scheduler, writer and GPU. */
import { chromium, firefox, webkit } from '@playwright/test';
import { mkdir, readdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { setTimeout as wait } from 'node:timers/promises';

const argument = name =>
  process.argv.find(value => value.startsWith(`--${name}=`))?.slice(name.length + 3);
const output = resolve(
  argument('output') ?? '../../../output/playwright/avatar-artistry/scenes-current'
);
const origin = argument('origin') ?? 'http://127.0.0.1:5188';
const selectedStyles = argument('styles')?.split(',');
const selectedScenes = argument('scenes')?.split(',');
const video = process.argv.includes('--video');
const lifecycle = process.argv.includes('--lifecycle');
const cold = process.argv.includes('--cold');
const closeup = process.argv.includes('--closeup');
const engine = argument('browser') ?? 'chromium';
if (!['chromium', 'firefox', 'webkit'].includes(engine)) throw new Error('Unknown browser engine');
const times = [0, 240, 480, 800, 1200, 1800, 2400, 3200, 4200, 5600, 7200];
const channels = [
  'bodyX',
  'bodyY',
  'bodyRoll',
  'bodySx',
  'bodySy',
  'bodySupport',
  'bodySupportSide',
  'tilt',
  'headYaw',
  'headPitch',
  'mass',
  'weatherCold',
  'ambientSway',
  'armL',
  'armR',
  'wristL',
  'wristR',
  'legL',
  'legR',
  'footL',
  'footR',
];
await mkdir(output, { recursive: true });
if ((await readdir(output)).length) throw new Error('Capture output must be empty');
const browser = await { chromium, firefox, webkit }[engine].launch({
  ...(engine === 'chromium' ? { channel: 'chromium' } : {}),
  headless: true,
});
const records = [];
const errors = [];
const warnings = [];

async function open(style, scene, record = video) {
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 2,
    reducedMotion: 'no-preference',
    ...(record
      ? { recordVideo: { dir: resolve(output, 'video'), size: { width: 1440, height: 900 } } }
      : {}),
  });
  await context.route('**/*', route => {
    const url = new URL(route.request().url());
    if (url.origin === origin && !url.pathname.startsWith('/api/')) return route.continue();
    errors.push(`Blocked unexpected request: ${url.origin}${url.pathname}`);
    return route.abort();
  });
  const page = await context.newPage();
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => {
    if (message.type() === 'error') errors.push(message.text());
    if (message.type() === 'warning') warnings.push(message.text());
  });
  await page.addInitScript(() => {
    let seed = 0x12345678;
    Math.random = () => {
      seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
      return seed / 0x100000000;
    };
  });
  if (!video) {
    await page.clock.install({ time: new Date('2026-11-07T12:00:00Z') });
    await page.clock.pauseAt(await page.evaluate(() => Date.now() + 10_000));
  }
  await page.goto(
    `${origin}/?character=${style}&life=true&size=xl&scene=${scene ?? 'body-hops'}&cold=${cold}&closeup=${closeup}`
  );
  for (let attempt = 0; attempt < (cold ? 160 : 100); attempt++) {
    if (video) await wait(32);
    else await page.clock.runFor(32);
    const ready = await page
      .locator('[data-live="true"] .lia-eyes')
      .evaluateAll(
        (roots, cold) =>
          roots.length === 2 &&
          roots.every(
            root =>
              root.getAttribute('data-volume-ready') === 'true' &&
              (!cold ||
                (root.getAttribute('data-volume-scarf-ready') === 'true' &&
                  Math.abs(
                    parseFloat(root.style.getPropertyValue('--rig-weather-cold')) -
                      Number(document.querySelector('main').dataset.coldTarget)
                  ) < 0.01))
          ),
        cold
      );
    if (ready) return { context, page };
    await wait(30);
  }
  await context.close();
  throw new Error(`${style}: native surface did not become ready`);
}

async function capture(page, style, scene, time, startedAt) {
  const elapsedMs = (await page.evaluate(() => performance.now())) - startedAt;
  const filename = `${style}-${scene}-${String(time).padStart(4, '0')}.png`;
  const pixels = await page.locator('.matrix').screenshot({ path: resolve(output, filename) });
  const poses = await page.locator('[data-live="true"] .lia-eyes').evaluateAll(
    (roots, keys) =>
      roots.map(root => {
        const canvas = root.querySelector('canvas');
        const gl = canvas?.getContext('webgl');
        const program = gl?.getParameter(gl.CURRENT_PROGRAM);
        const nativeJoints = Object.fromEntries(
          keys.slice(-8).map((key, index) => {
            const location = program ? gl.getUniformLocation(program, `u_joints[${index}]`) : null;
            const joint = location ? gl.getUniform(program, location) : null;
            return [key, joint instanceof Float32Array ? [...joint] : null];
          })
        );
        const motion = root.querySelector('.lia-body-motion');
        const shadow = root.querySelector('.lia-head-shadow');
        const head = root.querySelector('.lia-head');
        const figure = root.closest('figure').getBoundingClientRect();
        const matrix = root.closest('.matrix').getBoundingClientRect();
        const left = Math.floor((figure.left - matrix.left) * devicePixelRatio);
        const top = Math.floor((figure.top - matrix.top) * devicePixelRatio);
        return {
          variant: root.closest('[data-variant]')?.getAttribute('data-variant'),
          scene: root.getAttribute('data-scene'),
          visible: root.getAttribute('data-rig-visible'),
          crop: {
            left,
            top,
            width: Math.ceil((figure.right - matrix.left) * devicePixelRatio) - left,
            height: Math.ceil((figure.bottom - matrix.top) * devicePixelRatio) - top,
          },
          channels: Object.fromEntries(
            keys.map(key => [
              key,
              parseFloat(
                root.style.getPropertyValue(
                  `--rig-${key.replace(/[A-Z]/g, value => `-${value.toLowerCase()}`)}`
                )
              ),
            ])
          ),
          nativeJoints,
          transform: motion ? getComputedStyle(motion).transform : null,
          headTransform: head ? getComputedStyle(head).transform : null,
          shadow: shadow
            ? {
                transform: getComputedStyle(shadow).transform,
                opacity: getComputedStyle(shadow).opacity,
              }
            : null,
          surfaceReady: root.getAttribute('data-volume-ready'),
        };
      }),
    channels
  );
  // QA presentation only: the crops retain the exact pixels of the one native screenshot.
  const crops = await page.evaluate(
    async ({ png, boxes }) => {
      const source = new Image();
      source.src = `data:image/png;base64,${png}`;
      await source.decode();
      return boxes.map(box => {
        const canvas = document.createElement('canvas');
        canvas.width = box.width;
        canvas.height = box.height;
        const context = canvas.getContext('2d');
        if (!context) throw new Error('Native screenshot crop context unavailable');
        context.drawImage(
          source,
          box.left,
          box.top,
          box.width,
          box.height,
          0,
          0,
          box.width,
          box.height
        );
        return canvas.toDataURL('image/png').split(',')[1];
      });
    },
    { png: pixels.toString('base64'), boxes: poses.map(pose => pose.crop) }
  );
  await Promise.all(
    poses.map((pose, index) =>
      writeFile(
        resolve(output, `${style}-${pose.variant}-${scene}-${String(time).padStart(4, '0')}.png`),
        Buffer.from(crops[index], 'base64')
      )
    )
  );
  records.push({ style, scene, time, elapsedMs, filename, poses });
  await writeFile(
    resolve(output, 'evidence.json'),
    JSON.stringify(
      {
        browser: browser.version(),
        engine,
        origin,
        instrumentation:
          'Fixture-only factory import wrapper; actual native instances, production hook owns all frames and writes.',
        video,
        cold,
        closeup,
        clock: video
          ? 'Unmodified native browser wall clock and RAF'
          : 'Playwright deterministic browser clock',
        errors,
        warnings,
        records,
      },
      null,
      2
    )
  );
}

async function verifyReducedMotion(page, style, scene) {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  if (video) await wait(100);
  else await page.clock.runFor(64);
  const roots = page.locator('[data-live="true"] .lia-eyes');
  const read = () =>
    roots.evaluateAll(elements =>
      elements.map(root => ({
        style: root.getAttribute('style'),
        ready: root.getAttribute('data-volume-ready'),
      }))
    );
  const before = await read();
  const fixed = await page
    .locator('.matrix')
    .screenshot({ path: resolve(output, `${style}-${scene}-reduced.png`) });
  if (video) await wait(1200);
  else await page.clock.runFor(1200);
  const after = await read();
  const later = await page.locator('.matrix').screenshot();
  if (JSON.stringify(before) !== JSON.stringify(after) || !fixed.equals(later))
    throw new Error(`${engine}/${style}: reduced motion must keep native output fixed`);
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  // Recreating the native surface includes asynchronous texture decoding. Let
  // those real tasks settle while advancing the same production frame clock.
  let resumed = await read();
  let resumePolls = 0;
  while (resumed.some(root => root.ready !== 'true') && resumePolls < 100) {
    await wait(25);
    if (!video) await page.clock.runFor(32);
    resumed = await read();
    resumePolls++;
  }
  await writeFile(
    resolve(output, `${style}-${scene}-lifecycle.json`),
    JSON.stringify(
      { engine, before, after, resumed, resumePolls, identicalPixels: fixed.equals(later) },
      null,
      2
    )
  );
  if (resumed.some(root => root.ready !== 'true'))
    throw new Error(`${engine}/${style}: native surface must resume after reduced motion`);
}

try {
  const discovery = await open(selectedStyles?.[0] ?? 'bip', undefined, false);
  const availableStyles = await discovery.page
    .locator('#character option')
    .evaluateAll(options => options.map(option => option.value));
  const available = await discovery.page
    .locator('#scene option')
    .evaluateAll(options => options.map(option => option.value));
  await discovery.context.close();
  const scenes = selectedScenes ?? available;
  const styles = selectedStyles ?? availableStyles;
  if (scenes.some(scene => !available.includes(scene))) throw new Error('Unknown native scene');
  if (styles.some(style => !availableStyles.includes(style)))
    throw new Error('Unknown native style');
  for (const style of styles)
    for (const scene of scenes) {
      const { context, page } = await open(style, scene);
      const recording = page.video();
      try {
        await page.locator(cold ? '#play-warm-scene' : '#play-scene').click();
        const startedAt = await page.evaluate(() => performance.now());
        if (!video) await page.clock.runFor(16);
        let previous = 0;
        for (const time of times) {
          if (video)
            await wait(
              Math.max(0, time - ((await page.evaluate(() => performance.now())) - startedAt))
            );
          else await page.clock.runFor(time - previous);
          await capture(page, style, scene, time, startedAt);
          previous = time;
        }
        if (
          !records.some(
            record =>
              record.style === style &&
              record.scene === scene &&
              record.poses.every(pose => pose.scene === scene)
          )
        )
          throw new Error(`${style}/${scene}: native scene never played`);
        if (lifecycle) await verifyReducedMotion(page, style, scene);
        process.stdout.write(`${style} ${scene}: ${times.length} native keyframes\n`);
      } finally {
        await context.close();
      }
      if (recording) await recording.saveAs(resolve(output, `${style}-${scene}.webm`));
    }
  if (errors.length) throw new Error(`Unexpected browser errors: ${errors.join('\n')}`);
} finally {
  await browser.close();
}
