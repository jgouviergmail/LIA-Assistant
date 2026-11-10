/** One untouched browser screenshot of the selected native wrapped identities. */
import { chromium } from '@playwright/test';
import { mkdir, readdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { setTimeout as wait } from 'node:timers/promises';

const argument = name =>
  process.argv.find(value => value.startsWith(`--${name}=`))?.slice(name.length + 3);
const origin = argument('origin') ?? 'http://127.0.0.1:5189';
const styles = argument('styles')?.split(',') ?? ['bip', 'oscar', 'nimbo'];
if (!styles.length || styles.some(style => !['bip', 'oscar', 'nimbo'].includes(style)))
  throw new Error('Unknown wrapped identity requested');
const expectedCount = new Set(styles).size * 2;
const output = resolve(argument('output') ?? '../../../output/playwright/avatar-artistry/overview');
await mkdir(output, { recursive: true });
if ((await readdir(output)).length) throw new Error('Evidence directory must be empty');
const browser = await chromium.launch({ channel: 'chromium', headless: true });
const errors = [],
  warnings = [];
try {
  const context = await browser.newContext({
    viewport: { width: 1200, height: 1000 },
    deviceScaleFactor: 1,
    reducedMotion: 'no-preference',
  });
  await context.route('**/*', route => {
    const url = new URL(route.request().url());
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
  await page.clock.install({ time: new Date('2026-11-07T12:00:00Z') });
  await page.clock.pauseAt(await page.evaluate(() => Date.now() + 10000));
  await page.goto(
    `${origin}/?contact=true&characters=${styles.join(',')}&cold=true&life=true&size=xl`
  );
  let poses = [];
  for (let frame = 0; frame < 160; frame++) {
    await page.clock.runFor(32);
    poses = await page.locator('[data-live="true"] .lia-eyes').evaluateAll(roots =>
      roots.map(root => ({
        label: root.closest('article').querySelector('h2').textContent,
        ready: root.dataset.volumeReady,
        scarfReady: root.dataset.volumeScarfReady,
        cold: parseFloat(root.style.getPropertyValue('--rig-weather-cold')),
        fontSize: getComputedStyle(root).fontSize,
        scarfDescendants: [...root.querySelectorAll('.lia-ambient-weather--cold')].reduce(
          (sum, element) => sum + element.querySelectorAll('*').length + 1,
          0
        ),
        channels: root.getAttribute('style'),
        time: Date.now(),
      }))
    );
    if (
      poses.length === expectedCount &&
      poses.every(pose => pose.ready === 'true' && pose.scarfReady === 'true' && pose.cold > 0.6)
    )
      break;
    await wait(20);
  }
  if (
    poses.length !== expectedCount ||
    poses.some(pose => pose.ready !== 'true' || pose.scarfReady !== 'true' || pose.cold <= 0.6)
  )
    throw new Error('Every requested native wrapped identity must be ready');
  const filename = expectedCount === 6 ? 'six-avatars.png' : `${expectedCount}-avatars.png`;
  await page.locator('.matrix').screenshot({ path: resolve(output, filename) });
  await context.close();
  await writeFile(
    resolve(output, 'evidence.json'),
    JSON.stringify(
      {
        browser: browser.version(),
        origin,
        styles,
        filename,
        method:
          'One untouched browser screenshot at the product XL size, native rig and GPU; no image composition or retouch.',
        poses,
        errors,
        warnings,
      },
      null,
      2
    )
  );
  if (errors.length) throw new Error('Unexpected browser errors');
} finally {
  await browser.close();
}
