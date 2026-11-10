/** Native scarf audit: real environment context, component, rig, textures and GPU. */
import { chromium, firefox, webkit } from '@playwright/test';
import { measureScarfProjection } from './scarf-projection.mjs';
import { mkdir, readdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { setTimeout as wait } from 'node:timers/promises';

const argument = name =>
  process.argv
    .find(value => value.startsWith(`--${name}=`))
    ?.split('=')
    .slice(1)
    .join('=');
const output = resolve(argument('output') ?? '../../../output/playwright/avatar-artistry/before');
const origin = argument('origin') ?? 'http://127.0.0.1:5188';
const theme = argument('theme') ?? 'light';
if (!['light', 'dark'].includes(theme)) throw new Error('Unknown native theme');
const size = argument('size') ?? 'xl';
if (!['sm', 'md', 'lg', 'xl'].includes(size)) throw new Error('Unknown native size');
const selected = argument('styles')?.split(',');
const diagnostics = process.argv.includes('--diagnostics');
const closeup = process.argv.includes('--closeup');
const quick = process.argv.includes('--quick');
const fade = process.argv.includes('--fade');
const trail = process.argv.includes('--trail');
const engine = argument('browser') ?? 'chromium';
if (!['chromium', 'firefox', 'webkit'].includes(engine)) throw new Error('Unknown browser engine');
await mkdir(output, { recursive: true });
if ((await readdir(output)).length > 0)
  throw new Error('Capture output must be empty; preserve previous visual evidence');
const browser = await { chromium, firefox, webkit }[engine].launch({
  ...(engine === 'chromium' ? { channel: 'chromium' } : {}),
  headless: true,
});
const records = [];
const errors = [];
const warnings = [];

async function open(style = 'bip') {
  const context = await browser.newContext({
    viewport: { width: 1440, height: closeup ? 1200 : 900 },
    deviceScaleFactor: 2,
    reducedMotion: 'no-preference',
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
    const textures = new WeakMap();
    const frames = new WeakMap();
    const uploadTexture = WebGLRenderingContext.prototype.texImage2D;
    WebGLRenderingContext.prototype.texImage2D = function (...args) {
      const result = uploadTexture.apply(this, args);
      const image = args.at(-1);
      const texture = this.getParameter(this.TEXTURE_BINDING_2D);
      if (texture && image instanceof HTMLImageElement)
        textures.set(texture, new URL(image.currentSrc || image.src, location.href).pathname);
      return result;
    };
    const upload = WebGLRenderingContext.prototype.bufferData;
    WebGLRenderingContext.prototype.bufferData = function (...args) {
      const result = upload.apply(this, args);
      if (this.canvas instanceof HTMLCanvasElement)
        this.canvas.dataset.auditBufferUploads = String(
          Number(this.canvas.dataset.auditBufferUploads ?? 0) + 1
        );
      return result;
    };
    const draw = WebGLRenderingContext.prototype.drawElements;
    WebGLRenderingContext.prototype.drawElements = function (...args) {
      const canvas = this.canvas;
      if (canvas instanceof HTMLCanvasElement) {
        canvas.dataset.auditDraws = String(Number(canvas.dataset.auditDraws ?? 0) + 1);
        canvas.dataset.auditLastDepth = JSON.stringify([
          this.getParameter(this.DEPTH_FUNC),
          this.getParameter(this.DEPTH_WRITEMASK),
          canvas.dataset.auditScarfSample,
        ]);
      }
      const texturePath = textures.get(this.getParameter(this.TEXTURE_BINDING_2D));
      const scarfDraw = texturePath?.startsWith('/avatars/scarf/');
      const sampling =
        canvas instanceof HTMLCanvasElement &&
        canvas.dataset.auditScarfSample === 'true' &&
        scarfDraw;
      // The real body draw starts a frame. Its unchanged framebuffer is the
      // baseline for every subsequent cloth pass, including the depth-tested
      // ribbon and knot. Hidden back cloth never appears in the difference.
      if (canvas instanceof HTMLCanvasElement && !scarfDraw) frames.delete(canvas);
      let before = sampling ? frames.get(canvas)?.pixels : null;
      if (sampling && !before) {
        before = new Uint8Array(canvas.width * canvas.height * 4);
        this.readPixels(0, 0, canvas.width, canvas.height, this.RGBA, this.UNSIGNED_BYTE, before);
        frames.set(canvas, { pixels: before, passes: [] });
      }
      const result = draw.apply(this, args);
      if (before) {
        const program = this.getParameter(this.CURRENT_PROGRAM);
        const uniform = program ? this.getUniformLocation(program, 'u_drape') : null;
        const drape = uniform ? this.getUniform(program, uniform) : null;
        frames.get(canvas).passes.push({
          texturePath,
          depth: this.getParameter(this.DEPTH_FUNC),
          writesDepth: this.getParameter(this.DEPTH_WRITEMASK),
          drape: drape instanceof Float32Array ? [...drape] : null,
        });
        const after = new Uint8Array(before.length);
        this.readPixels(0, 0, canvas.width, canvas.height, this.RGBA, this.UNSIGNED_BYTE, after);
        const box = canvas.getBoundingClientRect();
        const mouth = canvas
          .closest('.lia-eyes')
          ?.querySelector('[data-rig-mouth]')
          ?.getBoundingClientRect();
        const mouthBox = mouth
          ? {
              left: ((mouth.left - box.left) / box.width) * canvas.width,
              top: ((mouth.top - box.top) / box.height) * canvas.height,
              right: ((mouth.right - box.left) / box.width) * canvas.width,
              bottom: ((mouth.bottom - box.top) / box.height) * canvas.height,
            }
          : null;
        let minX = canvas.width,
          minY = canvas.height,
          maxX = -1,
          maxY = -1,
          pixels = 0,
          mouthOverlap = 0;
        for (let y = 0; y < canvas.height; y++)
          for (let x = 0; x < canvas.width; x++) {
            const offset = (y * canvas.width + x) * 4;
            if (
              Math.abs(after[offset] - before[offset]) < 8 &&
              Math.abs(after[offset + 1] - before[offset + 1]) < 8 &&
              Math.abs(after[offset + 2] - before[offset + 2]) < 8 &&
              Math.abs(after[offset + 3] - before[offset + 3]) < 8
            )
              continue;
            const topY = canvas.height - 1 - y;
            pixels++;
            minX = Math.min(minX, x);
            maxX = Math.max(maxX, x);
            minY = Math.min(minY, topY);
            maxY = Math.max(maxY, topY);
            if (
              mouthBox &&
              x >= mouthBox.left &&
              x <= mouthBox.right &&
              topY >= mouthBox.top &&
              topY <= mouthBox.bottom
            )
              mouthOverlap++;
          }
        canvas.dataset.auditScarfRaster = JSON.stringify({
          draw: Number(canvas.dataset.auditDraws),
          width: canvas.width,
          height: canvas.height,
          pixels,
          minX,
          minY,
          maxX,
          maxY,
          mouthBox,
          mouthOverlap,
          passes: frames.get(canvas).passes,
          method:
            'RGBA difference >=8 from the actual body framebuffer through all native scarf-texture draws, retaining native depth occlusion',
        });
      }
      return result;
    };
    let seed = 0x12345678;
    Math.random = () => {
      seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
      return seed / 0x100000000;
    };
  });
  await page.clock.install({ time: new Date('2026-11-07T12:00:00Z') });
  await page.clock.pauseAt(await page.evaluate(() => Date.now() + 10_000));
  await page.goto(
    `${origin}/?character=${style}&cold=true&life=true&size=${size}&closeup=${closeup}&theme=${theme}`
  );
  for (let attempt = 0; attempt < 160; attempt++) {
    await page.clock.runFor(64);
    const ready = await page.evaluate(() => {
      const roots = [...document.querySelectorAll('[data-live="true"] .lia-eyes')];
      const target = Number(document.querySelector('main')?.getAttribute('data-cold-target'));
      return (
        roots.length === 2 &&
        roots.every(
          root =>
            root.getAttribute('data-volume-scarf-ready') === 'true' &&
            Math.abs(parseFloat(root.style.getPropertyValue('--rig-weather-cold')) - target) < 0.01
        )
      );
    });
    if (ready) return { context, page };
    await wait(30);
  }
  await page.screenshot({ path: resolve(output, `${style}-not-ready.png`), fullPage: true });
  await context.close();
  throw new Error(`${style}: native cold scarf did not become ready`);
}

async function armRaster(page) {
  await page.locator('[data-live="true"] canvas').evaluateAll(canvases => {
    for (const canvas of canvases) {
      if (canvas.dataset.auditScarfSample === 'true') continue;
      canvas.dataset.auditScarfSample = 'true';
      canvas.dataset.auditBufferStart = canvas.dataset.auditBufferUploads ?? '0';
      canvas.dataset.auditDrawStart = canvas.dataset.auditDraws ?? '0';
      delete canvas.dataset.auditScarfRaster;
    }
  });
}

async function capture(page, style, scenario, advance = true) {
  const fallbackScenario = scenario === 'context-lost' || scenario.startsWith('fallback-');
  await armRaster(page);
  let sampleMs = 0;
  for (let attempt = 0; attempt < (advance ? (fallbackScenario ? 1 : 32) : 0); attempt++) {
    await page.clock.runFor(32);
    sampleMs += 32;
    const painted = await page
      .locator('[data-live="true"] canvas')
      .evaluateAll(canvases => canvases.every(canvas => !!canvas.dataset.auditScarfRaster));
    if (painted) break;
  }
  const filename = `${style}-${scenario}.png`;
  const beforeScreenshot = await page.locator('[data-live="true"] canvas').evaluateAll(canvases =>
    canvases.map(canvas => ({
      uploads: Number(canvas.dataset.auditBufferUploads ?? 0),
      start: Number(canvas.dataset.auditBufferStart ?? 0),
      draws: Number(canvas.dataset.auditDraws ?? 0),
    }))
  );
  await page.locator('main').screenshot({ path: resolve(output, filename) });
  const poses = await page.locator('[data-live="true"] .lia-eyes').evaluateAll(roots =>
    roots.map(root => {
      const canvas = root.querySelector('canvas');
      const gl = canvas?.getContext('webgl');
      const program = gl?.getParameter(gl.CURRENT_PROGRAM);
      const poseLocation = program ? gl.getUniformLocation(program, 'u_pose') : null;
      const pose = poseLocation ? gl.getUniform(program, poseLocation) : null;
      const drapeLocation = program ? gl.getUniformLocation(program, 'u_drape') : null;
      const drape = drapeLocation ? gl.getUniform(program, drapeLocation) : null;
      const scarf = root.querySelector('.lia-ambient-weather--cold');
      const css = scarf ? getComputedStyle(scarf) : null;
      const facetProjection = [];
      const splitContinuity = [];
      const ancestorProjection = [];
      for (let node = scarf; node && node !== root.parentElement; node = node.parentElement) {
        const value = getComputedStyle(node),
          box = node.getBoundingClientRect();
        ancestorProjection.push({
          className: node.className,
          transform: value.transform,
          perspective: value.perspective,
          preserve: value.transformStyle,
          filter: value.filter,
          box: { x: box.x, y: box.y, width: box.width, height: box.height },
        });
      }
      const channel = key => parseFloat(root.style.getPropertyValue(`--rig-${key}`));
      if (canvas) delete canvas.dataset.auditScarfSample;
      return {
        variant: root.closest('[data-variant]')?.getAttribute('data-variant'),
        volumeReady: root.getAttribute('data-volume-ready'),
        scarfReady: root.getAttribute('data-volume-scarf-ready'),
        cold: channel('weather-cold'),
        trail: channel('scarf-trail'),
        yaw: channel('head-yaw'),
        pitch: channel('head-pitch'),
        paintedPose: pose instanceof Float32Array ? [...pose] : null,
        paintedDrape: drape instanceof Float32Array ? [...drape] : null,
        facetProjection,
        splitContinuity,
        mass: channel('mass'),
        scarfDescendants: [...root.querySelectorAll('.lia-ambient-weather--cold')].reduce(
          (sum, element) => sum + element.querySelectorAll('*').length + 1,
          0
        ),
        ancestorProjection,
        scarfRaster: canvas?.dataset.auditScarfRaster
          ? JSON.parse(canvas.dataset.auditScarfRaster)
          : null,
        sampleBufferUploads:
          Number(canvas?.dataset.auditBufferUploads ?? 0) -
          Number(canvas?.dataset.auditBufferStart ?? 0),
        sampleDraws:
          Number(canvas?.dataset.auditDraws ?? 0) - Number(canvas?.dataset.auditDrawStart ?? 0),
        nativeDraw: Number(canvas?.dataset.auditDraws ?? 0),
        lastDepth: canvas?.dataset.auditLastDepth,
        sampleFlag: canvas?.dataset.auditScarfSample,
        fallback: css
          ? {
              visibility: css.visibility,
              opacity: css.opacity,
              width: css.width,
              height: css.height,
              transform: css.transform,
            }
          : null,
        time: Date.now(),
      };
    })
  );
  if (fallbackScenario) {
    const projected = await measureScarfProjection(page, style);
    for (const pose of poses) {
      const geometry = projected.find(value => value.variant === pose.variant);
      if (geometry) Object.assign(pose, geometry);
    }
  }
  if (
    poses.length !== 2 ||
    !['female', 'male'].every(variant => poses.some(pose => pose.variant === variant))
  )
    throw new Error(`${style}/${scenario}: both native variant roots must remain mounted`);
  if (
    !fallbackScenario &&
    poses.some(
      pose =>
        pose.scarfReady !== 'true' ||
        !pose.scarfRaster?.pixels ||
        pose.scarfRaster.draw !== pose.nativeDraw ||
        pose.sampleBufferUploads !== 0
    )
  ) {
    await writeFile(
      resolve(output, `${style}-${scenario}-failure.json`),
      JSON.stringify({ style, scenario, beforeScreenshot, poses }, null, 2)
    );
    throw new Error(
      `${style}/${scenario}: scarf must paint real pixels without rebuilding GPU buffers`
    );
  }
  if (
    fallbackScenario &&
    ['bip', 'oscar', 'nimbo'].includes(style) &&
    poses.some(pose => !pose.passed)
  ) {
    await writeFile(
      resolve(output, `${style}-${scenario}-projection-failure.json`),
      JSON.stringify({ style, scenario, poses }, null, 2)
    );
    throw new Error(
      `${style}/${scenario}: painted cloth must match independent source-to-head projection within 0.05 CSS pixels`
    );
  }
  if (
    fallbackScenario &&
    poses.some(pose => pose.scarfReady !== 'false' || pose.fallback?.visibility !== 'visible')
  )
    throw new Error(`${style}: context loss must show the native scarf fallback`);
  if (
    fallbackScenario &&
    poses.some(
      pose =>
        ['bip', 'oscar', 'nimbo'].includes(style) &&
        (pose.facetProjection.length !== 32 ||
          pose.splitContinuity.length !== 4 ||
          pose.splitContinuity.some(point => point.gap === null || point.gap > 0.05))
    )
  ) {
    await writeFile(
      resolve(output, `${style}-${scenario}-continuity-failure.json`),
      JSON.stringify({ style, scenario, poses }, null, 2)
    );
    throw new Error(
      `${style}/${scenario}: native front/rear boundary corners must meet within 0.05 CSS pixels`
    );
  }
  for (const variant of ['female', 'male']) {
    await page.locator(`article[data-variant="${variant}"] [data-live="true"] .stage`).screenshot({
      path: resolve(output, `${style}-${variant}-${scenario}.png`),
    });
  }
  records.push({ style, scenario, filename, sampleMs, beforeScreenshot, poses });
  await writeFile(
    resolve(output, 'evidence.json'),
    JSON.stringify(
      {
        browser: browser.version(),
        engine,
        theme,
        size,
        projectionMethod:
          'Independent source geometry projected through the head matrix, including source Z; actual painted patch points measured separately',
        origin,
        viewport: page.viewportSize(),
        deviceScaleFactor: 2,
        environment: {
          temperature_c: 5,
          condition_code: 'Clear',
          wind_speed_kmh: 0,
          timezone: 'UTC',
        },
        errors,
        warnings,
        records,
      },
      null,
      2
    )
  );
  process.stdout.write(`${style} ${scenario}: ${filename}\n`);
  return poses;
}

async function cueTail(page, gaze) {
  await page.locator('#gaze').selectOption(gaze);
  for (let frame = 0; frame < 24; frame++) {
    await page.clock.runFor(16);
    const values = await page
      .locator('[data-live="true"] .lia-eyes')
      .evaluateAll(roots =>
        roots.map(root => Number(root.style.getPropertyValue('--rig-scarf-trail')))
      );
    if (values.length === 2 && values.every(value => Math.abs(value) > 0.02)) return;
  }
  throw new Error('Both native free ends must respond to the deliberate head turn');
}

async function inspectTail(page, style) {
  await armRaster(page);
  await cueTail(page, 'left');
  const gpu = await capture(page, style, 'tail-native-moving', false);
  for (const pose of gpu) {
    const [band, knot] = pose.scarfRaster.passes;
    if (
      pose.scarfRaster.passes.length !== 2 ||
      !band.drape?.every(value => value === 0) ||
      !knot.drape ||
      Math.abs(knot.drape[0] - pose.trail) > 0.001 ||
      !Number.isFinite(knot.drape[1])
    )
      throw new Error(
        `${style}: the native band must stay attached while the free end follows the turn`
      );
  }
  await page.clock.runFor(1100);
  await page.locator('[data-live="true"] canvas').evaluateAll(canvases =>
    canvases.forEach(canvas => {
      const extension = canvas.getContext('webgl')?.getExtension('WEBGL_lose_context');
      if (!extension) throw new Error('Native context loss is required');
      extension.loseContext();
    })
  );
  await wait(80);
  const rest = await capture(page, style, 'fallback-tail-settled', false);
  if (rest.some(pose => pose.trail !== 0))
    throw new Error(`${style}: the free end must stay still on a settled head`);
  await cueTail(page, 'right');
  const moving = await capture(page, style, 'fallback-tail-moving', false);
  if (moving.some((pose, index) => pose.trail * gpu[index].trail >= 0))
    throw new Error(`${style}: the free end must respond in opposite directions to opposite turns`);
}

async function quickInspection(page, style) {
  for (const gaze of ['left', 'right']) {
    await armRaster(page);
    await page.locator('#gaze').selectOption(gaze);
    await page.clock.runFor(1000);
    await capture(page, style, `turn-${gaze}`);
  }
  await armRaster(page);
  await page.locator('#gaze').selectOption('center');
  await page.clock.runFor(1000);
  await capture(page, style, 'front-before-loss');
  await page.locator('[data-live="true"] canvas').evaluateAll(canvases =>
    canvases.forEach(canvas => {
      const extension = canvas.getContext('webgl')?.getExtension('WEBGL_lose_context');
      if (!extension) throw new Error('Native context-loss extension is required');
      extension.loseContext();
    })
  );
  await wait(80);
  await capture(page, style, 'context-lost', false);
  for (const gaze of ['left', 'right', 'up', 'down']) {
    await page.locator('#gaze').selectOption(gaze);
    await page.clock.runFor(1000);
    await capture(page, style, `fallback-${gaze}`);
  }
}

async function inspectFallbackFade(page, style) {
  await page.locator('[data-live="true"] canvas').evaluateAll(canvases =>
    canvases.forEach(canvas => {
      const extension = canvas.getContext('webgl')?.getExtension('WEBGL_lose_context');
      if (!extension) throw new Error('Native context-loss extension is required');
      extension.loseContext();
    })
  );
  await wait(80);
  await capture(page, style, 'context-lost', false);
  await page.locator('#cold').uncheck();
  for (let frame = 0; frame < 100; frame++) {
    await page.clock.runFor(16);
    const values = await page
      .locator('[data-live="true"] .lia-eyes')
      .evaluateAll(roots =>
        roots.map(root => parseFloat(root.style.getPropertyValue('--rig-weather-cold')))
      );
    if (values.every(value => value >= 0.2 && value <= 0.35)) {
      await capture(page, style, 'fallback-partial', false);
      await page.locator('#cold').check();
      await page.clock.runFor(1000);
      for (const gaze of ['left', 'right', 'up', 'down']) {
        await page.locator('#gaze').selectOption(gaze);
        await page.clock.runFor(1000);
        await capture(page, style, `fallback-${gaze}`);
      }
      return;
    }
  }
  throw new Error('Native cold fade must cross the measured partial interval');
}

try {
  const discovery = await open();
  const available = await discovery.page
    .locator('#character option')
    .evaluateAll(options => options.map(option => option.value));
  await discovery.context.close();
  const styles = selected ?? available;
  if (styles.some(style => !available.includes(style)))
    throw new Error('Unknown native style requested');
  for (const style of styles) {
    const { context, page } = await open(style);
    try {
      await page.clock.runFor(320);
      await capture(page, style, size === 'xl' ? 'front-large' : `front-${size}`);
      if (trail) await inspectTail(page, style);
      else if (fade) await inspectFallbackFade(page, style);
      else if (quick) await quickInspection(page, style);
      else if (diagnostics) {
        await armRaster(page);
        await page.clock.runFor(1000);
        await capture(page, style, 'stable-cold');
        await armRaster(page);
        await page.locator('#expression').selectOption('surprise');
        await page.clock.runFor(900);
        await capture(page, style, 'open-mouth');
        await page.locator('#expression').selectOption('neutral');
        await page.clock.runFor(900);
        for (const gaze of ['left', 'right', 'up', 'down']) {
          await armRaster(page);
          await page.locator('#gaze').selectOption(gaze);
          await page.clock.runFor(1000);
          await capture(page, style, `turn-${gaze}`);
        }
        await page.locator('#gaze').selectOption('center');
        await page.locator('#size').selectOption('sm');
        await page.clock.runFor(640);
        await capture(page, style, 'front-compact');
        await page.getByLabel('Dark', { exact: true }).check();
        await page.locator('#size').selectOption('xl');
        await page.clock.runFor(640);
        await capture(page, style, 'front-dark');
        await page.locator('[data-live="true"] canvas').evaluateAll(canvases => {
          for (const canvas of canvases) {
            const extension = canvas.getContext('webgl')?.getExtension('WEBGL_lose_context');
            if (!extension) throw new Error('Native context-loss extension is required');
            extension.loseContext();
          }
        });
        await wait(80);
        await page.clock.runFor(64);
        await capture(page, style, 'context-lost');
        for (const gaze of ['left', 'right', 'up', 'down']) {
          await page.locator('#gaze').selectOption(gaze);
          await page.clock.runFor(1000);
          await capture(page, style, `fallback-${gaze}`);
        }
      }
    } finally {
      await context.close();
    }
  }
  if (errors.length) throw new Error(`Unexpected browser errors: ${errors.join('\n')}`);
} finally {
  await browser.close();
}
