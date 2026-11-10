/** Real texture delivery, coherent native fallback and retained-resource recovery. */
import { chromium } from '@playwright/test';
import { mkdir, readdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { setTimeout as wait } from 'node:timers/promises';

const argument = name =>
  process.argv.find(value => value.startsWith(`--${name}=`))?.slice(name.length + 3);
const origin = argument('origin') ?? 'http://127.0.0.1:5189';
const output = resolve(
  argument('output') ?? '../../../output/playwright/avatar-artistry/scarf-loading'
);
await mkdir(output, { recursive: true });
if ((await readdir(output)).length) throw new Error('Evidence directory must be empty');
const browser = await chromium.launch({ channel: 'chromium', headless: true });
const records = [],
  errors = [],
  failedRequests = [],
  requests = [],
  consoleMessages = [];
let completed = false;

async function read(page) {
  return page.locator('[data-live="true"] .lia-eyes').evaluateAll(roots =>
    roots.map(root => {
      const canvas = root.querySelector('canvas'),
        head = root.querySelector('.lia-head');
      return {
        variant: root.closest('article').dataset.variant,
        ready: root.dataset.volumeReady,
        scarfReady: root.dataset.volumeScarfReady,
        yaw: parseFloat(root.style.getPropertyValue('--rig-head-yaw')),
        cold: parseFloat(root.style.getPropertyValue('--rig-weather-cold')),
        bodyUploads: Number(canvas?.dataset.bodyUploads ?? 0),
        bufferUploads: Number(canvas?.dataset.bufferUploads ?? 0),
        fallback: getComputedStyle(head, '::before').visibility,
        perspective: getComputedStyle(root).perspective,
        bodySource: getComputedStyle(head, '::before').backgroundImage,
      };
    })
  );
}

async function until(page, predicate) {
  for (let attempt = 0; attempt < 180; attempt++) {
    await page.clock.runFor(32);
    const state = await read(page);
    if (state.length === 2 && state.every(predicate)) return state;
    await wait(20);
  }
  throw new Error(`Native state did not settle: ${JSON.stringify(await read(page))}`);
}

async function capture(page, mode, phase, state) {
  const filename = `${mode}-${phase}.png`;
  await page.locator('.matrix').screenshot({ path: resolve(output, filename) });
  records.push({ mode, phase, filename, state });
  await save();
}

async function save() {
  await writeFile(
    resolve(output, 'evidence.json'),
    JSON.stringify(
      {
        browser: browser.version(),
        origin,
        method:
          'Only the real scarf texture response is delayed or failed; native body texture, rig, painter, fallback and warm recovery remain unchanged.',
        errors,
        completed,
        requests,
        consoleMessages,
        failedRequests,
        records,
      },
      null,
      2
    )
  );
}

try {
  for (const mode of ['delayed', 'failed']) {
    const context = await browser.newContext({
      viewport: { width: 1440, height: 1200 },
      deviceScaleFactor: 2,
      reducedMotion: 'no-preference',
    });
    let release;
    const gate = new Promise(resolve => {
      release = resolve;
    });
    await context.route('**/*', route => {
      const url = new URL(route.request().url());
      if (url.origin === origin && !url.pathname.startsWith('/api/')) return route.continue();
      errors.push(`Unexpected request: ${url.origin}${url.pathname}`);
      return route.abort();
    });
    await context.route('**/avatars/scarf/v1/front.webp', async route => {
      if (mode === 'failed') return route.abort('failed');
      await gate;
      return route.continue();
    });
    const page = await context.newPage();
    page.on('pageerror', error => errors.push(error.message));
    page.on('request', request => requests.push({ mode, path: new URL(request.url()).pathname }));
    page.on('console', message => {
      if (['warning', 'error'].includes(message.type()))
        consoleMessages.push({
          mode,
          type: message.type(),
          text: message.text(),
          url: message.location().url,
        });
    });
    page.on('requestfailed', request =>
      failedRequests.push({
        mode,
        path: new URL(request.url()).pathname,
        error: request.failure()?.errorText,
      })
    );
    await page.addInitScript(() => {
      const texture = WebGLRenderingContext.prototype.texImage2D;
      WebGLRenderingContext.prototype.texImage2D = function (...args) {
        const result = texture.apply(this, args),
          source = args.at(-1);
        if (
          this.canvas instanceof HTMLCanvasElement &&
          source instanceof HTMLImageElement &&
          source.src.endsWith('/body.webp')
        )
          this.canvas.dataset.bodyUploads = String(
            Number(this.canvas.dataset.bodyUploads ?? 0) + 1
          );
        return result;
      };
      const buffer = WebGLRenderingContext.prototype.bufferData;
      WebGLRenderingContext.prototype.bufferData = function (...args) {
        const result = buffer.apply(this, args);
        if (this.canvas instanceof HTMLCanvasElement)
          this.canvas.dataset.bufferUploads = String(
            Number(this.canvas.dataset.bufferUploads ?? 0) + 1
          );
        return result;
      };
    });
    try {
      await page.clock.install({ time: new Date('2026-11-07T12:00:00Z') });
      await page.clock.pauseAt(await page.evaluate(() => Date.now() + 10_000));
      await page.goto(
        `${origin}/?character=bip&cold=false&life=false&size=xl&gaze=left&closeup=true`
      );
      await page.clock.runFor(64);
      await capture(page, mode, 'warm-static', await read(page));
      await page.goto(
        `${origin}/?character=bip&cold=false&life=true&size=xl&gaze=left&closeup=true`
      );
      const warmLive = await until(
        page,
        state => state.ready === 'true' && Math.abs(state.yaw) > 0.5
      );
      await capture(page, mode, 'warm-live', warmLive);
      if (
        requests.some(
          request => request.mode === mode && request.path.startsWith('/avatars/scarf/')
        )
      )
        throw new Error(`${mode}: warm live and static avatars must not fetch scarf textures`);
      await page.goto(
        `${origin}/?character=bip&cold=true&life=true&size=xl&gaze=left&closeup=true`,
        { waitUntil: 'domcontentloaded' }
      );
      const pending = await until(
        page,
        state => state.bodyUploads > 0 && state.cold > 0.5 && Math.abs(state.yaw) > 0.5
      );
      await capture(page, mode, 'body-ready-scarf-unavailable', pending);
      if (
        pending.some(
          state =>
            state.ready !== 'false' ||
            state.scarfReady !== 'false' ||
            state.fallback !== 'visible' ||
            state.perspective !== 'none'
        )
      )
        throw new Error(
          `${mode}: body and cloth must share the native fallback camera while scarf is unavailable`
        );
      if (mode === 'delayed') {
        release();
        const ready = await until(
          page,
          state => state.ready === 'true' && state.scarfReady === 'true'
        );
        await capture(page, mode, 'scarf-ready', ready);
      }
      await page.locator('#cold').uncheck();
      const warm = await until(page, state => state.ready === 'true' && state.cold < 0.01);
      await capture(page, mode, 'warm-recovery', warm);
      if (warm.some((state, index) => state.bodyUploads !== pending[index].bodyUploads))
        throw new Error(`${mode}: warm recovery must retain the loaded native body texture`);
    } finally {
      release();
      await context.close();
    }
  }
  if (
    errors.length ||
    failedRequests.some(
      request => request.mode !== 'failed' || request.path !== '/avatars/scarf/v1/front.webp'
    ) ||
    consoleMessages.some(
      message =>
        message.type === 'error' &&
        !(message.mode === 'failed' && message.url === `${origin}/avatars/scarf/v1/front.webp`)
    )
  )
    throw new Error('Unexpected browser failure during the isolated texture journey');
  completed = true;
} finally {
  await browser.close();
  await save();
}
