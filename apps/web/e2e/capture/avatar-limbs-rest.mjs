/** Deterministic native-clock observation; no pose injection or alternate renderer. */
import { chromium } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';

const output = resolve(process.argv[2] ?? '../../../output/playwright/avatar-limbs/rest');
const characters = ['spirit', 'moss', 'lumen', 'nimbo', 'orbit', 'bip', 'boulon', 'oscar'];
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ channel: 'chromium', headless: true });
const results = [];
try {
  for (const character of characters) {
    const context = await browser.newContext({
      viewport: { width: 1180, height: 700 },
      deviceScaleFactor: 2,
    });
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.addInitScript(() => {
      let seed = 0x12345678;
      Math.random = () => {
        seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
        return seed / 0x100000000;
      };
    });
    await page.clock.install({ time: new Date('2026-11-07T12:00:00Z') });
    await page.clock.pauseAt(await page.evaluate(() => Date.now() + 100));
    await page.goto(`http://127.0.0.1:5187/?character=${character}&life=true`);
    await page.locator('[data-live="true"] .lia-eyes').last().waitFor();
    await page.clock.runFor(300);
    const samples = [];
    const peaks = { arm: 0, foot: 0 };
    const scenes = new Set();
    for (let elapsed = 0; elapsed < 44000; elapsed += 250) {
      await page.clock.runFor(250);
      const poses = await page.locator('[data-live="true"] .lia-eyes').evaluateAll(roots =>
        roots.map(root => ({
          scene: root.dataset.scene,
          ready: root.dataset.volumeReady,
          channels: Object.fromEntries(
            ['arm-l', 'arm-r', 'wrist-l', 'wrist-r', 'leg-l', 'leg-r', 'foot-l', 'foot-r'].map(
              name => [name, parseFloat(root.style.getPropertyValue(`--rig-${name}`)) || 0]
            )
          ),
        }))
      );
      samples.push({ elapsed, poses });
      for (const kind of ['arm', 'foot']) {
        const peak = Math.max(
          ...poses.flatMap(pose => [
            Math.abs(pose.channels[`${kind}-l`]),
            Math.abs(pose.channels[`${kind}-r`]),
          ])
        );
        if (peak > peaks[kind] + 2) {
          peaks[kind] = peak;
          await page
            .locator('main')
            .screenshot({ path: resolve(output, `${character}-${kind}-peak.png`) });
        }
      }
      for (const pose of poses) {
        if (!pose.scene || scenes.has(pose.scene)) continue;
        scenes.add(pose.scene);
        await page
          .locator('main')
          .screenshot({ path: resolve(output, `${character}-${pose.scene}.png`) });
      }
    }
    await page.locator('#size').selectOption('sm');
    await page.setViewportSize({ width: 380, height: 820 });
    await page.clock.runFor(400);
    await page.locator('main').screenshot({ path: resolve(output, `${character}-mobile.png`) });
    results.push({ character, peaks, scenes: [...scenes], errors, samples });
    await context.close();
    process.stdout.write(
      `${character}: rest peaks ${JSON.stringify(peaks)}, scenes ${[...scenes].join(',')}\n`
    );
  }
  await writeFile(
    resolve(output, 'evidence.json'),
    JSON.stringify({ browser: browser.version(), results }, null, 2)
  );
  if (results.some(result => result.errors.length))
    throw new Error('Native browser errors; see evidence.json');
} finally {
  await browser.close();
}
