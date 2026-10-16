import { writeFileSync } from 'node:fs';
import type { Page } from '@playwright/test';
import { test, expect, idleNotificationStream } from '../fixtures';
import { awaitStyledPage } from './overflow-report';

test.use({ viewport: { width: 360, height: 800 }, isMobile: true, hasTouch: true });

async function capture(page: Page, name: string) {
  const png = await page.screenshot({ fullPage: false });
  const rgb = await page.evaluate(async base64 => {
    const image = new Image();
    image.src = `data:image/png;base64,${base64}`;
    await image.decode();
    const canvas = document.createElement('canvas');
    canvas.width = image.width;
    canvas.height = image.height;
    const context = canvas.getContext('2d');
    if (!context) throw new Error('Screenshot decoding requires a canvas');
    context.drawImage(image, 0, 0);
    // The outer page gutter carries only the decorative background.
    return Array.from(context.getImageData(2, Math.floor(image.height / 2), 1, 1).data).slice(0, 3);
  }, png.toString('base64'));
  writeFileSync(test.info().outputPath(`${name}.png`), png);
  await test.info().attach(name, { body: png, contentType: 'image/png' });
  const geometry = await page.evaluate(() => {
    const backdrop = document.querySelector('.cosmos-nebula');
    if (!backdrop) throw new Error('Expected the real application cosmos');
    const ancestors = [];
    let node: Element | null = backdrop;
    while (node) {
      const style = getComputedStyle(node);
      const rect = node.getBoundingClientRect();
      ancestors.push({
        tag: node.tagName,
        classes: node.className,
        top: rect.top,
        height: rect.height,
        position: style.position,
        zIndex: style.zIndex,
        transform: style.transform,
        filter: style.filter,
        contain: style.contain,
        overflow: style.overflow,
        background: style.backgroundColor,
        isolation: style.isolation,
      });
      node = node.parentElement;
    }
    return { scrollY, viewport: { width: innerWidth, height: innerHeight }, ancestors };
  });
  const report = JSON.stringify({ rgb, ...geometry }, null, 2);
  writeFileSync(test.info().outputPath(`${name}-geometry.json`), report);
  await test.info().attach(`${name}-geometry`, { body: report, contentType: 'application/json' });
  return rgb;
}

test('mobile settings retains the painted cosmos after a real downward scroll', async ({
  page,
  authenticate,
  mockApi,
}) => {
  await authenticate({ theme: 'oled', voice_enabled: false });
  await mockApi([
    idleNotificationStream,
    { url: /\/api\/v1\/connectors(?:\?fresh=true)?$/, json: { connectors: [] } },
  ]);
  await page.goto('/en/dashboard/settings');
  await awaitStyledPage(page, 'mobile cosmos background');
  await expect(page.locator('html')).toHaveAttribute('data-oled', '');
  await expect(page.locator('.cosmos-nebula')).toHaveCSS('position', 'fixed');
  const before = await capture(page, 'mobile-background-before-scroll');
  // Mobile WebKit does not implement Playwright's wheel input. Scroll the
  // real document and inspect a fresh viewport paint on both engines.
  await page.evaluate(() => window.scrollBy({ top: 1200, behavior: 'instant' }));
  await expect.poll(() => page.evaluate(() => scrollY)).toBeGreaterThan(800);
  await expect
    .poll(() => page.locator('.cosmos-nebula').evaluate(node => node.getBoundingClientRect().top))
    .toBe(0);
  const after = await capture(page, 'mobile-background-after-scroll');
  expect(
    Math.max(...before.map((channel, index) => Math.abs(channel - after[index]))),
    `Background gutter before=${before} after=${after}`
  ).toBeLessThanOrEqual(8);
});
