/** Actual-browser matrix capture against the local native-component bench. */
import { chromium } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';

const output = resolve(process.argv[2] ?? '../../../output/playwright/avatar-limbs/after');
const expressions = process.argv.includes('--baseline')
  ? ['neutral']
  : ['neutral', 'attentive', 'thinking', 'speaking', 'surprise'];
const characters = ['spirit', 'moss', 'lumen', 'nimbo', 'orbit', 'bip', 'boulon', 'oscar'];
const channels = ['armL', 'armR', 'wristL', 'wristR', 'legL', 'legR', 'footL', 'footR'];
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ channel: 'chromium', headless: true });
const context = await browser.newContext({
  viewport: { width: 1180, height: 700 },
  deviceScaleFactor: 2,
  reducedMotion: 'no-preference',
});
const page = await context.newPage();
const errors = [];
page.on('pageerror', error => errors.push(error.message));
page.on('console', message => {
  if (message.type() === 'error') errors.push(message.text());
});
const results = [];
try {
  for (const character of characters) {
    await page.goto(`http://127.0.0.1:5187/?character=${character}`);
    await page.locator('[data-live="true"] [data-volume-ready="true"]').last().waitFor();
    for (const expression of expressions) {
      await page.locator('#expression').selectOption(expression);
      await page.waitForTimeout(1600);
      const samples = [];
      for (let step = 0; step < 8; step++) {
        samples.push(
          await page
            .locator('[data-live="true"] .lia-eyes')
            .evaluateAll(
              (roots, names) =>
                roots.map(root =>
                  Object.fromEntries(
                    names.map(name => [
                      name,
                      Number.parseFloat(
                        root.style.getPropertyValue(
                          `--rig-${name.replace(/[A-Z]/g, value => `-${value.toLowerCase()}`)}`
                        )
                      ) || 0,
                    ])
                  )
                ),
              channels
            )
        );
        await page.waitForTimeout(160);
      }
      const screenshot = `${character}-${expression}.png`;
      await page.locator('main').screenshot({ path: resolve(output, screenshot) });
      results.push({ character, expression, samples, screenshot });
    }
    if (!process.argv.includes('--baseline')) {
      await page.getByLabel('Dark', { exact: true }).check();
      await page.locator('#expression').selectOption('speaking');
      await page.waitForTimeout(900);
      await page.locator('main').screenshot({ path: resolve(output, `${character}-dark.png`) });
      await page.locator('#size').selectOption('sm');
      await page.waitForTimeout(600);
      await page.locator('main').screenshot({ path: resolve(output, `${character}-compact.png`) });
    }
    process.stdout.write(`${character}: captured\n`);
  }
  await writeFile(
    resolve(output, 'evidence.json'),
    JSON.stringify(
      {
        browser: browser.version(),
        viewport: page.viewportSize(),
        deviceScaleFactor: 2,
        errors,
        results,
      },
      null,
      2
    )
  );
  if (errors.length) throw new Error(`Browser errors: ${errors.join('\n')}`);
} catch (error) {
  await page.screenshot({ path: resolve(output, 'failure.png') });
  await writeFile(
    resolve(output, 'failure.json'),
    JSON.stringify({ errors, url: page.url() }, null, 2)
  );
  throw error;
} finally {
  await context.close();
  await browser.close();
}
