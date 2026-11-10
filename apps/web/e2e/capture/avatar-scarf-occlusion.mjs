/** Native rear-cloth occlusion, bounded by the independent source alpha transmission. */
import { chromium, firefox, webkit } from '@playwright/test';
import { createHash } from 'node:crypto';
import { mkdir, readdir, readFile, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { setTimeout as wait } from 'node:timers/promises';

const argument = name =>
  process.argv.find(value => value.startsWith(`--${name}=`))?.slice(name.length + 3);
const origin = new URL(argument('origin') ?? 'http://127.0.0.1:5189').origin;
const output = resolve(
  argument('output') ?? '../../../output/playwright/avatar-artistry/scarf-occlusion'
);
const engine = argument('browser') ?? 'webkit';
const styles = (argument('styles') ?? 'bip,oscar,nimbo').split(',');
const diagnose = process.argv.includes('--diagnose');
const visibleControl = process.argv.includes('--visible-control');
const preroll = process.argv.includes('--preroll');
const cssPath = argument('css') ? resolve(argument('css')) : null;
if (!['chromium', 'firefox', 'webkit'].includes(engine)) throw new Error('Unknown browser engine');
if (!styles.length || styles.some(style => !['bip', 'oscar', 'nimbo'].includes(style)))
  throw new Error('Occlusion qualification requires the declared wrapped identities');
await mkdir(output, { recursive: true });
if ((await readdir(output)).length) throw new Error('Evidence directory must be empty');
const diagnosticCss = cssPath ? await readFile(cssPath, 'utf8') : null;
if (diagnosticCss) await writeFile(resolve(output, 'diagnostic.css'), diagnosticCss);
const browser = await { chromium, firefox, webkit }[engine].launch({
  ...(engine === 'chromium' ? { channel: 'chromium' } : {}),
  headless: true,
});
const records = [],
  errors = [],
  consoleMessages = [];
let completed = false;

async function save() {
  const caseResults = records.flatMap(record => record.results);
  await writeFile(
    resolve(output, 'evidence.json'),
    JSON.stringify(
      {
        browser: browser.version(),
        engine,
        origin,
        diagnose,
        visibleControl,
        preroll,
        completed,
        status: completed
          ? caseResults.every(result => result.passed) && !errors.length
            ? 'passed'
            : 'failed'
          : 'incomplete',
        caseCount: caseResults.length,
        failedCaseCount: caseResults.filter(result => !result.passed).length,
        scope: 'Rear scarf occlusion only; this does not qualify scarf geometry or continuity.',
        diagnosticCss: cssPath
          ? {
              path: cssPath,
              sha256: createHash('sha256').update(diagnosticCss).digest('hex'),
              warning: 'Diagnostic CSS override; not production-source qualification',
            }
          : null,
        method:
          'Paused native clock; original matrix and only rear scarf layers hidden. ROI uses source body.webp alpha >= 254 eroded by 2 source pixels, normalized central quarter-to-three-quarter square, affine projection measured through zero-size native head probes, and actual eyes/mouth exclusions. Each pixel allows only its physically possible residual transmission, ceil(255*(1-normalizedAlpha)); normalizedAlpha uses the conservative minimum source alpha in its 2 px sampling footprint and the actual native SVG transfer. Fully opaque footprints require exact zero delta. Unchanged and restored native frames must be pixel-identical.',
        errors,
        consoleMessages,
        records,
      },
      null,
      2
    )
  );
}

async function settle(page, fallback) {
  for (let attempt = 0; attempt < 180; attempt++) {
    await page.clock.runFor(32);
    const state = await page.locator('[data-live="true"] .lia-eyes').evaluateAll(roots =>
      roots.map(root => ({
        ready: root.dataset.volumeReady,
        scarf: root.dataset.volumeScarfReady,
        cold: parseFloat(root.style.getPropertyValue('--rig-weather-cold')),
        fallback: getComputedStyle(root.querySelector('.lia-head'), '::before').visibility,
      }))
    );
    if (
      state.length === 2 &&
      state.every(
        value =>
          value.cold > 0.5 &&
          (fallback
            ? value.ready === 'false' && value.scarf === 'false' && value.fallback === 'visible'
            : value.ready === 'true' && value.scarf === 'true')
      )
    )
      return;
    await wait(20);
  }
  throw new Error('Both cold native variants must reach the requested rendering state');
}

/** Native non-painting probes include the head and every actual ancestor transform. */
async function projectSources(page) {
  return page.locator('[data-live="true"] .lia-eyes').evaluateAll(roots =>
    roots.map(root => {
      const head = root.querySelector('.lia-head');
      const pseudo = getComputedStyle(head, '::before');
      const source = pseudo.backgroundImage.match(/^url\(["']?(.*?)["']?\)$/)?.[1];
      if (!source || !source.endsWith('/body.webp'))
        throw new Error('An original body texture is required');
      const alpha = root.closest('[data-spirit-companion]').querySelector('filter feFuncA');
      if (alpha?.getAttribute('type') !== 'linear')
        throw new Error('The native alpha transfer must be linear');
      const transfer = {
        slope: Number(alpha.getAttribute('slope')),
        intercept: Number(alpha.getAttribute('intercept')),
      };
      if (!Object.values(transfer).every(Number.isFinite))
        throw new Error('Invalid native alpha transfer');
      if (Math.abs(transfer.slope + transfer.intercept - 1) > 1e-12)
        throw new Error('The native transfer must preserve fully opaque source pixels');
      if (
        pseudo.transform !== 'none' ||
        !['none', '0px'].includes(pseudo.translate) ||
        pseudo.rotate !== 'none'
      )
        throw new Error(
          'An unmeasured pseudo-element transform cannot enter the projection oracle'
        );
      const width = parseFloat(pseudo.width),
        height = parseFloat(pseudo.height);
      const left = parseFloat(pseudo.left),
        top = parseFloat(pseudo.top);
      const scale = pseudo.scale === 'none' ? [1] : pseudo.scale.split(' ').map(Number);
      const [originX, originY] = pseudo.transformOrigin.split(' ').map(parseFloat);
      if (![width, height, left, top, ...scale, originX, originY].every(Number.isFinite))
        throw new Error('The actual body projection must have finite dimensions');
      if (pseudo.backgroundSize !== 'contain')
        throw new Error('The measured source layout is contain');
      const probe = (u, v) => {
        // Published body art is square. Its decoded dimensions are independently
        // checked before this mapping is admitted into the pixel comparison.
        const edge = Math.min(width, height);
        const x = (width - edge) / 2 + edge * u;
        const y = (height - edge) / 2 + edge * v;
        const point = document.createElement('span');
        Object.assign(point.style, {
          position: 'absolute',
          left: `${left + originX + (x - originX) * scale[0]}px`,
          top: `${top + originY + (y - originY) * (scale[1] ?? scale[0])}px`,
          width: '0',
          height: '0',
          visibility: 'hidden',
          pointerEvents: 'none',
        });
        head.append(point);
        const box = point.getBoundingClientRect();
        point.remove();
        return { x: box.x, y: box.y };
      };
      const points = [
        [0, 0],
        [1, 0],
        [0, 1],
        [1, 1],
      ].map(([u, v]) => probe(u, v));
      const affineError = Math.hypot(
        points[3].x - (points[1].x + points[2].x - points[0].x),
        points[3].y - (points[1].y + points[2].y - points[0].y)
      );
      if (affineError > 0.05) throw new Error(`Non-affine source projection: ${affineError}`);
      const exclusions = [...root.querySelectorAll('.lia-eye, [data-rig-mouth]')].map(organ => {
        const box = organ.getBoundingClientRect();
        return { left: box.left, top: box.top, right: box.right, bottom: box.bottom };
      });
      return {
        variant: root.closest('article').dataset.variant,
        source,
        transfer,
        points,
        affineError,
        exclusions,
        width,
        height,
        scale,
        perspective: getComputedStyle(root).perspective,
        ready: root.dataset.volumeReady,
        cold: parseFloat(root.style.getPropertyValue('--rig-weather-cold')),
        yaw: parseFloat(root.style.getPropertyValue('--rig-head-yaw')),
        pitch: parseFloat(root.style.getPropertyValue('--rig-head-pitch')),
        style: root.getAttribute('style'),
        rearLayers: root.querySelectorAll('.lia-scarf-wrap-layer--back').length,
      };
    })
  );
}

async function compare(page, before, after, control, restored, clip, projections) {
  return page.evaluate(
    async ({ before, after, control, restored, clip, projections }) => {
      const decode = async url => {
        const image = new Image();
        image.src = url;
        await image.decode();
        const canvas = document.createElement('canvas');
        canvas.width = image.naturalWidth;
        canvas.height = image.naturalHeight;
        const context = canvas.getContext('2d', { willReadFrequently: true });
        context.drawImage(image, 0, 0);
        return {
          width: canvas.width,
          height: canvas.height,
          data: context.getImageData(0, 0, canvas.width, canvas.height).data,
        };
      };
      const a = await decode(`data:image/png;base64,${before}`);
      const b = await decode(`data:image/png;base64,${after}`);
      const c = await decode(`data:image/png;base64,${control}`);
      const d = await decode(`data:image/png;base64,${restored}`);
      if ([b, c, d].some(value => a.width !== value.width || a.height !== value.height))
        throw new Error('Screenshot dimensions changed');
      const changedPixels = other => {
        let count = 0;
        for (let offset = 0; offset < a.data.length; offset += 4)
          if (
            [0, 1, 2, 3].some(channel => a.data[offset + channel] !== other.data[offset + channel])
          )
            count++;
        return count;
      };
      const controlChanged = changedPixels(c),
        restoredChanged = changedPixels(d);
      const ratioX = a.width / clip.width,
        ratioY = a.height / clip.height;
      const erodeSource = body => {
        const mask = new Uint8Array(body.width * body.height);
        let sourceOpaquePixels = 0,
          sourceNearOpaquePixels = 0,
          erodedPixels = 0;
        for (let offset = 3; offset < body.data.length; offset += 4) {
          if (body.data[offset] === 255) sourceOpaquePixels++;
          if (body.data[offset] >= 254) sourceNearOpaquePixels++;
        }
        for (let y = 2; y < body.height - 2; y++)
          for (let x = 2; x < body.width - 2; x++) {
            let minimumAlpha = 255;
            for (let dy = -2; dy <= 2; dy++)
              for (let dx = -2; dx <= 2; dx++)
                minimumAlpha = Math.min(
                  minimumAlpha,
                  body.data[((y + dy) * body.width + x + dx) * 4 + 3]
                );
            if (minimumAlpha >= 254) {
              mask[y * body.width + x] = minimumAlpha;
              erodedPixels++;
            }
          }
        return { mask, sourceOpaquePixels, sourceNearOpaquePixels, erodedPixels };
      };
      const sourcePixel = (x, y, projection, body, mask) => {
        const [o, horizontal, vertical] = projection.points;
        const ax = horizontal.x - o.x,
          ay = horizontal.y - o.y;
        const bx = vertical.x - o.x,
          by = vertical.y - o.y;
        const determinant = ax * by - ay * bx;
        if (Math.abs(determinant) < 1) throw new Error('Degenerate source projection');
        const pageX = clip.x + (x + 0.5) / ratioX,
          pageY = clip.y + (y + 0.5) / ratioY;
        const px = pageX - o.x,
          py = pageY - o.y;
        const u = (px * by - py * bx) / determinant,
          v = (ax * py - ay * px) / determinant;
        if (u < 0.25 || u > 0.75 || v < 0.25 || v > 0.75) return null;
        const sourceAlpha =
          mask[Math.floor(v * body.height) * body.width + Math.floor(u * body.width)];
        if (!sourceAlpha) return null;
        if (
          projection.exclusions.some(
            box =>
              pageX >= box.left && pageX <= box.right && pageY >= box.top && pageY <= box.bottom
          )
        )
          return null;
        const normalizedAlpha = Math.min(
          1,
          Math.max(
            0,
            (sourceAlpha / 255) * projection.transfer.slope + projection.transfer.intercept
          )
        );
        const bound = sourceAlpha === 255 ? 0 : Math.ceil(255 * (1 - normalizedAlpha));
        return { x, y, pageX, pageY, u, v, sourceAlpha, normalizedAlpha, bound };
      };
      const accumulate = (stats, sample) => {
        const { x, y, sourceAlpha, bound } = sample;
        stats.roiPixels++;
        stats.sourceAlphaMin = Math.min(stats.sourceAlphaMin, sourceAlpha);
        stats.sourceAlphaMax = Math.max(stats.sourceAlphaMax, sourceAlpha);
        stats.maximumTransmission = Math.max(stats.maximumTransmission, bound);
        const offset = (y * a.width + x) * 4;
        const delta = Math.max(
          ...[0, 1, 2, 3].map(channel =>
            Math.abs(a.data[offset + channel] - b.data[offset + channel])
          )
        );
        if (delta > 0) stats.exactChanged++;
        if (delta > 2) stats.changedOverTwo++;
        if (bound === 0) {
          stats.opaquePixels++;
          if (delta > 0) stats.opaqueChanged++;
        }
        if (delta > bound) stats.transmissionViolations++;
        stats.maxDelta = Math.max(stats.maxDelta, delta);
        if (delta > bound && stats.examples.length < 12) stats.examples.push({ ...sample, delta });
      };
      const results = [];
      for (const projection of projections) {
        const body = await decode(projection.source);
        if (body.width !== body.height)
          throw new Error('Non-square source requires its own measured contain mapping');
        const { mask, ...sourceStats } = erodeSource(body);
        const stats = {
          roiPixels: 0,
          exactChanged: 0,
          changedOverTwo: 0,
          maxDelta: 0,
          sourceAlphaMin: 255,
          sourceAlphaMax: 0,
          maximumTransmission: 0,
          opaquePixels: 0,
          opaqueChanged: 0,
          transmissionViolations: 0,
          examples: [],
        };
        for (let y = 0; y < a.height; y++)
          for (let x = 0; x < a.width; x++) {
            const sample = sourcePixel(x, y, projection, body, mask);
            if (sample) accumulate(stats, sample);
          }
        results.push({
          variant: projection.variant,
          sourceWidth: body.width,
          sourceHeight: body.height,
          ...sourceStats,
          ...stats,
          passed:
            stats.roiPixels > 100 &&
            stats.transmissionViolations === 0 &&
            controlChanged === 0 &&
            restoredChanged === 0,
        });
      }
      return {
        width: a.width,
        height: a.height,
        ratioX,
        ratioY,
        controlChanged,
        restoredChanged,
        results,
      };
    },
    {
      before: before.toString('base64'),
      after: after.toString('base64'),
      control: control.toString('base64'),
      restored: restored.toString('base64'),
      clip,
      projections,
    }
  );
}

async function stableRaster(page, clip, label) {
  let previous = await page.screenshot({ clip });
  for (let attempt = 0; attempt < 3; attempt++) {
    // Screenshot completion is not a compositor-idle signal. Keep native time
    // paused while giving pending image/filter raster work a bounded wall interval.
    await wait(100);
    const current = await page.screenshot({ clip });
    if (current.equals(previous)) return { image: current, frames: attempt + 2 };
    await writeFile(resolve(output, `${label}-settling-${attempt}.png`), previous);
    previous = current;
  }
  throw new Error('The paused native raster did not stabilize in four captures');
}

async function capture(page, style, gaze) {
  const projections = await projectSources(page);
  if (
    projections.length !== 2 ||
    projections
      .map(p => p.variant)
      .sort()
      .join(',') !== 'female,male' ||
    projections.some(p => p.rearLayers !== 1 || p.ready !== 'false' || p.cold <= 0.5)
  )
    throw new Error('Both cold fallback variants and their rear layers must be present');
  const expected = { center: [0, 0], left: [-1, 0], right: [1, 0], up: [0, -1], down: [0, 1] }[
    gaze
  ];
  if (
    projections.some(projection =>
      [projection.yaw, projection.pitch].some(
        (value, axis) => !Number.isFinite(value) || Math.abs(value - expected[axis]) > 0.1
      )
    )
  )
    throw new Error('The real gaze control must settle its native head pose');
  const box = await page.locator('.matrix').boundingBox();
  if (!box) throw new Error('The native matrix must be visible');
  const clip = {
    x: Math.floor(box.x),
    y: Math.floor(box.y),
    width: Math.ceil(box.x + box.width) - Math.floor(box.x),
    height: Math.ceil(box.y + box.height) - Math.floor(box.y),
  };
  const clock = await page.evaluate(() => Date.now());
  // A completed screenshot can precede a compositor's last raster commit.
  // Establish an unchanged paused frame before choosing the reference; never
  // relax the exact control/restoration comparisons that follow it.
  const stabilized = await stableRaster(page, clip, `${style}-${gaze}-reference`);
  const originalFile = `${style}-${gaze}-original.png`,
    hiddenFile = `${style}-${gaze}-rear-hidden.png`;
  const original = await page.screenshot({ path: resolve(output, originalFile), clip });
  const controlFile = `${style}-${gaze}-unchanged-control.png`,
    restoredFile = `${style}-${gaze}-restored.png`;
  const control = await page.screenshot({ path: resolve(output, controlFile), clip });
  const hidden = await page.addStyleTag({
    content: `.lia-scarf-wrap-layer--back { visibility: ${visibleControl ? 'visible' : 'hidden'} !important; }`,
  });
  let withoutRear;
  try {
    withoutRear = await page.screenshot({ path: resolve(output, hiddenFile), clip });
  } finally {
    await hidden.evaluate(element => element.remove());
  }
  const restoredRaster = await stableRaster(page, clip, `${style}-${gaze}-restoration`);
  const restoredImage = restoredRaster.image;
  await writeFile(resolve(output, restoredFile), restoredImage);
  const restored = await projectSources(page);
  if (
    (await page.evaluate(() => Date.now())) !== clock ||
    JSON.stringify(restored) !== JSON.stringify(projections)
  )
    throw new Error('The diagnostic changed time, native pose or source projection');
  const pixels = await compare(
    page,
    original,
    withoutRear,
    control,
    restoredImage,
    clip,
    projections
  );
  const record = {
    style,
    gaze,
    clock,
    stabilizationFrames: stabilized.frames,
    restorationFrames: restoredRaster.frames,
    originalFile,
    hiddenFile,
    controlFile,
    restoredFile,
    clip,
    projections,
    ...pixels,
  };
  records.push(record);
  await save();
  process.stdout.write(
    `${style}/${gaze}: ${pixels.results.map(r => `${r.variant} ${r.transmissionViolations}/${r.roiPixels} violations (${r.exactChanged} changed, max ${r.maxDelta}, bound ${r.maximumTransmission})`).join('; ')}; control ${pixels.controlChanged}, restored ${pixels.restoredChanged}\n`
  );
  if (!diagnose && pixels.results.some(result => !result.passed))
    throw new Error(`${style}/${gaze}: rear cloth exceeded source alpha transmission`);
}

try {
  for (const style of styles) {
    const context = await browser.newContext({
      viewport: { width: 1440, height: 1200 },
      deviceScaleFactor: 2,
      reducedMotion: 'no-preference',
    });
    try {
      await context.route('**/*', route => {
        const url = new URL(route.request().url());
        if (url.origin === origin && !url.pathname.startsWith('/api/')) return route.continue();
        errors.push(`Unexpected request: ${url.origin}${url.pathname}`);
        return route.abort();
      });
      const page = await context.newPage();
      page.on('pageerror', error => errors.push(error.message));
      page.on('console', message => {
        if (['warning', 'error'].includes(message.type()))
          consoleMessages.push({ style, type: message.type(), text: message.text() });
      });
      await page.clock.install({ time: new Date('2026-11-07T12:00:00Z') });
      await page.clock.pauseAt(await page.evaluate(() => Date.now() + 10_000));
      await page.goto(
        `${origin}/?character=${style}&cold=true&life=true&size=xl&gaze=center&closeup=true`
      );
      if (diagnosticCss) await page.addStyleTag({ content: diagnosticCss });
      await settle(page, false);
      await page.locator('[data-live="true"] canvas').evaluateAll(canvases => {
        if (canvases.length !== 2) throw new Error('Both native surfaces are required');
        for (const canvas of canvases) {
          const extension = canvas.getContext('webgl')?.getExtension('WEBGL_lose_context');
          if (!extension) throw new Error('Native context loss is required');
          extension.loseContext();
        }
      });
      await wait(80);
      await settle(page, true);
      if (preroll) {
        for (const gaze of ['left', 'center']) {
          await page.locator('#gaze').selectOption(gaze);
          await page.clock.runFor(1000);
        }
      }
      for (const gaze of ['center', 'left', 'right', 'up', 'down']) {
        await page.locator('#gaze').selectOption(gaze);
        await page.clock.runFor(1000);
        await capture(page, style, gaze);
      }
    } finally {
      await context.close();
    }
  }
  completed = true;
  if (errors.length) throw new Error('Unexpected browser error; see evidence.json');
} finally {
  await save();
  await browser.close();
}
