/** A comparable real-time take of each native avatar pair. */
import { chromium } from '@playwright/test';
import { mkdir, readdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import assert from 'node:assert/strict';
import { setTimeout as wait } from 'node:timers/promises';

const argument = name =>
  process.argv.find(value => value.startsWith(`--${name}=`))?.slice(name.length + 3);
const origin = argument('origin') ?? 'http://127.0.0.1:5192';
const output = resolve(
  argument('output') ?? '../../../output/playwright/avatar-finishing-20261108/before'
);
const filter = argument('styles')?.split(',');
const nativeSize = argument('size');
const cold = process.argv.includes('--cold');
const interrupt = process.argv.includes('--interrupt');
const viewport = { width: 1440, height: 900 };
const seed = 0x12345678;
const phaseCueColors = [
  '#2fb344',
  '#ef1f7b',
  '#2d8cec',
  '#f59f00',
  '#7158e2',
  '#007e87',
  '#d9381e',
  '#0f39a8',
  '#803a12',
];
const singleScene = argument('scene');
const scene = singleScene ?? 'body-bow';
const comparisonPhases = [
  { name: 'idle', durationMs: 4200 },
  { name: 'listening', expression: 'attentive', durationMs: 1100 },
  { name: 'thinking', expression: 'thinking', durationMs: 1700 },
  { name: 'speaking', expression: 'speaking', durationMs: 2300 },
  { name: 'return', expression: 'neutral', durationMs: 750 },
  { name: 'bow and recovery', scene, durationMs: 5200 },
];
const phases = singleScene
  ? [
      { name: 'idle', durationMs: 1000 },
      { name: `${scene} and recovery`, scene, durationMs: 6500 },
    ]
  : comparisonPhases;
if (interrupt) {
  assert.ok(!singleScene, 'Interruptions use the common bow comparison');
  phases.push(
    { name: 'second bow', scene, durationMs: 900 },
    { name: 'speech interrupts bow', expression: 'speaking', durationMs: 1600 },
    { name: 'settled after interruption', expression: 'neutral', durationMs: 1600 }
  );
}

assert.match(origin, /^http:\/\/127\.0\.0\.1:\d+$/);
if (nativeSize) assert.ok(['sm', 'md', 'lg', 'xl'].includes(nativeSize), 'Unknown native size');
await mkdir(output, { recursive: true });
assert.equal((await readdir(output)).length, 0, 'Capture output must be empty');
const browser = await chromium.launch({ channel: 'chromium', headless: true });

async function open(style, record) {
  const context = await browser.newContext({
    viewport,
    deviceScaleFactor: 1,
    reducedMotion: 'no-preference',
    serviceWorkers: 'block',
    ...(record ? { recordVideo: { dir: resolve(output, 'video'), size: viewport } } : {}),
  });
  const errors = [];
  const warnings = [];
  try {
    await context.route('**/*', route => {
      const url = new URL(route.request().url());
      if (url.origin === origin && !url.pathname.startsWith('/api/')) return route.continue();
      errors.push(`Blocked unexpected request: ${url.origin}${url.pathname}`);
      return route.abort();
    });
    const page = await context.newPage();
    page.on('pageerror', error => errors.push(error.message));
    page.on('response', response => {
      if (response.status() >= 400) errors.push(`${response.status()} ${response.url()}`);
    });
    page.on('console', message => {
      if (message.type() === 'error') errors.push(message.text());
      if (message.type() === 'warning') warnings.push(message.text());
    });
    await page.addInitScript(initialSeed => {
      let state = initialSeed;
      Math.random = () => {
        state = (Math.imul(state, 1664525) + 1013904223) >>> 0;
        return state / 0x100000000;
      };
    }, seed);
    const parameters = new URLSearchParams({
      take: 'finishing',
      character: style,
      life: 'true',
      size: nativeSize ?? 'xl',
      closeup: String(!nativeSize),
      scene,
      cold: String(cold),
    });
    await page.goto(`${origin}/?${parameters}`);
    const roots = page.locator('[data-live="true"] .lia-eyes');
    await page.waitForFunction(
      wearScarf => {
        const roots = [...document.querySelectorAll('[data-live="true"] .lia-eyes')];
        return (
          roots.length === 2 &&
          roots.every(
            root =>
              root.dataset.volumeReady === 'true' &&
              root.dataset.rigVisible === 'true' &&
              (!wearScarf ||
                (root.dataset.volumeScarfReady === 'true' &&
                  Math.abs(
                    Number(root.style.getPropertyValue('--rig-weather-cold')) -
                      Number(document.querySelector('main').dataset.coldTarget)
                  ) < 0.01))
          )
        );
      },
      cold,
      { polling: 100, timeout: 15000 }
    );
    return { context, page, roots, errors, warnings };
  } catch (error) {
    await context.close();
    throw new Error(`${style}: ${errors.join(' / ')}`, { cause: error });
  }
}

function intervals(values) {
  assert.ok(values.length, 'No rig frames in this phase');
  const sorted = values.toSorted((left, right) => left - right);
  return {
    min: sorted[0],
    p50: sorted[Math.floor(sorted.length * 0.5)],
    p95: sorted[Math.floor(sorted.length * 0.95)],
    max: sorted.at(-1),
  };
}

function analyze(variants, take, timeline, endedAtMs) {
  assert.deepEqual(variants, ['female', 'male']);
  assert.equal(take.frames.length, variants.length);
  return variants.map((variant, index) => {
    const frames = take.frames[index];
    const phaseStats = timeline.map((phase, phaseIndex) => {
      const end = timeline[phaseIndex + 1]?.atMs ?? endedAtMs;
      const rows = frames.filter(frame => frame.atMs >= phase.atMs && frame.atMs < end);
      const ranges = take.trackedChannels.map((channel, channelIndex) => {
        const values = rows.map(row => row.channels[channelIndex]);
        assert.ok(values.every(Number.isFinite), `${variant}/${phase.name}: non-finite ${channel}`);
        return [channel, { min: Math.min(...values), max: Math.max(...values) }];
      });
      return {
        name: phase.name,
        frames: rows.length,
        nativeDeltaMs: intervals(rows.map(row => row.deltaMs)),
        wallIntervalMs: intervals(
          rows.slice(1).map((row, rowIndex) => row.atMs - rows[rowIndex].atMs)
        ),
        channels: Object.fromEntries(ranges),
      };
    });
    assert.ok(
      frames.some(frame => frame.scene === scene),
      `${variant}: ${scene} was never observed`
    );
    assert.equal(frames.at(-1).scene, null, `${variant}: ${scene} did not release`);
    const performance = phaseStats.find(phase => phase.name.endsWith('and recovery')).channels;
    const travel = channel => performance[channel].max - performance[channel].min;
    if (scene === 'body-bow') assert.ok(travel('headPitch') > 0.15, `${variant}: did not bow`);
    else
      assert.ok(
        ['bodyY', 'headPitch', 'bodySx', 'armL', 'armR'].some(channel => travel(channel) > 0.05)
      );
    if (interrupt) {
      const [second, interruption] = timeline.slice(-3);
      assert.ok(
        frames.some(
          frame =>
            frame.atMs >= second.atMs && frame.atMs < interruption.atMs && frame.scene === scene
        )
      );
      const framesDuringInterruption = frames.filter(
        frame => frame.atMs >= interruption.atMs + 150
      );
      assert.ok(
        framesDuringInterruption.every(frame => frame.scene !== scene),
        `${variant}: speech did not interrupt bow`
      );
    }
    const idle = phaseStats[0].channels.mass;
    assert.ok(idle.max - idle.min > 0.0001, `${variant}: idle breathing did not move`);
    if (!singleScene) {
      const speech = phaseStats.find(phase => phase.name === 'speaking').channels.mouthOpen;
      assert.ok(speech.max - speech.min > 0.01, `${variant}: speech did not articulate`);
    }
    return { variant, phases: phaseStats };
  });
}

async function record(style) {
  const { context, page, roots, errors, warnings } = await open(style, true);
  const video = page.video();
  const timeline = [];
  const filename = `${style}.webm`;
  let evidence;
  try {
    for (const [index, phase] of phases.entries()) {
      if (phase.expression) await page.locator('#expression').selectOption(phase.expression);
      if (phase.scene) await page.locator('#play-warm-scene').click();
      const cue = phaseCueColors[index];
      const atMs = await page.evaluate(color => {
        let marker = document.querySelector('#native-take-cue');
        if (!marker) {
          marker = document.createElement('span');
          marker.id = 'native-take-cue';
          marker.setAttribute('aria-hidden', 'true');
          marker.style.cssText =
            'position:fixed;top:0;left:0;width:16px;height:16px;z-index:9999;pointer-events:none';
          document.body.append(marker);
        }
        marker.style.background = color;
        return performance.now();
      }, cue);
      timeline.push({ ...phase, atMs, cue });
      await wait(phase.durationMs);
    }
    const { take, endedAtMs, visibility } = await page.evaluate(() => ({
      take: window.avatarFinishingTake,
      endedAtMs: performance.now(),
      visibility: document.visibilityState,
    }));
    assert.equal(visibility, 'visible');
    const variants = await roots.evaluateAll(elements =>
      elements.map(root => root.closest('[data-variant]').dataset.variant)
    );
    evidence = { style, filename, timeline, endedAtMs, errors, warnings, take, variants };
    evidence.stats = analyze(variants, take, timeline, endedAtMs);
    assert.deepEqual(errors, [], `${style}: unexpected browser errors`);
  } finally {
    await context.close();
    await video.saveAs(resolve(output, filename));
    await video.delete();
    await writeFile(
      resolve(output, `${style}.json`),
      JSON.stringify(evidence ?? { style, timeline, errors, warnings }, null, 2)
    );
  }
  const counts = evidence.stats.map(variant =>
    variant.phases.reduce((sum, phase) => sum + phase.frames, 0)
  );
  process.stdout.write(
    `${style}: ${counts.join('/')} native rig steps, ${errors.length} browser errors\n`
  );
}

try {
  const discovery = await open(filter?.[0] ?? 'bip', false);
  const available = await discovery.page
    .locator('#character option')
    .evaluateAll(options => options.map(option => option.value));
  const availableScenes = await discovery.page
    .locator('#scene option')
    .evaluateAll(options => options.map(option => option.value));
  const graphics = await discovery.roots
    .first()
    .locator('canvas')
    .evaluate(canvas => {
      const gl = canvas.getContext('webgl');
      const debug = gl?.getExtension('WEBGL_debug_renderer_info');
      return gl
        ? {
            version: gl.getParameter(gl.VERSION),
            renderer: gl.getParameter(debug?.UNMASKED_RENDERER_WEBGL ?? gl.RENDERER),
            vendor: gl.getParameter(debug?.UNMASKED_VENDOR_WEBGL ?? gl.VENDOR),
          }
        : null;
    });
  await discovery.context.close();
  assert.deepEqual(discovery.errors, []);
  assert.equal(available.length, 14);
  assert.ok(availableScenes.includes(scene), `Unknown native scene ${scene}`);
  const styles = filter ?? available;
  for (const style of styles)
    assert.ok(available.includes(style), `Unknown native identity ${style}`);
  await writeFile(
    resolve(output, 'take.json'),
    JSON.stringify(
      {
        origin,
        browser: browser.version(),
        graphics,
        viewport,
        seed,
        scene,
        styles,
        phases,
        nativeSize: nativeSize ?? 'xl with fixture closeup (160px em)',
        cold,
        interrupt,
        clock:
          'Native performance.now, Date.now and RAF. The fixture records each delegated native rig step.',
        phaseCue: 'The 16px top-left square marks each input phase in the recorded video.',
        entropy:
          'Fixed browser Math.random and per-rig native life PRNG seeds. Draw counts may differ as code changes.',
        limits:
          'Headless capture load, frame skipping, idle scheduler cadence and clamping affect observed intervals. Browser recording timestamps do not equal rig-step timestamps. Speech is the native speaking expression with no audio.',
      },
      null,
      2
    )
  );
  for (const style of styles) await record(style);
} finally {
  await browser.close();
}
