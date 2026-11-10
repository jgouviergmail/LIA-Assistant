/** Native material qualification; no component pose or material is replaced. */
import { chromium, firefox, webkit } from '@playwright/test';
import { mkdir, readdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { setTimeout as wait } from 'node:timers/promises';

const argument = name =>
  process.argv.find(value => value.startsWith(`--${name}=`))?.slice(name.length + 3);
const output = resolve(
  argument('output') ?? '../../../output/playwright/avatar-artistry/material-current'
);
const origin = argument('origin') ?? 'http://127.0.0.1:5188';
const engine = argument('browser') ?? 'chromium';
const companions = ['spirit', 'moss', 'lumen', 'nimbo', 'orbit', 'bip', 'boulon', 'oscar'];
const styles = argument('styles')?.split(',') ?? [
  ...companions,
  'cozmo',
  'capsules',
  'billes',
  'amande',
  'traits',
  'anneaux',
];
const baseline = process.argv.includes('--baseline');
const warmOnly = process.argv.includes('--warm-only');
if (!['chromium', 'firefox', 'webkit'].includes(engine)) throw new Error('Unknown engine');
await mkdir(output, { recursive: true });
if ((await readdir(output)).length) throw new Error('Evidence directory must be empty');
const browser = await { chromium, firefox, webkit }[engine].launch({
  ...(engine === 'chromium' ? { channel: 'chromium' } : {}),
  headless: true,
});
const records = [],
  errors = [],
  warnings = [];

async function settle(page, ready) {
  for (let attempt = 0; attempt < 100; attempt++) {
    await page.clock.runFor(32);
    const states = await page
      .locator('[data-live="true"] .lia-eyes')
      .evaluateAll(roots => roots.map(root => root.getAttribute('data-volume-ready')));
    if (states.length === 2 && states.every(state => state === String(ready))) return;
    await wait(25);
  }
  throw new Error(`Native readiness did not reach ${ready}`);
}

async function open(style, theme) {
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 2,
    reducedMotion: 'no-preference',
  });
  await context.route('**/*', route => {
    const url = new URL(route.request().url());
    if (warmOnly && url.pathname.startsWith('/avatars/scarf/')) {
      errors.push('A warm avatar requested a scarf texture');
      return route.abort();
    }
    if (url.origin === origin && !url.pathname.startsWith('/api/')) return route.continue();
    errors.push(`Unexpected request: ${url.origin}${url.pathname}`);
    return route.abort();
  });
  const page = await context.newPage();
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => {
    if (message.type() === 'error') errors.push(message.text());
    if (message.type() === 'warning') warnings.push(message.text());
  });
  await page.addInitScript(() => {
    const draw = WebGLRenderingContext.prototype.drawElements;
    WebGLRenderingContext.prototype.drawElements = function (...args) {
      const result = draw.apply(this, args);
      const canvas = this.canvas;
      if (!(canvas instanceof HTMLCanvasElement) || !canvas.closest('[data-live="true"]'))
        return result;
      const pixels = new Uint8Array(canvas.width * canvas.height * 4);
      this.readPixels(0, 0, canvas.width, canvas.height, this.RGBA, this.UNSIGNED_BYTE, pixels);
      const histogram = Array(256).fill(0);
      for (let i = 3; i < pixels.length; i += 4) histogram[pixels[i]]++;
      const program = this.getParameter(this.CURRENT_PROGRAM);
      const uniform = this.getUniformLocation(program, 'u_alpha_transfer');
      const transfer = uniform ? Array.from(this.getUniform(program, uniform)) : null;
      canvas.dataset.materialRaster = JSON.stringify({
        width: canvas.width,
        height: canvas.height,
        histogram,
        transfer,
      });
      return result;
    };
  });
  await page.clock.install({ time: new Date('2026-11-07T12:00:00Z') });
  await page.clock.pauseAt(await page.evaluate(() => Date.now() + 10_000));
  await page.goto(`${origin}/?character=${style}&theme=${theme}&life=false&size=xl`);
  await settle(page, true);
  await page.clock.runFor(800);
  return { context, page };
}

/** Exercise the exact mounted SVG filter against the exact mounted source image. */
async function inspectFilter(page) {
  return page.locator('[data-live="true"] .lia-head').evaluateAll(async heads => {
    const results = [];
    for (const head of heads) {
      const style = getComputedStyle(head, '::before');
      const filterUrl = style.filter.match(/url\("?([^\)"]+)/)?.[1];
      const sourceUrl = style.backgroundImage.match(/url\("?([^\)"]+)/)?.[1];
      if (!filterUrl || !sourceUrl)
        throw new Error('The real baked source and local filter are required');
      const id = new URL(filterUrl, location.href).hash.slice(1);
      const filter = document.getElementById(decodeURIComponent(id));
      if (!filter) throw new Error('Mounted native source filter unavailable');
      const blob = await (await fetch(sourceUrl)).blob();
      const data = await new Promise(resolve => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.readAsDataURL(blob);
      });
      const source = new Image();
      source.src = data;
      await source.decode();
      const width = source.naturalWidth,
        height = source.naturalHeight;
      const canvas = document.createElement('canvas');
      canvas.width = width;
      canvas.height = height;
      const context = canvas.getContext('2d', { willReadFrequently: true });
      context.drawImage(source, 0, 0);
      const original = context.getImageData(0, 0, width, height).data;
      const controlSvg = `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}"><image width="${width}" height="${height}" href="${data}"/></svg>`;
      const controlImage = new Image();
      controlImage.src = `data:image/svg+xml,${encodeURIComponent(controlSvg)}`;
      await controlImage.decode();
      context.clearRect(0, 0, width, height);
      context.drawImage(controlImage, 0, 0);
      const control = context.getImageData(0, 0, width, height).data;
      async function filteredPixels(definition) {
        const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}"><defs>${definition.outerHTML}</defs><image width="${width}" height="${height}" href="${data}" filter="url(#${definition.id})"/></svg>`;
        const image = new Image();
        image.src = `data:image/svg+xml,${encodeURIComponent(svg)}`;
        await image.decode();
        context.clearRect(0, 0, width, height);
        context.drawImage(image, 0, 0);
        return context.getImageData(0, 0, width, height).data;
      }
      const identityDefinition = filter.cloneNode(true);
      identityDefinition.querySelector('feFuncA').setAttribute('slope', '1');
      identityDefinition.querySelector('feFuncA').setAttribute('intercept', '0');
      const identity = await filteredPixels(identityDefinition);
      const endpointDefinition = filter.cloneNode(true);
      const slope = Math.fround(255 / 253);
      endpointDefinition.querySelector('feFuncA').setAttribute('slope', String(slope));
      endpointDefinition.querySelector('feFuncA').setAttribute('intercept', String(1 - slope));
      const endpoint = await filteredPixels(endpointDefinition);
      const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}"><defs>${filter.outerHTML}</defs><image width="${width}" height="${height}" href="${data}" filter="url(#${filter.id})"/></svg>`;
      const corrected = new Image();
      corrected.src = `data:image/svg+xml,${encodeURIComponent(svg)}`;
      await corrected.decode();
      context.clearRect(0, 0, width, height);
      context.drawImage(corrected, 0, 0);
      const filtered = context.getImageData(0, 0, width, height).data;
      let mattePixels = 0,
        matteNotClear = 0,
        opaquePixels = 0,
        opaqueChanged = 0,
        svgControlChanged = 0,
        identityOpaqueChanged = 0,
        identityOpaqueMaxDelta = 0,
        normalizationBeyondIdentity = 0,
        endpointOpaqueChanged = 0;
      const opaqueDifferences = [];
      for (let i = 0; i < original.length; i += 4) {
        if (original[i + 3] === 2) {
          mattePixels++;
          if (filtered[i + 3] !== 0) matteNotClear++;
        }
        if (original[i + 3] === 255) {
          opaquePixels++;
          if (original.slice(i, i + 4).some((value, index) => value !== control[i + index]))
            svgControlChanged++;
          if (control.slice(i, i + 4).some((value, index) => value !== identity[i + index]))
            identityOpaqueChanged++;
          for (let channel = 0; channel < 4; channel++)
            identityOpaqueMaxDelta = Math.max(
              identityOpaqueMaxDelta,
              Math.abs(control[i + channel] - identity[i + channel])
            );
          if (identity.slice(i, i + 4).some((value, index) => value !== filtered[i + index]))
            normalizationBeyondIdentity++;
          if (control.slice(i, i + 4).some((value, index) => value !== endpoint[i + index]))
            endpointOpaqueChanged++;
          if (
            control[i] !== filtered[i] ||
            control[i + 1] !== filtered[i + 1] ||
            control[i + 2] !== filtered[i + 2] ||
            control[i + 3] !== filtered[i + 3]
          ) {
            opaqueChanged++;
            if (opaqueDifferences.length < 10)
              opaqueDifferences.push({
                pixel: i / 4,
                original: Array.from(original.slice(i, i + 4)),
                control: Array.from(control.slice(i, i + 4)),
                filtered: Array.from(filtered.slice(i, i + 4)),
              });
          }
        }
      }
      results.push({
        sourceUrl,
        filter: filter.outerHTML,
        width,
        height,
        mattePixels,
        matteNotClear,
        opaquePixels,
        opaqueChanged,
        svgControlChanged,
        identityOpaqueChanged,
        identityOpaqueMaxDelta,
        normalizationBeyondIdentity,
        endpointOpaqueChanged,
        opaqueDifferences,
      });
    }
    return results;
  });
}

async function capture(page, style, theme, scenario, filters = null) {
  const poses = await page.locator('[data-live="true"] .lia-eyes').evaluateAll(roots =>
    roots.map(root => {
      const canvas = root.querySelector('canvas');
      const head = root.querySelector('.lia-head');
      const baked = head ? getComputedStyle(head, '::before') : null;
      return {
        variant: root.closest('article').dataset.variant,
        ready: root.getAttribute('data-volume-ready'),
        raster: canvas?.dataset.materialRaster ? JSON.parse(canvas.dataset.materialRaster) : null,
        sourceFilter: baked?.filter,
        sourceVisibility: baked?.visibility,
        headTransform: head ? getComputedStyle(head).transform : null,
        cold: parseFloat(root.style.getPropertyValue('--rig-weather-cold')) || 0,
        pageWidth: document.documentElement.clientWidth,
        scrollWidth: document.documentElement.scrollWidth,
      };
    })
  );
  const filename = `${style}-${theme}-${scenario}.png`;
  await page.locator('.matrix').screenshot({ path: resolve(output, filename) });
  records.push({ style, theme, scenario, filename, poses, filters });
  await save();
  if (!baseline && companions.includes(style)) {
    for (const pose of poses) {
      if (pose.ready === 'true') {
        if (!pose.raster || pose.raster.histogram[255] === 0)
          throw new Error(`${style}: actual native opaque body required`);
        // The source matte was a broad alpha2 field. Antialiasing may still
        // produce isolated alpha2 edge pixels; it must not form a surface.
        if (pose.raster.histogram[2] > pose.raster.width * pose.raster.height * 0.01)
          throw new Error(`${style}: broad alpha2 field remains in the actual framebuffer`);
      } else if (pose.sourceVisibility !== 'visible' || !pose.sourceFilter?.includes('url('))
        throw new Error(`${style}: native filtered fallback required`);
    }
    if (
      filters?.some(
        filter =>
          filter.mattePixels === 0 ||
          filter.matteNotClear !== 0 ||
          filter.opaquePixels === 0 ||
          filter.svgControlChanged !== 0 ||
          filter.normalizationBeyondIdentity !== 0
      )
    )
      throw new Error(
        `${style}: normalization must remove matte and preserve opaque RGBA relative to the identity filter`
      );
  }
}

async function save() {
  await writeFile(
    resolve(output, 'evidence.json'),
    JSON.stringify(
      {
        engine,
        browser: browser.version(),
        baseline,
        warmOnly,
        method:
          'Actual untouched native framebuffer alpha histogram; mounted SVG filter rasterized against the mounted source; opaque RGBA compared exactly.',
        errors,
        warnings,
        records,
      },
      null,
      2
    )
  );
}

try {
  for (const style of styles) {
    for (const theme of companions.includes(style) && !warmOnly ? ['light', 'dark'] : ['light']) {
      const { context, page } = await open(style, theme);
      try {
        const filters =
          companions.includes(style) && !baseline && !warmOnly && theme === 'light'
            ? await inspectFilter(page)
            : null;
        await capture(page, style, theme, 'front', filters);
        if (!companions.includes(style)) continue;
        for (const gaze of warmOnly ? [] : ['left', 'right']) {
          await page.locator('#gaze').selectOption(gaze);
          await page.clock.runFor(800);
          await capture(page, style, theme, `turn-${gaze}`);
        }
        await page.emulateMedia({ reducedMotion: 'reduce' });
        await settle(page, false);
        await capture(page, style, theme, 'reduced');
        await page.emulateMedia({ reducedMotion: 'no-preference' });
        await settle(page, true);
        await page
          .locator('[data-live="true"] [data-volume-canvas]')
          .evaluateAll(canvases =>
            canvases.forEach(canvas =>
              canvas.getContext('webgl').getExtension('WEBGL_lose_context').loseContext()
            )
          );
        await settle(page, false);
        await capture(page, style, theme, 'context-lost');
        await page.locator('#gaze').selectOption('left');
        await page.clock.runFor(800);
        await capture(page, style, theme, 'fallback-left');
      } finally {
        await context.close();
      }
    }
    process.stdout.write(`${style}: native material scenarios captured\n`);
  }
  if (errors.length) throw new Error(`Native browser errors: ${errors.join('\n')}`);
} finally {
  await browser.close();
  await save();
}
