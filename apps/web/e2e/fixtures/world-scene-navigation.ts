/** Navigate by authored place centres; a tiny minimap cannot target an object pixel exactly. */
import { expect, type Page } from '@playwright/test';
import { WORLD } from '../../src/features/world/definition';
import type { WorldProp } from '../../src/features/world/types';
import { compactWorld } from './world-admission';
export async function frameWorldProp(page: Page, prop: WorldProp, label: (id: string) => string) {
  const zone = WORLD.zones.find(
    z => prop.x >= z.x && prop.y >= z.y && prop.x < z.x + z.width && prop.y < z.y + z.height
  );
  if (!zone) throw new Error('Object has no authored place');
  const summary = page.locator('[data-world-place-menu]');
  const toggle = page.locator('.world-hud-toggle');
  // A desktop HUD still mounting its map has no toggle: reading the folded
  // state from the summary's visibility clicked a control that never appears.
  let reveal = false;
  if (await compactWorld(page)) {
    await expect(toggle).toBeVisible();
    reveal = (await toggle.getAttribute('aria-expanded')) === 'false';
    if (reveal) await toggle.click();
  }
  await summary.click();
  await page
    .locator('.world-map-directory')
    .getByRole('menuitem', { name: label(zone.id), exact: true })
    .click();
  await expect(summary).toBeFocused();
  const canvas = page.locator('canvas.world-canvas');
  const bounds = await canvas.boundingBox();
  if (!bounds) throw new Error('Missing scene');
  const dx = prop.x + prop.width / 2 - (zone.x + zone.width / 2);
  const dy = prop.y + prop.depth / 2 - (zone.y + zone.height / 2);
  const zoom = Number((await page.locator('[data-world-zoom]').innerText()).replace('%', '')) / 100;
  const point = {
    x: bounds.x + bounds.width / 2 + (dx - dy) * 32 * zoom,
    y: bounds.y + bounds.height / 2 + ((dx + dy) * 16 - prop.height * 16) * zoom,
  };
  async function restoreControls() {
    if (!(await toggle.isVisible())) return;
    if (((await toggle.getAttribute('aria-expanded')) === 'true') === reveal) await toggle.click();
  }
  // Wide outdoor places do not fit one viewport. Pan through the real game
  // gesture instead of assuming that selecting a place exposes every object.
  for (let i = 0; i < 8; i++) {
    if (
      point.x > bounds.x + 80 &&
      point.x < bounds.x + bounds.width - 80 &&
      point.y > bounds.y + 150 &&
      point.y < bounds.y + bounds.height - 150 &&
      (await page.evaluate(
        ({ x, y }) =>
          document.elementFromPoint(x, y) === document.querySelector('canvas.world-canvas'),
        point
      ))
    ) {
      await restoreControls();
      return point;
    }
    // The expanded phone toolbar can cover the drag origin. A gesture swallowed
    // by the HUD must never be mistaken for a successful camera displacement.
    if ((await toggle.isVisible()) && (await toggle.getAttribute('aria-expanded')) === 'true')
      await toggle.click();
    const start = { x: bounds.x + bounds.width / 2, y: bounds.y + bounds.height / 2 };
    expect(
      await page.evaluate(
        ({ x, y }) =>
          document.elementFromPoint(x, y) === document.querySelector('canvas.world-canvas'),
        start
      )
    ).toBe(true);
    const dx = Math.max(-bounds.width / 3, Math.min(bounds.width / 3, start.x - point.x));
    const dy = Math.max(-bounds.height / 3, Math.min(bounds.height / 3, start.y - point.y));
    await page.mouse.move(start.x, start.y);
    await page.mouse.down();
    await page.mouse.move(start.x + dx, start.y + dy, { steps: 8 });
    await page.mouse.up();
    point.x += dx;
    point.y += dy;
    await page.evaluate(() => new Promise<void>(resolve => requestAnimationFrame(() => resolve())));
  }
  throw new Error('Authored object could not be framed through the game camera');
}
/** Use the same opaque pixel picking as a human; never dispatch a private runtime command. */
export async function clickWorldProp(page: Page, prop: WorldProp, label: (id: string) => string) {
  const point = await frameWorldProp(page, prop, label);
  const toggle = page.locator('.world-hud-toggle');
  if ((await toggle.isVisible()) && (await toggle.getAttribute('aria-expanded')) === 'true')
    await toggle.click();
  expect(
    await page.evaluate(
      ({ x, y }) =>
        document.elementFromPoint(x, y) === document.querySelector('canvas.world-canvas'),
      point
    )
  ).toBe(true);
  await page.mouse.move(point.x, point.y);
  await expect
    .poll(() => page.locator('canvas.world-canvas').evaluate(node => node.style.cursor))
    .toBe('pointer');
  await page.mouse.click(point.x, point.y);
  return point;
}
